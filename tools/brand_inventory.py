#!/usr/bin/env python3
"""Phase 1 for Grishko + Capezio folders: inventory + draft CSV.

Grishko (83 files): Grishko pointe-shoe models + Go Dance-ish codes + accessories.
  - stems with a digit-leading code -> colour variants of one product (0405PT Black)
  - pure model names (Nova 2007 Pro, Fouette, Dream Pointe 2007) = separate products
    (same stem with different extensions = multiple photos of one product)
Capezio (97 files): first token = style code (102, B201W, 2037C), rest = model/colour
    name; "B122C BAL"/"B122C PSK" = colour codes of one style.

No catalogue PDFs provided for these brands -> titles from filenames, other data
cells left empty for the operator. Greek titles drafted from the EN name.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "real-images"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
BEST_EXT_ORDER = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"]

COLOUR_WORDS = {
    "black", "blue", "burgundy", "coffee", "gold", "grey", "gray", "ice blue",
    "laguna", "mirtillo", "misty blue", "orchid mist", "grey pink", "dusty pink",
    "bordeaux", "mirtillo", "orchid mist", "suntan", "light toast", "toast",
    "violet", "hunter green", "white", "pink", "purple", "sunset", "violet",
    "sky blue", "pastel", "turquoise", "poppy", "mauve", "satin", "matt",
    "matte", "toffee", "lilac", "lavender", "orchid",
}


def norm(code: str) -> str:
    return code.casefold().replace("-", "").replace("_", "").replace(" ", "")


def group_products(files: list[Path], brand: str) -> dict[str, dict]:
    if brand == "grishko":
        # code-leading stems group by first token; name-stems are their own product
        groups: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            stem = f.stem
            m = re.match(r"^(\d{3,6}[A-Z]{0,3}|[A-Z]{2}\d{3}[A-Z]?|[A-Z]\d[A-Z]?)"
                         r"[\s_-]+([A-Za-z ]+)$", stem)
            if m and any(w.lower() in COLOUR_WORDS for w in m.group(2).split()):
                groups[m.group(1)].append(f)
            else:
                groups[f.stem.casefold()].append(f)
        # normalize digit-led keys to their code token (0928402 Violet -> 0928402)
        for base in list(groups.keys()):
            m = re.match(r"^(\d{3,7}(?:-\d+)?)\s+(.+)$", base or "")
            if m and all(w.lower() in COLOUR_WORDS for w in m.group(2).split()):
                groups[m.group(1)] = groups[base]
                del groups[base]
        # fold digit-led short keys into longer ones (0405 -> 0405PT)
        keys = list(groups.keys())
        for short in keys:
            if re.fullmatch(r"\d{3,7}", short or ""):
                targets = [k for k in keys if k != short and norm(k).startswith(norm(short))
                           and len(norm(k)) - len(norm(short)) >= 2]
                if len(targets) == 1:
                    groups[targets[0]].extend(groups[short])
                    del groups[short]
        # merge stem-suffix duplicates: "0928402" + "0928402 Violet"
        for base in list(groups.keys()):
            if not re.fullmatch(r"\d{3,7}", base or ""):
                continue
            for k in list(groups.keys()):
                if k != base and norm(k).startswith(base + " "):
                    groups[base].extend(groups[k])
                    del groups[k]
        return {k: best_format(v) for k, v in groups.items()}
    if brand == "capezio":
        groups: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            m = re.match(r"^([A-Z]?\d{2,5}[A-Z]?[A-Z]?)\s+(.*)$", f.stem)
            if m:
                groups[m.group(1).upper()].append(f)
            else:
                groups[f.stem.casefold()].append(f)
        return {k: best_format(v) for k, v in groups.items()}
    raise ValueError(brand)


def best_format(files: list[Path]) -> list[Path]:
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_stem[f.stem.casefold()].append(f)
    kept = []
    for _s, g in by_stem.items():
        kept.append(min(g, key=lambda p: BEST_EXT_ORDER.index(p.suffix.lower())
                        if p.suffix.lower() in BEST_EXT_ORDER else 99))
    return sorted(kept, key=lambda p: p.name.casefold())


def title_words(stem: str) -> str:
    return re.sub(r"[_\s]+", " ", stem).strip()


def greek_title(en_title: str, brand: str) -> str:
    # very mechanical translation of common garment words
    t = en_title
    subs = [
        ("Pre Pointe", "Προ-Πουάν"), ("Pointe", "Πουάν"),
        ("Character Skirt", "Φούστα Χαρακτήρων"),
        ("Wrap Around Chiffon Skirt", "Περαστή Φούστα Σιφόν"),
        ("Wrap Around Skirt", "Περαστή Φούστα"),
        ("Camisole Tutu Dress", "Φόρεμα με τουτού"),
        ("Empire Dress", "Φόρεμα Empire"),
        ("Tutu Dress", "Φόρεμα με τουτού"),
        ("Camisole Leotard", "Λεοκάρδα με λάστιχα"),
        ("Tank Leotard", "Λεοκάρδα ολομέτωπη"),
        ("Pinch Front Tank Leotard", "Λεοκάρδα ολομέτωπη"),
        ("Short Sleeve Leotard", "Λεοκάρδα με κοντά μανίκια"),
        ("Long Sleeve Leotard", "Λεοκάρδα με μακριά μανίκια"),
        ("Flutter Sleeve Leotard", "Λεοκάρδα φλοτέρ"),
        ("3/4 Sleeve Leotard", "Λεοκάρδα με 3/4 μανίκια"),
        ("Leotard", "Λεοκάρδα"),
        ("Skirt", "Φούστα"),
        ("Jazz Sneakers", "Sneakers Τζαζ"),
        ("Jazz Shoes", "Παπούτσια Τζαζ"),
        ("Footlight", "Φουτλάιτ"), ("Tap", "Ταπ"),
        ("Sneakers", "Sneakers"),
        ("Ankle Weights", "Ασκήσεις Αστράγαλων"),
        ("Replacement Thread", "Λάστιχα αντικατάστασης"),
        ("Rolling Leg Massager", "Roller Μασάζ Ποδιών"),
        ("Massage Stick", "Roller Μασάζ"),
        ("Loop Resistant Bands", "Λάστιχα Αντίστασης"),
        ("Resistant Bands", "Λάστιχα Αντίστασης"),
        ("Ballet", "Μπαλέτου"), ("Dance", "Χορού"),
        ("Full Sole", "Full Sole"), ("Half Socks", "Μισές Κάλτσες"),
        ("Booties", "Μποτάκια"), ("Satin Ribbon", "Σατέν Κορδέλα"),
        ("Satin", "Σατέν"), ("Ribbon", "Κορδέλα"), ("Elastic", "Λάστιχο"),
        ("Mesh Elastic", "Δίχτυ Λάστιχο"), ("Velour", "Βελούδο"),
        ("Pencil Case", "Κασετίνα"), ("Keyring", "Κρεμαστό Κλειδί"),
        ("Heel Caps", "Μανταλάκια Τακουνιών"), ("Heel Grips", "Ενθέματα Τακουνιών"),
        ("Hairpin", "Καρφίτσα Μαλλιών"), ("Bag", "Τσάντα"),
        ("Backpack", "Σακίδιο"), ("Tote", "Τσάντα Tote"),
        ("Hot Shorts", "Σορτς"), ("Bra", "Σουτιέν"), ("Brief", "Σλιπ"),
        ("Skirt", "Φούστα"),
    ]
    for en, el in subs:
        t = re.sub(re.escape(en), el, t, flags=re.I)
    if brand == "grishko" and "Πουάν" not in t and re.search(r"pointe", en_title, re.I):
        pass
    return t.strip()


def fabric_from(name: str) -> str:
    low = name.lower()
    for kw, f in [("satin", "Satin"), ("canvas", "Canvas"), ("leatheroid", "Leatheroid"),
                  ("leather", "Leather"), ("mesh", "Mesh"), ("velvet", "Velvet"),
                  ("velour", "Velour"), ("lycra", "Lycra"), ("cotton", "Cotton"),
                  ("microfibre", "Microfibre"), ("flyknit", "Flyknit"),
                  ("elastic", "Elastic"), ("silk", "Silk"), ("duck", "Duck")]:
        if kw in low:
            return f
    return ""


def main() -> int:
    n_total = 0
    for brand, folder_name in (("grishko", "grishko"), ("capezio", "capezio")):
        brand_dir = REAL / brand
        files = [f for f in sorted(brand_dir.iterdir())
                 if f.is_file() and f.suffix.lower() in IMG_EXT]
        groups = group_products(files, brand)
        out = REAL / brand_dir.name / "inventory-review.csv"
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["code", "colours", "n_photos", "photo_files", "open_question"])
            for code, best in sorted(groups.items()):
                colours = []
                for f in best:
                    m = re.match(r"^[A-Za-z0-9]+[\s_-]+(.+)$", title_words(f.stem))
                    if m:
                        for word in m.group(1).split():
                            if word.lower() in COLOUR_WORDS:
                                colours.append(word.title())
                            elif (brand == "capezio"
                                  and re.fullmatch(r"[A-Z]{2,3}", word)
                                  and f.suffix.lower() == ".jpg"):
                                colours.append(word.upper())
                colours = sorted(set(colours)) or ["(single)"]
                # title: use the most descriptive stem (longest)
                name = title_words(max((f.stem for f in best), key=len))
                w.writerow([code, " | ".join(colours), len(best),
                            " ; ".join(str(f.relative_to(brand_dir)) for f in best), ""])
            print(f"{brand}: {len(groups)} products -> {out.name} ({len(files)} files)")

        # ── draft products CSV ────────────────────────────────────────────
        prows = []
        for code, best in sorted(groups.items()):
            name = title_words(max((f.stem for f in best), key=len))
            colours = []
            for f in best:
                m = re.match(r"^[A-Za-z0-9]+[\s_-]+(.+)$", title_words(f.stem))
                if m:
                    for word in m.group(1).split():
                        if word.lower() in COLOUR_WORDS:
                            colours.append(word.title())
                        elif (brand == "capezio"
                              and re.fullmatch(r"[A-Z]{2,3}", word)
                              and f.suffix.lower() == ".jpg"):
                            colours.append(word.upper())
            colours_j = "|".join(sorted(set(colours)))
            title_en = name
            title_el = greek_title(name, brand)
            fabric = fabric_from(name)
            desc_en = f"{name}. Colours: {colours_j.replace('|', ', ')}." if colours_j else f"{name}."
            desc_el = (f"{title_el}. Χρώματα: {colours_j.replace('|', ', ')}." if colours_j
                       else f"{title_el}.")
            prows.append({
                "sku": code, "title_en": title_en, "description_en": desc_en,
                "title_el": title_el, "description_el": desc_el,
                "price": "", "sizes": "", "colours": colours_j, "fabric": fabric,
            })
        pout = ROOT / f"products.{brand}.csv"
        with open(pout, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[
                "sku", "title_en", "description_en", "title_el", "description_el",
                "price", "sizes", "colours", "fabric", "short_desc_en", "short_desc_el"])
            w.writeheader()
            w.writerows(prows)
        print(f"  draft CSV: {pout.name} ({len(prows)} rows)")
        n_total += len(groups)
    print(f"total products (grishko+capezio): {n_total}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
