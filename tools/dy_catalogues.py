#!/usr/bin/env python3
"""Parse the Dance You / Dux / Go Dance catalogue PDFs (text layer) into a
code -> product-data map.

Catalogue formats:
  Dance U 2026.txt:   "DYxxxx Name" + "Colors : ..." + "Sizes : ..." + "Price : N"
  Dux Dance 2026.txt: same, prices in Euros, plain codes (8A, 26, DZ002...)
  Go Dance Latin:     "CODE ColourDesc" + "Heel : ..." + "Sizes : EU a - b" + "(Reduced) Price : N Euros"
                      (heel can vary per size: multi-line "Heel : 2.5 (Size 35,36...)")
  Go Dance Catalogue: "CODE Name" + "Sizes : ..." + colour-code matrix lines (no prices)

Output: real-images/dance you/catalogues/catalogue-data.csv
        columns: source, code, name, colours, sizes, price, reduced_price, heel
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

CAT = Path(__file__).resolve().parent.parent / "real-images" / "dance you" / "catalogues"


def parse_latin(text: str, source: str):
    """Go Dance Latin raw format: sequential blocks:
         CODE ColourDesc
         Heel : ...
         Sizes : EU 35 - 42
         (Reduced) Price : N Euros
    """
    rows = []
    lines = [l.strip() for l in text.splitlines()]
    i = 0
    code_re = re.compile(r"^((?:\d{4,6}|7\d{3}[A-Z]{2}|CD\d{3})\s+.+)$")
    while i < len(lines):
        m = code_re.match(lines[i])
        if not m or re.match(r"^(Heel|Sizes|Price)", lines[i], re.I):
            i += 1
            continue
        code, name = m.group(1).split(maxsplit=1)
        name = name.strip()
        rec = {"source": source, "code": code, "name": name, "colours": "",
               "sizes": "", "price": "", "reduced_price": "", "heel": ""}
        j = i + 1
        while j < len(lines):
            l2 = lines[j]
            if code_re.match(l2) or re.match(r"^\d+$", l2):
                break
            if re.match(r"^Heel\s*:", l2, re.I):
                heel = re.sub(r"^Heel\s*:\s*", "", l2, flags=re.I)
                heel = re.sub(r"\s*\(Size[^)]*\)", "", heel).strip()
                heel = re.sub(r"\s+", " ", heel)
                rec["heel"] = f"{rec['heel']}; {heel}".strip("; ") if rec["heel"] else heel
            elif re.match(r"^Sizes\s*:", l2, re.I):
                rec["sizes"] = re.sub(r"^Sizes\s*:\s*EU\s*", "", l2, flags=re.I)
            elif re.match(r"^(Reduced Price|Price)\s*:", l2, re.I):
                mm = re.match(r"^(Reduced Price|Price)\s*:\s*([\d.]+)", l2, re.I)
                if mm:
                    key = ("reduced_price" if mm.group(1).lower().startswith("reduced")
                           else "price")
                    rec[key] = mm.group(2)
            j += 1
        if rec["name"]:
            rows.append(rec)
        i = max(j, i + 1)
    return rows


def main() -> int:
    rows: list[dict] = []

    for source_name in ("Go Dance Latin Catalogue 2026.txt", "Dance U 2026.txt",
                        "Dux Dance 2026.txt", "Go Dance Catalogue 2026.txt"):
        p = CAT / source_name
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8", errors="replace")
        if "latin" in source_name.lower():
            rows.extend(parse_latin(content, "go-dance-latin"))
            continue
        # block style: Dance U / Dux (+ Go Dance full catalogue, partial data)
        current = None
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"^\d{1,2}$", line) or re.match(r"^(Colors?|Sizes?|Price|Heel|Color|Size)\b", line, re.I):
                pass
            m = re.match(r"^((?:DY|DZ|LTCH?|LTEY)?[0-9]{2,6}[A-Z]{0,3}|8[ABC]|26|29)\s+(.+)$", line)
            if m and not re.match(r"^(Colors?|Sizes?|Price|Heel|Color|Size)\b", line, re.I):
                name = m.group(2).strip()
                if re.search(r"[A-Za-z]{4}", name) and not re.match(r"^[\d.]+$", name):
                    current = {"source": source_name, "code": m.group(1), "name": name,
                               "colours": "", "sizes": "", "price": "",
                               "reduced_price": "", "heel": ""}
                    rows.append(current)
                    continue
            if current:
                if re.match(r"^Colors?\s*:", line, re.I):
                    current["colours"] = re.sub(r"^Colors?\s*:\s*", "", line, flags=re.I)
                elif re.match(r"^(Sizes?|Size)\s*:", line, re.I):
                    current["sizes"] = re.sub(r"^(Sizes?|Size)\s*:\s*", "", line, flags=re.I)
                elif re.match(r"^(Reduced Price|Price)\s*:", line, re.I):
                    mm = re.match(r"^(Reduced Price|Price)\s*:\s*([\d.]+)", line, re.I)
                    if mm:
                        key = ("reduced_price" if mm.group(1).lower().startswith("reduced")
                               else "price")
                        current[key] = mm.group(2)

    merged: dict[str, dict] = {}
    for r in rows:
        key = r["code"].upper().replace(" ", "")
        if key not in merged:
            merged[key] = dict(r)
        else:
            tgt = merged[key]
            for f in ("name", "colours", "sizes", "price", "reduced_price", "heel"):
                if not tgt[f] and r.get(f):
                    tgt[f] = r[f]

    out = CAT / "catalogue-data.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "colours", "sizes", "price", "reduced_price", "heel", "source"])
        for code, r in sorted(merged.items()):
            w.writerow([code, r.get("name", ""), r.get("colours", ""), r.get("sizes", ""),
                        r.get("price", ""), r.get("reduced_price", ""), r.get("heel", ""),
                        r.get("source", "")])
    print(f"catalogue-data.csv: {len(merged)} codes -> {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
