#!/usr/bin/env python3
"""Phase 1 — Dance You inventory v3 (family rules verified visually 2026-09-18).

Verified rules:
  F1: 26A-D                = photos of product 26
  F1: 4A/4B/4C/4D + XH     = SEPARATE products; '4B.jpg' is a photo of 4BXH
  F1: 8A/8B/8C -N          = separate products; -N = photo number
  F1: 29 Black Back/Front  = colour + view
  F1: DZxxx Colour (A)     = colourways; trailing A = extra photo
  F1: LTCxxxx CC Name      = colour-code + colour name (one product)
  F1: PS90W2 J03-N / Pink  = colourways of PS90W2 J03 (leading photo digits stripped)
  F2: DY3118 / 3118        = same product (DY prefix optional, merged second pass)
      DY3118B / DY3506B    = BACK view photo
  F3: 161236 + 161236A     = photos of one product; lowercase b = photo B
      same stem, different extension = format duplicate (best ext kept)
  F3: 7xxx + PS/BS/CS/SG   = colour/material code suffix
  F4: 1106A / 1106AB       = colour A (photo B); letters after code = COLOUR index
      CODE+Colour-word+letter = colour + photo letter
      7004 vs 7004N etc.   = N-variants -> separate SKU (open question)
      9935A vs 9935A2      = colour A, photo 2
      8006or8504 etc.      = ambiguous double codes -> user question
      TS1 S / TS1 M        = S/M -> likely sizes (open question)
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "real-images" / "dance you"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
BEST_EXT_ORDER = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"]

JUNK_STEMS = {"thumbs.db", "img_20131219_063105.jpg", "instagram logo.jpg",
              "shoe pencil case"}  # pencil case: ask user? keep as accessory actually

QUESTIONS: dict[str, str] = {
    "8006OR8504": "'8006or8504' — which code is correct?",
    "8010OR8508": "'8010 or 8508' — which code is correct?",
    "8503OR8506": "'8503 or 8506' — which code is correct?",
    "9966OR9967": "'9966 or 9967' — one product or two codes?",
    "7004N": "'N' variant of 7004 — separate SKU (width?) or same product?",
    "7005N": "N variant of 7005 — same question as 7004N.",
    "8008S": "'S' on 8008 — variant or photo label?",
    "9935A": "A2 = second photo of colour A?",
    "TS1": "TS1 S / TS1 M / TS1 A — S/M = sizes?",
    "TS2": "TS2 / TS2A — sizes too?",
    "3120": "3120: single photo, no colour — code correct?",
    "CD004": "CD004 ALREADY EXISTS in the shop (product 494). 'CD004 Skin' here: new colour "
             "of the existing product or new product? Existing SKUs excluded from batch 1.",
}


def norm(code: str) -> str:
    return code.upper().replace("-", "").replace(" ", "")


def parse(stem: str, folder: str):
    low = stem.lower()
    if (low in JUNK_STEMS or re.match(r"^\d{8}_\d{6}", stem)
        or re.match(r"^IMG_\d{8}_\d{6}", stem) or "logo" in low):
        return None
    if low.endswith(" jpg"):          # 'LTC1227 A02 Black jpg.jpg' typo
        stem = stem[:-4]

    # ── folder 1 ────────────────────────────────────────────────────────────
    if folder == "1":
        if re.match(r"^26[A-D]$", stem, re.I):
            return "26", "", f"photo {stem[-1].upper()}"
        m = re.match(r"^4([ABCD])XH$", stem, re.I)
        if m:
            return f"4{m.group(1).upper()}XH", "", ""
        if re.match(r"^4B$", stem, re.I):
            return "4BXH", "", ""
        m = re.match(r"^8([ABC])-(\d)$", stem, re.I)
        if m:
            return f"8{m.group(1).upper()}", "", f"photo {m.group(2)}"
        m = re.match(r"^(29)\s+Black\s+(Back|Front)$", stem, re.I)
        if m:
            return m.group(1), "Black", m.group(2).lower()
        m = re.match(r"^(DZ\d{3})\s+(.+?)(?:\s+([A-Z]))?$", stem, re.I)
        if m:
            return m.group(1).upper(), m.group(2).strip(), (
                f"photo {m.group(3).upper()}" if m.group(3) else "")
        m = re.match(r"^(LTC[0-9A-Z]+)\s+((?:A|B)\d{2})\s+(.+)$", stem, re.I)
        if m:
            return m.group(1).upper(), f"{m.group(2)} {m.group(3)}", ""
        m = re.match(r"^(PS90W2?)\s+(J\d{2})[-\s]+(?:(\d)-)?(.+)$", stem, re.I)
        if m:
            return f"{m.group(1)} {m.group(2)}", m.group(4), ""
        m = re.match(r"^(PS987)\s+(J\d+)\s+(.+)$", stem, re.I)
        if m:
            return m.group(1), f"{m.group(2)} {m.group(3)}", ""
        m = re.match(r"^(62)\s+(.+?)(?:\s+([AB]))?$", stem, re.I)
        if m:
            return m.group(1), m.group(2).strip(), (
                f"photo {m.group(3).upper()}" if m.group(3) else "")
        m = re.match(r"^(\d+[A-Z]+)-(\d)$", stem)  # 94MWD-1, 952WE-2 (photo numbers)
        if m:
            return m.group(1).upper(), "", f"photo {m.group(2)}"
        m = re.match(r"^(P\d+[A-Z]?|DZ002)$", stem, re.I)
        if m:
            return stem.upper(), "", ""

    # ── folder 2 ────────────────────────────────────────────────────────────
    if folder == "2":
        m = re.match(r"^(?:DY)?(\d{3,4})(B?)\s*(.*)$", stem, re.I)
        if m:
            view = "back" if m.group(2).upper() == "B" else ""
            return f"DY{m.group(1)}", m.group(3).strip(), view
        m = re.match(r"^(DY\d{3,5})[ _-]*(.*)$", stem, re.I)
        if m:
            return m.group(1).upper(), m.group(2), ""
        m = re.match(r"^([A-Za-z0-9]+)\s+(.*)$", stem)
        if m:
            return m.group(1), m.group(2), ""

    # ── folder 3 ────────────────────────────────────────────────────────────
    if folder == "3":
        m = re.match(r"^(\d{4,6})([aAbB])(?:\s+(.+))?$", stem)
        if m:
            return m.group(1), (m.group(3) or ""), f"photo {m.group(2).upper()}"
        m = re.match(r"^(\d{4,6})\s*(.*)$", stem)
        if m:
            return m.group(1), m.group(2), ""
        m = re.match(r"^([A-Z]{1,3}\d{3,4})([aAbB])(?:\s+(.+))?$", stem)
        if m:
            return m.group(1).upper(), (m.group(3) or ""), f"photo {m.group(2)}"
        m = re.match(r"^([A-Z]{1,3}\d{3,4})\s+(.+?)\s+([A-Z])$", stem)
        if m:
            return m.group(1).upper(), m.group(2), f"photo {m.group(3)}"
        m = re.match(r"^([A-Z]{1,3}\d{3,4})(?:\s+(.+))?$", stem)
        if m:
            return m.group(1).upper(), m.group(2) or "", ""
        m = re.match(r"^([A-Z]{1,3}\d{2,4})$", stem, re.I)
        if m:
            return stem.upper(), "", ""
        return stem, "", ""

    # ── folder 4 ────────────────────────────────────────────────────────────
    if folder == "4":
        # 9931A Burgundy / 9935A2 Black  (colour index + colour name [+ photo no])
        m = re.match(r"^(\d{3,4})([A-Z])(\d?)\s+(.+)$", stem)
        if m:
            colour = f"colour-{m.group(2)} {m.group(4)}".title()
            photo = f"photo {m.group(3)}" if m.group(3) else ""
            return m.group(1), colour, photo
        # 7008Tan / D006183Black (camel-case colour glued to code)
        m = re.match(r"^(\d{3,4}|[A-Z]\d{5})([A-Z][a-z]+)$", stem)
        if m and m.group(2).lower() not in {"n"}:
            return m.group(1), m.group(2), ""
        m = re.match(r"^(\d{3,4})([A-Z])([A-Z])?$", stem, re.I)
        if m:  # 1106A (colour A), 1106AB (colour A photo B), 1106C
            colour = f"colour-{m.group(2).upper()}"
            photo = f"photo {m.group(3).upper()}" if m.group(3) else ""
            code = m.group(1) + ("N" if m.group(2).upper() == "N" else "")
            colour = "" if m.group(2).upper() == "N" else colour
            return (code if m.group(2).upper() == "N" else m.group(1)), colour, photo
        m = re.match(r"^(\d{3,4})\s+(.+?)\s+(Back|Front)$", stem, re.I)
        if m:
            return m.group(1), m.group(2), m.group(3).lower()
        m = re.match(r"^(\d{3,4})\s+(.+?)(?:\s+([AB]))?$", stem)
        if m:
            return m.group(1), m.group(2), (f"photo {m.group(3).upper()}" if m.group(3) else "")
        m = re.match(r"^(\d{3,4})([a-z])$", stem, re.I)
        if m:
            return m.group(1), "", f"photo {m.group(2).upper()}"
        if re.match(r"^\d{3,4}$", stem):
            return stem, "", ""
        m = re.match(r"^(TS\s*\d)\s*([SMA])?$", stem, re.I)
        if m:
            return m.group(1).upper().replace(" ", ""), m.group(2) or "", ""
        return stem, "", ""

    parts = stem.split()
    return (parts[0], " ".join(parts[1:]), "") if len(parts) > 1 else (stem, "", "")


def best_format(files: list[Path]) -> list[Path]:
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_stem[f.stem.casefold()].append(f)
    kept = []
    for _stem, group in by_stem.items():
        best = min(group, key=lambda p: BEST_EXT_ORDER.index(p.suffix.lower())
                   if p.suffix.lower() in BEST_EXT_ORDER else 99)
        kept.append(best)
    return sorted(kept, key=lambda p: p.name.casefold())


def main() -> int:
    raw: dict[tuple, dict] = defaultdict(lambda: {"files": [], "colours": set(),
                                                 "photos": set(), "views": set()})
    junk = []
    for folder in sorted(p for p in BRAND_DIR.iterdir() if p.is_dir()):
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in IMG_EXT:
                junk.append((folder.name, f.name, f"non-image {f.suffix}"))
                continue
            parsed = parse(f.stem, folder.name)
            if parsed is None:
                junk.append((folder.name, f.name, "junk"))
                continue
            code, colour, photo = parsed
            key = (folder, norm(code))
            e = raw.setdefault(key, {"code": code, "files": [], "colours": set(),
                                     "photos": set(), "views": set()})
            e["files"].append(f)
            if colour:
                c = colour.strip().title()
                if c.lower().startswith("colour-"):
                    e["colours"].add(c)          # keep colour-index form distinct
                else:
                    e["colours"].add(c)
            if photo:
                e["photos"].add(photo)

    # second pass: merge bare-code duplicates into DY-prefixed ones (3118 -> DY3118)
    all_codes = {c for (_f, c) in raw}
    merged: dict[tuple, dict] = {}
    for (folder, code), e in raw.items():
        if not code.lower().startswith("dy") and ("dy" + code) in all_codes:
            key = (folder, "dy" + code)
            merged[key]["files"].extend(e["files"])
            merged[key]["colours"] |= e["colours"]
            continue
        merged[(folder, code)] = e

    out = BRAND_DIR / "inventory-review.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["folder", "code", "colours", "n_photos", "photo_files", "open_question"])
        n_q = 0
        for (folder, code), e in sorted(merged.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            best = best_format(e["files"])
            rel = " ; ".join(f"{folder}/{f.name}" for f in best)
            colours = " | ".join(sorted(e["colours"])) or "(single)"
            q = next((t for k, t in QUESTIONS.items() if norm(code).startswith(k)), "")
            if q:
                n_q += 1
            w.writerow([folder.name, code, colours, len(best), rel, q])
    print(f"Dance You inventory: {len(merged)} products -> {out.name} ({n_q} with open questions)")
    print(f"junk/non-image ({len(junk)}): {junk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
