#!/usr/bin/env python3
"""Merge products.grishko.csv with grishkoshop.com official data.

Matching: token overlap between our model names and official names
("fouette pro" -> "0501/1 Fouette Pro"; "maya 1" -> "0504 Maya I").
After match: sku = official article code, title_en = official name minus the
code prefix, description_en = official copy, price = official USD incl VAT.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dy_csv import build_description

ROOT = Path(__file__).resolve().parent.parent
OFF = ROOT / "data" / "grishko" / "official-data.csv"
CSV_IN = ROOT / "products.grishko.csv"


def strip_code(name: str) -> str:
    """Official names start with the code ('0501 Fouette, with drawstring') -> strip it."""
    return re.sub(r"^[0-9A-Z]{2,10}[-/ ]+\s*", "", name).strip()


def main() -> int:
    official = list(csv.DictReader(open(ROOT / "data/grishko/official-data.csv")))
    index: dict[str, dict] = {}
    for r in official:
        low = re.sub(r"^\d+[a-zA-Z/+]*\s*", "", (r["name"] or "").lower())
        index[r["code"].upper()] = r
        index[low] = r

    prows = list(csv.DictReader(open(CSV_IN)))
    fieldnames = ["sku", "title_en", "description_en", "title_el", "description_el",
                  "price", "sizes", "colours", "fabric", "short_desc_en", "short_desc_el"]

    matched, unmatched = 0, []
    for row in prows:
        title = (row["title_en"] or row["sku"]).strip()
        tokens = re.split(r"[-\s]+", title.lower())
        cands: list[tuple[float, dict]] = []
        for r in official:
            name = (r["name"] or "").lower()
            score = 0.0
            for tok in tokens_of(title):
                if tok in name:
                    score += len(tok)
            if score >= 6:
                cands.append((score, r))
        cands.sort(key=lambda c: (-c[0], c[1]["code"]))
        if cands:
            best = cands[0][1]
            row["sku"] = best["code"]
            name = best["name"]
            row["title_en"] = re.sub(r"^[0-9A-Z]{2,10}[-/ ]+\s*", "", name).strip() or name
            if best["description"]:
                row["description_en"] = re.sub(
                    r"\s*SIZE CHART.*$", "", best["description"], flags=re.I).strip()
            row["price"] = best["price"] or row["price"]
            row["currency"] = best["currency"]
            row["fabric"] = fabric_from((best["name"] or "") + " " + (best["description"] or ""))
            # refresh Greek title + description from the official EN name
            from brand_inventory import greek_title
            row["title_el"] = greek_title(row["title_en"], "grishko")
            row["description_el"] = build_description(
                row["title_en"], colours_en=row["colours"], heel="", sizes="",
                lang="el", el_title=row["title_el"])
            matched += 1
        else:
            unmatched.append(row)

    for row in prows:
        for extra in list(row.keys()):
            if extra not in fieldnames:
                del row[extra]
    print(f"matched: {matched}/{len(prows)}")
    if unmatched:
        print("unmatched:", " ".join(u["title_en"] or u["sku"] for u in unmatched))
    tmp = CSV_IN.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(prows)
    tmp.replace(CSV_IN)
    print("updated products.grishko.csv")
    return 0


def fabric_from(name: str) -> str:
    low = name.lower()
    for kw, f in [("satin", "Satin"), ("canvas", "Canvas"), ("leatheroid", "Leatheroid"),
                  ("leather", "Leather"), ("mesh", "Mesh"), ("velvet", "Velvet"),
                  ("velour", "Velour"), ("lycra", "Lycra"), ("cotton", "Cotton"),
                  ("microfibre", "Microfibre"), ("flyknit", "Flyknit"),
                  ("elastic", "Elastic"), ("ribbon", "Ribbon"), ("duck", "Duck"),
                  ("patent", "Patent"), ("chiffon", "Chiffon")]:
        if kw in low:
            return f
    return ""


def tokens_of(title: str) -> list[str]:
    stop = {"with", "and", "the", "of"}
    return [t for t in re.split(r"[-\s]+", title.lower()) if len(t) >= 3 and t not in stop]


if __name__ == "__main__":
    sys.exit(main())
