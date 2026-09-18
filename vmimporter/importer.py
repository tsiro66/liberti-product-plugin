"""Import service: plan building (diff against DB) + transactional execution.

Design: every CSV row is diffed against the current database state and turned
into a list of declarative Action objects (the PLAN). The plan is displayed in
dry-run mode and executed unchanged in import mode — plan and execution cannot
drift because the executor only interprets actions, it never re-derives diffs.

Update semantics (owned fields only — everything else is preserved):
  owned:     product core row (modified_on/by + flag fixes), EN/EL product_name
             and product_desc (plus product_s_desc when the optional CSV column
             is filled), the default price row, custom-field rows for ids 6/7/10,
             product image links + ordering, media rows for newly registered files.
  untouched: slug, customtitle, metadesc, metakey, published (unless
             --set-published), manufacturer links, all other custom fields
             (e.g. custom 18 "Heel"), shoppergroup-specific price rows, orders,
             ratings, the vmcustomadvanced plugin tables.

Idempotency: diffs compare desired vs current, so re-running the same CSV
yields a plan with zero actions -> no transaction is even started.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import CUSTOM_COLOUR, CUSTOM_FABRIC, CUSTOM_SIZE, Config
from .db import Database
from .images import MIME_TYPES, copy_image, natural_key
from .products_csv import ProductRow, parse_price
from .repos import (
    CategoryRepository,
    CustomFieldRepository,
    LanguageRepository,
    MediaRepository,
    PriceRepository,
    ProductRepository,
)
from .slug import slugify, unique_slug

# Action kinds -----------------------------------------------------------------
A_INSERT_CORE = "insert_core"
A_INSERT_LANG = "insert_lang"
A_UPDATE_LANG = "update_lang"
A_INSERT_PRICE = "insert_price"
A_UPDATE_PRICE = "update_price"
A_INSERT_CF = "insert_cf"
A_DELETE_CF = "delete_cf"
A_INSERT_MEDIA = "insert_media"
A_INSERT_LINK = "insert_link"
A_UPDATE_LINK = "update_link"
A_INSERT_CAT_LINK = "insert_cat_link"
A_UPDATE_CORE = "update_core"

TABLE_OF = {
    A_INSERT_CORE: "virtuemart_products",
    A_INSERT_LANG: "virtuemart_products_{lang}",
    A_UPDATE_LANG: "virtuemart_products_{lang}",
    A_INSERT_PRICE: "virtuemart_product_prices",
    A_UPDATE_PRICE: "virtuemart_product_prices",
    A_INSERT_CF: "virtuemart_product_customfields",
    A_DELETE_CF: "virtuemart_product_customfields",
    A_INSERT_MEDIA: "virtuemart_medias",
    A_INSERT_LINK: "virtuemart_product_medias",
    A_UPDATE_LINK: "virtuemart_product_medias",
    A_INSERT_CAT_LINK: "virtuemart_product_categories",
    A_UPDATE_CORE: "virtuemart_products",
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Action:
    kind: str
    description: str
    payload: dict = field(default_factory=dict)

    def table(self) -> str:
        t = TABLE_OF[self.kind]
        return t.format(lang=self.payload.get("lang", ""))


@dataclass
class ProductPlan:
    sku: str
    operation: str = "CREATE"            # CREATE | UPDATE | NOOP
    product_id: int | None = None
    slug: str = ""
    note: str | None = None
    actions: list[Action] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: url -> local source path, for files that must be copied to the server
    copies: dict[str, Path] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(self.actions)

    def summary_lines(self) -> list[str]:
        lines = [
            f"SKU: {self.sku}",
            f"Operation: {self.operation}"
            + (f" (product id {self.product_id})" if self.product_id else ""),
        ]
        if self.note:
            lines.append(f"Note: {self.note}")
        for w in self.warnings:
            lines.append(f"Warning: {w}")
        if not self.actions:
            lines.append("Changes: none (already up to date)")
        for a in self.actions:
            lines.append(f"  [{a.kind.upper():12s}] {a.table()}: {a.description}")
        return lines


class ProductImporter:
    def __init__(self, db: Database, cfg: Config) -> None:
        self.db = db
        self.cfg = cfg
        self.products = ProductRepository(db)
        self.languages = LanguageRepository(db)
        self.prices = PriceRepository(db)
        self.customfields = CustomFieldRepository(db)
        self.media = MediaRepository(db)
        self.categories = CategoryRepository(db)

    # ------------------------------------------------------------------ helpers

    def net_price(self, row: ProductRow) -> float:
        value = row.price_net
        if value is None:
            value, err = parse_price(row.price_raw)
            if err:
                raise ValueError(f"SKU {row.sku}: {err}")
        if self.cfg.price_mode == "gross":
            return round(value / (1.0 + self.cfg.vat_rate / 100.0), 6)
        return value

    # ------------------------------------------------------------------ planning

    def build_plan(self, row: ProductRow) -> ProductPlan:
        plan = ProductPlan(sku=row.sku)
        # deterministic image order regardless of CSV/caller order
        row.images = sorted(row.images, key=lambda p: natural_key(p.name))
        try:
            product_id, note = self.products.find_id_by_sku(row.sku)
        except RuntimeError as exc:
            plan.errors.append(str(exc))
            return plan
        if note:
            plan.note = note

        if product_id is None:
            plan.operation = "CREATE"
            self._plan_create(plan, row)
        else:
            plan.operation = "UPDATE"
            plan.product_id = product_id
            self._plan_update(plan, row, product_id)
        return plan

    # -- CREATE -------------------------------------------------------------------

    def _plan_create(self, plan: ProductPlan, row: ProductRow) -> None:
        if self.products.sku_exists(row.sku):
            plan.errors.append(
                f"SKU '{row.sku}' already exists with different spelling "
                f"(case/whitespace); refusing to auto-create a duplicate"
            )
            return

        published = 0 if self.cfg.set_published is None else self.cfg.set_published
        plan.slug = self._plan_slug(plan, row.title_en)
        net = self.net_price(row)

        plan.actions.append(Action(A_INSERT_CORE, f"core row (published={published}, gtin=sku)", {
            "sku": row.sku, "published": published,
            "has_categories": 1 if self.cfg.category_id else 0,
            "has_medias": 1 if row.images else 0,
        }))
        for lang, title, desc, s_desc in (
            ("en_gb", row.title_en, row.description_en, row.short_desc_en),
            ("el_gr", row.title_el, row.description_el, row.short_desc_el),
        ):
            plan.actions.append(Action(
                A_INSERT_LANG,
                f"name='{title[:60]}', description ({len(desc)} chars), slug='{plan.slug}'",
                {"lang": lang, "name": title, "description": desc, "s_desc": s_desc,
                 "slug": plan.slug},
            ))
        plan.actions.append(Action(
            A_INSERT_PRICE, f"net price {net} (tax rule 1, EUR, shoppergroup 0)",
            {"net": net},
        ))
        self._plan_customfields(plan, row, None)
        self._plan_media(plan, row, None)
        if self.cfg.category_id:
            plan.actions.append(Action(
                A_INSERT_CAT_LINK, f"link to category {self.cfg.category_id}",
                {"category_id": self.cfg.category_id},
            ))

    def _plan_slug(self, plan: ProductPlan, title_en: str) -> str:
        base = slugify(title_en)
        taken: set[str] = set()
        for lang in self.languages.LANGS:
            taken |= set(self.languages.taken_slugs(lang))
        slug = unique_slug(base, taken)
        if slug != base:
            plan.warnings.append(f"slug '{base}' already taken, using '{slug}'")
        return slug

    # -- UPDATE ---------------------------------------------------------------------

    def _plan_update(self, plan: ProductPlan, row: ProductRow, product_id: int) -> None:
        net = self.net_price(row)

        self._plan_language_diff(plan, row, product_id)
        self._plan_price_diff(plan, row, product_id, net)
        self._plan_customfields(plan, row, product_id)
        self._plan_media(plan, row, product_id)
        self._plan_category_link(plan, product_id)

        core = self.products.get_core(product_id)
        extra_sets: list[str] = []
        if core:
            if (self.cfg.set_published is not None
                    and core["published"] != self.cfg.set_published):
                extra_sets.append("published")
                plan.warnings.append(
                    f"published explicitly set to {self.cfg.set_published} via --set-published "
                    f"(current: {core['published']})"
                )
            if any(a.kind == A_INSERT_MEDIA for a in plan.actions) and not core["has_medias"]:
                extra_sets.append("has_medias")
            if (any(a.kind == A_INSERT_CAT_LINK for a in plan.actions)
                    and not core["has_categories"]):
                extra_sets.append("has_categories")
        if plan.actions or extra_sets:
            plan.actions.append(Action(
                A_UPDATE_CORE,
                "modified_on/by" + (f" + {', '.join(extra_sets)}" if extra_sets else ""),
                {"extra_sets": extra_sets},
            ))

    def _plan_language_diff(self, plan: ProductPlan, row: ProductRow, product_id: int) -> None:
        # slugs already stored for this product (missing rows reuse the sibling
        # language's slug — same-slug-per-product is the shop convention and
        # keeps URLs stable)
        stored_slugs: dict[str, str] = {}
        for lang in self.languages.LANGS:
            r = self.languages.get(product_id, lang)
            if r:
                stored_slugs[lang] = r["slug"]

        for lang, title, desc, s_desc in (
            ("en_gb", row.title_en, row.description_en, row.short_desc_en),
            ("el_gr", row.title_el, row.description_el, row.short_desc_el),
        ):
            current = self.languages.get(product_id, lang)
            if current is None:
                sibling_slug = next(
                    (s for l, s in stored_slugs.items() if l != lang and s), None)
                slug = sibling_slug or self._plan_slug(plan, row.title_en)
                plan.actions.append(Action(
                    A_INSERT_LANG, f"missing language row: name='{title[:60]}'",
                    {"lang": lang, "name": title, "description": desc,
                     "s_desc": s_desc, "slug": slug},
                ))
                continue
            changes: list[str] = []
            if (current["product_name"] or "") != title:
                changes.append(f"name '{(current['product_name'] or '')[:40]}' -> '{title[:40]}'")
            if (current["product_desc"] or "") != desc:
                changes.append(
                    f"description ({len(current['product_desc'] or '')} -> {len(desc)} chars)"
                )
            if s_desc and current["product_s_desc"] != s_desc:
                changes.append("short description")
            if changes:
                plan.actions.append(Action(
                    A_UPDATE_LANG, "; ".join(changes),
                    {"lang": lang, "name": title, "description": desc,
                     "s_desc": s_desc if s_desc else None},
                ))

    def _plan_price_diff(
        self, plan: ProductPlan, row: ProductRow, product_id: int, net: float,
    ) -> None:
        count = self.prices.count_default_price_rows(product_id)
        if count > 1:
            plan.warnings.append(
                f"{count} default price rows exist (shoppergroup 0, qty 0-0); "
                f"updating the lowest-id one only"
            )
        current = self.prices.get_default_price_row(product_id)
        if current is None:
            plan.actions.append(Action(
                A_INSERT_PRICE, f"net price {net} (tax rule 1, EUR, shoppergroup 0)",
                {"net": net},
            ))
        elif abs(float(current["product_price"] or 0) - net) > 1e-9:
            plan.actions.append(Action(
                A_UPDATE_PRICE,
                f"net price {current['product_price']} -> {net} "
                f"(price row {current['virtuemart_product_price_id']})",
                {"net": net, "price_row_id": int(current["virtuemart_product_price_id"])},
            ))

    # -- custom fields (ids 6/7/10 only) ----------------------------------------------

    def _plan_customfields(
        self, plan: ProductPlan, row: ProductRow, product_id: int | None,
    ) -> None:
        """Set-diff per managed custom field.

        An empty CSV cell means 'not provided': existing values stay untouched.
        Removal happens only inside customs 6/7/10 and only when the CSV
        provides a non-empty list. customfield_price is always 0 — this
        reproduces the database convention (every existing Colour row is 0 and
        the CSV format carries no surcharge amounts; see analysis section 6).
        """
        managed = (
            (CUSTOM_SIZE, row.sizes, "Size"),
            (CUSTOM_COLOUR, row.colours, "Colour"),
            (CUSTOM_FABRIC, row.fabric, "Fabric"),
        )
        for custom_id, desired, label in managed:
            if not desired:
                continue
            existing = (
                self.customfields.list_for(product_id, custom_id) if product_id else []
            )
            existing_values = {r["customfield_value"] for r in existing}
            for v in desired:
                if v not in existing_values:
                    plan.actions.append(Action(
                        A_INSERT_CF, f"{label} = '{v}' (custom {custom_id}, price 0, published 0)",
                        {"custom_id": custom_id, "value": v},
                    ))
            to_remove = [r for r in existing if r["customfield_value"] not in desired]
            if to_remove:
                plan.actions.append(Action(
                    A_DELETE_CF,
                    f"{label} rows removed: "
                    f"{', '.join(repr(r['customfield_value']) for r in to_remove)} "
                    f"(customfield_ids {[r['virtuemart_customfield_id'] for r in to_remove]})",
                    {"ids": [r["virtuemart_customfield_id"] for r in to_remove]},
                ))

    # -- media --------------------------------------------------------------------------

    def _plan_media(
        self, plan: ProductPlan, row: ProductRow, product_id: int | None,
    ) -> None:
        """Deterministic image handling.

        Desired order = CSV-matched files in natural filename order; the first
        one becomes the main image (VirtueMart convention: product_medias
        ordering 1). Existing product images not managed by this CSV are
        KEPT and appended after the desired ones — nothing is ever deleted.
        Ordering is renumbered 1..N, which keeps repeated imports idempotent.
        """
        desired_urls: list[str] = []
        warned_no_dir = False
        for path in row.images:
            url = f"{self.cfg.media_url_prefix}/{path.name}"
            desired_urls.append(url)
            if self.cfg.vm_media_dir:
                if not (Path(self.cfg.vm_media_dir) / path.name).exists():
                    plan.copies[url] = path
            elif not warned_no_dir:
                warned_no_dir = True
                plan.warnings.append(
                    "VM_MEDIA_DIR not configured: physical file copy location unknown "
                    "(database rows still planned)"
                )

        existing = self.media.list_product_images(product_id) if product_id else []
        existing_by_url = {r["file_url"]: r for r in existing}

        for pos, url in enumerate(desired_urls, start=1):
            if url in existing_by_url:
                continue
            mimetype = MIME_TYPES.get(Path(url).suffix.lower(), "application/octet-stream")
            meta = row.title_en if pos == 1 else ""
            plan.actions.append(Action(
                A_INSERT_MEDIA,
                f"'{Path(url).name}' ({mimetype})"
                + (", file_meta = EN title (main image)" if meta else ""),
                {"url": url, "title": Path(url).name, "mimetype": mimetype, "meta": meta},
            ))

        unmanaged = [r for r in existing if r["file_url"] not in desired_urls]
        for r in unmanaged:
            plan.warnings.append(
                f"existing image kept (not managed by this CSV): {r['file_url']}"
            )

        ordered_urls = desired_urls + [r["file_url"] for r in unmanaged]
        for pos, url in enumerate(ordered_urls, start=1):
            link = existing_by_url.get(url)
            if link is None:
                plan.actions.append(Action(
                    A_INSERT_LINK, f"link ordering {pos}: {Path(url).name}",
                    {"url": url, "ordering": pos},
                ))
            elif int(link["ordering"]) != pos:
                plan.actions.append(Action(
                    A_UPDATE_LINK,
                    f"ordering {int(link['ordering'])} -> {pos}: {Path(url).name}",
                    {"join_id": int(link["join_id"]), "ordering": pos},
                ))

    def _plan_category_link(self, plan: ProductPlan, product_id: int) -> None:
        if not self.cfg.category_id:
            return
        if not self.categories.link_exists(product_id, self.cfg.category_id):
            plan.actions.append(Action(
                A_INSERT_CAT_LINK,
                f"link to category {self.cfg.category_id}",
                {"category_id": self.cfg.category_id},
            ))

    # ------------------------------------------------------------------ execution

    def execute(self, plan: ProductPlan) -> None:
        """Execute a plan. Files are copied BEFORE the DB transaction: the
        filesystem cannot roll back, and an orphan image file is harmless while
        a media row without its file is not. Any DB failure rolls the whole
        product back."""
        if plan.errors:
            raise RuntimeError("; ".join(plan.errors))
        if not plan.has_changes:
            return

        for src in plan.copies.values():
            try:
                copy_image(src, self.cfg.vm_media_dir, self.cfg.media_url_prefix)
            except Exception as exc:
                raise RuntimeError(f"image copy failed for {src.name}: {exc}") from exc

        self.db.begin()
        try:
            self._execute_actions(plan)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _execute_actions(self, plan: ProductPlan) -> None:
        now = now_str()
        user_id = self.cfg.vm_admin_user_id
        new_media_ids: dict[str, int] = {}   # url -> media_id inserted in this tx
        pid = plan.product_id

        for action in plan.actions:
            k = action.kind
            p = action.payload

            if k == A_INSERT_CORE:
                pid = self.products.insert_core(
                    sku=p["sku"], published=p["published"],
                    has_categories=p["has_categories"], has_medias=p["has_medias"],
                    now=now, user_id=user_id,
                )
                plan.product_id = pid

            elif k == A_INSERT_LANG:
                self.languages.insert(
                    pid, p["lang"], name=p["name"], description=p["description"],
                    s_desc=p.get("s_desc") or "", metadesc=p.get("s_desc") or "",
                    metakey=p.get("s_desc") or "", customtitle=p["name"],
                    slug=p["slug"],
                )

            elif k == A_UPDATE_LANG:
                self.languages.update_owned_fields(
                    pid, p["lang"], name=p["name"], description=p["description"],
                    s_desc=p.get("s_desc"),
                )

            elif k == A_INSERT_PRICE:
                self.prices.insert(pid, p["net"], now=now, user_id=user_id)

            elif k == A_UPDATE_PRICE:
                self.prices.update_price(
                    p["price_row_id"], p["net"], now=now, user_id=user_id,
                )

            elif k == A_INSERT_CF:
                self.customfields.insert(
                    pid, p["custom_id"], p["value"], now=now, user_id=user_id,
                )

            elif k == A_DELETE_CF:
                self.customfields.delete_by_ids(p["ids"])

            elif k == A_INSERT_MEDIA:
                media_id = self.media.insert(
                    file_title=p["title"], file_url=p["url"], mimetype=p["mimetype"],
                    file_meta=p["meta"], now=now, user_id=user_id,
                )
                new_media_ids[p["url"]] = media_id

            elif k == A_INSERT_LINK:
                media_id = new_media_ids.get(p["url"])
                if media_id is None:
                    media_id = self.media.find_id_by_url(p["url"])
                if media_id is None:
                    raise RuntimeError(
                        f"media row for {p['url']} does not exist and was not planned; "
                        f"refusing to create a dangling product-media link"
                    )
                self.media.insert_link(pid, media_id, p["ordering"])

            elif k == A_UPDATE_LINK:
                self.media.update_link_ordering(p["join_id"], p["ordering"])

            elif k == A_INSERT_CAT_LINK:
                self.categories.insert_link(pid, p["category_id"])

            elif k == A_UPDATE_CORE:
                extra_sets: list[str] = []
                extra_params: list = []
                core = self.products.get_core(pid)
                for flag in p.get("extra_sets", []):
                    if flag == "published":
                        extra_sets.append("published = %s")
                        extra_params.append(self.cfg.set_published)
                    elif flag == "has_medias" and core and not core["has_medias"]:
                        extra_sets.append("has_medias = 1")
                    elif flag == "has_categories" and core and not core["has_categories"]:
                        extra_sets.append("has_categories = 1")
                self.products.touch(pid, now, user_id, extra_sets, extra_params)

            else:  # pragma: no cover
                raise RuntimeError(f"unknown action kind: {k}")
