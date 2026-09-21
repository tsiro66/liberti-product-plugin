"""CSV parsing and validation.

CSV format (documented in README):
    sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric
    CD004,Go Dance Latin Shoes CD004,...,<p>...</p>,<p>...</p>,96.50,35|36|37|38,BLK|RED,Leather

  - `sizes`, `colours`, `fabric` accept multiple values separated by `|`.
    Values are stripped; empty entries are dropped; duplicates collapse (warn).
    An empty cell means "not provided": existing DB values for that field are
    left untouched on update.
  - `price` uses a dot as decimal separator; a single comma is tolerated
    (European notation) and converted. The semantics of the number (net vs
    gross) are controlled by --price-mode, not by the CSV.
  - optional columns: short_desc_en, short_desc_el (product_s_desc),
    category_id (per-product category; pipe-separated for several, e.g. `62|65`).
    An EMPTY cell means "no category for this row" (even if --category-id is
    given). If the column is absent entirely, the --category-id CLI flag
    applies to every new product. Ids are validated against the DB during
    planning (unknown id = error for that row).
  - optional column: manufacturer_id (single virtuemart_manufacturer_id; the
    shop convention is one manufacturer per product). Empty/absent = no
    manufacturer. Validated against the DB during planning.
  - unknown columns are a validation error (typo protection).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field

REQUIRED_COLUMNS = [
    "sku",
    "title_en",
    "description_en",
    "title_el",
    "description_el",
    "price",
    "sizes",
    "colours",
    "fabric",
]
OPTIONAL_COLUMNS = ["short_desc_en", "short_desc_el", "category_id",
                    "manufacturer_id"]
KNOWN_COLUMNS = set(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)

MULTI_VALUE_FIELDS = ("sizes", "colours", "fabric")


class ValidationError(Exception):
    """Raised with a list of human-readable problems after full-file validation."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(f"{len(problems)} validation error(s): " + "; ".join(problems))


@dataclass
class ProductRow:
    row_number: int  # 1-based CSV data row (header excluded)
    sku: str
    title_en: str
    description_en: str
    title_el: str
    description_el: str
    price_raw: str
    sizes: list[str]
    colours: list[str]
    fabric: list[str]
    short_desc_en: str = ""
    short_desc_el: str = ""
    #: Per-product category ids from the CSV `category_id` column.
    #: None  = column absent from the header -> --category-id CLI flag applies.
    #: []    = column present but cell empty -> NO category for this row.
    #: [ids] = the validated later against the DB (importer planning).
    category_ids: list[int] | None = None
    #: Per-product manufacturer id from the CSV `manufacturer_id` column.
    #: None  = column absent from the header -> no manufacturer.
    #: None-celled empty list [] = column present but cell empty -> none.
    #: Single id = validated later against the DB (importer planning).
    manufacturer_id: int | None = None
    #: populated during image matching; deterministic order (main image first)
    images: list = field(default_factory=list)
    #: set later by the price module
    price_net: float | None = None


def split_multi(value: str | None) -> list[str]:
    """Split a pipe-separated cell into stripped, non-empty values (order kept)."""
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def dedupe_keep_order(values: list[str]) -> tuple[list[str], list[str]]:
    """Return (deduped list, list of duplicated values found)."""
    seen: set[str] = set()
    dupes: list[str] = []
    out: list[str] = []
    for v in values:
        if v in seen:
            if v not in dupes:
                dupes.append(v)
            continue
        seen.add(v)
        out.append(v)
    return out, dupes


def parse_price(raw: str) -> tuple[float | None, str | None]:
    """Parse a price cell. Returns (value, error). Tolerates one decimal comma."""
    text = (raw or "").strip()
    if not text:
        return None, "price is empty"
    if "," in text and "." in text:
        return None, f"price {raw!r} has both '.' and ','"
    if "," in text:
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None, f"price {raw!r} is not a number"
    if value <= 0:
        return None, f"price {raw!r} must be > 0"
    return value, None


def parse_csv(path: str) -> tuple[list[ProductRow], list[str]]:
    """Parse and validate the whole file.

    Returns (rows, warnings). Raises ValidationError listing ALL problems
    (never fails on the first one) so the operator sees the full picture.
    """
    problems: list[str] = []
    warnings: list[str] = []

    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            try:
                header = [h.strip().lower() for h in next(reader)]
            except StopIteration:
                raise ValidationError(["CSV file is empty"])

            header = [h.lstrip("\ufeff") for h in header]
            unknown = [h for h in header if h not in KNOWN_COLUMNS]
            if unknown:
                # unknown columns are an error, but parsing continues so that the
                # operator sees ALL problems in one run
                problems.append(f"unknown column(s): {', '.join(unknown)}")
            missing = [c for c in REQUIRED_COLUMNS if c not in header]
            if missing:
                problems.append(f"missing required column(s): {', '.join(missing)}")
                raise ValidationError(problems)

            has_cat_col = "category_id" in header
            has_mf_col = "manufacturer_id" in header

            rows: list[ProductRow] = []
            seen_skus: dict[str, int] = {}

            for data in reader:
                if not data or all(not c.strip() for c in data):
                    continue  # tolerate blank lines
                if len(data) < len(header):
                    data = data + [""] * (len(header) - len(data))
                rec = dict(zip(header, (d.strip() for d in data)))
                n = reader.line_num
                row_num = n

                sku = rec.get("sku", "")
                if not sku:
                    problems.append(f"row {row_num}: sku is empty")
                    continue

                if sku.lower() in seen_skus:
                    problems.append(
                        f"row {row_num}: duplicate SKU '{sku}' "
                        f"(first seen on row {seen_skus[sku.lower()]})"
                    )
                else:
                    seen_skus[sku.lower()] = row_num

                for col, label in (
                    ("title_en", "title_en"),
                    ("description_en", "description_en"),
                    ("title_el", "title_el"),
                    ("description_el", "description_el"),
                ):
                    if not rec.get(col, ""):
                        problems.append(f"row {row_num} ({sku}): {label} is empty")

                price, price_err = parse_price(rec.get("price", ""))
                if price_err:
                    problems.append(f"row {row_num} ({sku}): {price_err}")

                multi: dict[str, list[str]] = {}
                for fieldname in MULTI_VALUE_FIELDS:
                    values = split_multi(rec.get(fieldname, ""))
                    for v in values:
                        if "\n" in v or "\r" in v:
                            problems.append(
                                f"row {row_num} ({sku}): malformed value in '{fieldname}': "
                                f"line break inside {v[:40]!r}"
                            )
                        elif len(v) > 2500:
                            # customfield_value is varchar(2500) — longer values
                            # would be truncated/corrupted on insert
                            problems.append(
                                f"row {row_num} ({sku}): value in '{fieldname}' exceeds "
                                f"2500 characters ({len(v)})"
                            )
                    values, dupes = dedupe_keep_order(values)
                    if dupes:
                        warnings.append(
                            f"row {row_num} ({sku}): duplicate value(s) in '{fieldname}' ignored: "
                            f"{', '.join(dupes)}"
                        )
                    multi[fieldname] = values

                # per-product category ids (CSV column wins over the CLI flag;
                # an empty cell means explicitly NO category for this row)
                category_ids: list[int] | None = None
                if has_cat_col:
                    raw_cat = rec.get("category_id", "")
                    if raw_cat:
                        cat_values = [t.strip() for t in raw_cat.split("|") if t.strip()]
                        parsed_ids: list[int] = []
                        for tok in cat_values:
                            try:
                                parsed_ids.append(int(tok))
                            except ValueError:
                                problems.append(
                                    f"row {row_num} ({sku}): category_id value {tok!r} "
                                    f"is not a category id (whole numbers only, e.g. 62|65)"
                                )
                        parsed_ids, cat_dupes = dedupe_keep_order(parsed_ids)
                        if cat_dupes:
                            warnings.append(
                                f"row {row_num} ({sku}): duplicate category_id(s) ignored: "
                                f"{', '.join(str(d) for d in cat_dupes)}"
                            )
                        category_ids = parsed_ids
                    else:
                        category_ids = []

                # per-product manufacturer (single id; empty = none)
                manufacturer_id: int | None = None
                if has_mf_col:
                    raw_mf = rec.get("manufacturer_id", "").strip()
                    if raw_mf:
                        if "|" in raw_mf:
                            problems.append(
                                f"row {row_num} ({sku}): manufacturer_id {raw_mf!r} must be a "
                                f"single id (the shop uses one manufacturer per product)"
                            )
                        else:
                            try:
                                manufacturer_id = int(raw_mf)
                            except ValueError:
                                problems.append(
                                    f"row {row_num} ({sku}): manufacturer_id value "
                                    f"{raw_mf!r} is not a manufacturer id (whole number, e.g. 16)"
                                )

                rows.append(
                    ProductRow(
                        row_number=row_num,
                        sku=sku,
                        title_en=rec.get("title_en", ""),
                        description_en=rec.get("description_en", ""),
                        title_el=rec.get("title_el", ""),
                        description_el=rec.get("description_el", ""),
                        price_raw=rec.get("price", ""),
                        sizes=multi["sizes"],
                        colours=multi["colours"],
                        fabric=multi["fabric"],
                        short_desc_en=rec.get("short_desc_en", ""),
                        short_desc_el=rec.get("short_desc_el", ""),
                        category_ids=category_ids,
                        manufacturer_id=manufacturer_id,
                        price_net=price,
                    )
                )

            if not rows:
                problems.append("CSV contains no data rows")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            [f"CSV is not valid UTF-8 (save/export the file as UTF-8): {exc}"]
        )
    except csv.Error as exc:
        raise ValidationError([f"malformed CSV structure: {exc}"])

    if problems:
        raise ValidationError(problems)
    return rows, warnings
