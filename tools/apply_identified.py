#!/usr/bin/env python3
"""Apply identified titles/descriptions to the product CSVs.

Sources:
  data/identified/danceyou-manual.csv  (visual + filename-derived)
  data/identified/grishko-manual.csv   (official-code corrections)

For each CSV row whose SKU matches a manual entry, overwrite:
  title_en, title_el, description_en, description_el (when non-empty)
  price (grishko manual only, when non-empty)
  sku (grishko manual official_code, when given)

Idempotent: rows not in the manual stay untouched.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDENT = ROOT / "data" / "identified"

FIELDS = ["sku", "title_en", "description_en", "title_el", "description_el",
          "price", "sizes", "colours", "fabric", "short_desc_en", "short_desc_el"]


def apply(csv_path: Path, manual_path: Path, sku_map: dict | None = None) -> tuple[int, int]:
    if not csv_path.exists() or not manual_path.exists():
        return 0, 0
    manual = {}
    for r in csv.DictReader(open(manual_path, encoding="utf-8")):
        manual[r["sku"].strip().upper()] = r
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    changed = 0
    for row in rows:
        key = row["sku"].strip().upper()
        m = manual.get(key)
        if not m:
            continue
        changed += 1
        for field in FIELDS:
            val = (m.get(field) or "").strip()
            if val:
                row[field] = val
        if sku_map and (m.get("official_code") or "").strip():
            row["sku"] = m["official_code"].strip()
    tmp = csv_path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[f for f in FIELDS if f in rows[0]] or FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})
    tmp.replace(csv_path)
    return changed, len(rows)


def main() -> int:
    n, total = apply(ROOT / "products.danceyou.csv", IDENT / "danceyou-manual.csv")
    print(f"danceyou: applied {n}/{total} rows")
    n, total = apply(ROOT / "products.grishko.csv", IDENT / "grishko-manual.csv")
    print(f"grishko: applied {n}/{total} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
