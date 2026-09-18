#!/usr/bin/env python3
"""Generate products.danceyou.csv from inventory-review.csv + catalogue-data.csv.

Rules (operator-approved):
  - price = manufacturer's catalogue price (PRICE_MODE=gross on import → customer
    pays exactly that). Rows without catalogue price leave the cell empty
    (validation will flag them until filled).
  - title_en = "{EN type} {code}" (catalogue name preferred)
  - title_el = "{GR type} {code}" (mechanical translation of the type)
  - colours = catalogue "Colors :" else filename colours
  - sizes = numeric EU ranges expanded (35 - 42 -> 35|36|...|42);
    size codes (SC,MC,LC,XLC / SA,MA... / Small, Intermediate...) kept as words
  - fabric from name keywords (Satin/Canvas/Leather/Mesh/Velvet/Lycra/Cotton/Microfibre)
  - Go Dance Latin shoes follow the existing shop naming family:
    "Godance Latin Shoes <colour-desc> <code>" / "Υπόδημα Λάτιν <desc> <code>"

Usage: python3 tools/dy_csv.py
Output: products.danceyou.csv
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DY = ROOT / "real-images" / "dance you"

# ── translation dictionaries ─────────────────────────────────────────────────
TYPE_EL = [
    ("Camisole Tutu Dress", "Φόρεμα με τουτού"),
    ("Empire Dress", "Φόρεμα Empire"),
    ("Tutu Dress", "Φόρεμα με τουτού"),
    ("Flutter Sleeve Leotard", "Λεοκάρδα με αέρινα μανίκια"),
    ("Short Sleeve Leotard", "Λεοκάρδα με κοντά μανίκια"),
    ("3/4 Sleeve Leotard", "Λεοκάρδα με 3/4 μανίκια"),
    ("Long Sleeve Leotard", "Λεοκάρδα με μακριά μανίκια"),
    ("Long Sleeve", "Λεοκάρδα με μακριά μανίκια"),
    ("Cap Sleeve Leotard", "Λεοκάρδα με κοντά μανίκια"),
    ("Camisole Leotard", "Λεοκάρδα με λάστιχα"),
    ("Tank Leotard", "Λεοκάρδα ολομέτωπη"),
    ("Leotard", "Λεοκάρδα"),
    ("Camisole Tutu Dress", "Φόρεμα με τουτού"),
    ("Wrap Around Chiffon Skirt", "Περαστή φούστα σιφόν"),
    ("Pull On Crossover Skirt", "Φούστα crossover"),
    ("Character Skirt", "Φούστα Χαρακτήρων"),
    ("Character Shoe", "Παπούτσια Character"),
    ("Wrap Around Skirt", "Περαστή φούστα"),
    ("Crossover Skirt", "Φούστα crossover"),
    ("Chiffon Skirt", "Φούστα σιφόν"),
    ("Skirt", "Φούστα"),
    ("Flyknit Jazz Sneakers", "Sneakers Τζαζ"),
    ("Jazz Sneakers", "Sneakers Τζαζ"),
    ("Jazz Shoes", "Παπούτσια Τζαζ"),
    ("Sneakers", "Sneakers"),
    ("Greek Sandals", "Σανδάλια δασκάλας"),
    ("Sandals", "Σανδάλια"),
    ("Latin Shoes", "Υπόδημα Λάτιν"),
    ("Ballet Full Sole", "Παπούτσια Μπαλέτου"),
    ("Rhythmic Half Shoe", "Μισοπαπούτσια Ρυθμικής"),
    ("Half Shoe", "Μισοπαπούτσια"),
    ("Power Mesh Layer Top", "Τοπ δίχτυ"),
    ("Layer Top", "Τοπ"),
    ("Hot Shorts", "Σορτς"),
    ("Hot Short", "Σορτς"),
    ("Dance Bra", "Σουτιέν χορού"),
    ("Dance Brief", "Σλιπ χορού"),
    ("Camisole", "Λεοκάρδα με λάστιχα"),
    ("Dress", "Φόρεμα"),
]
QUALIFIER_EL = [
    ("w/Flower embroidery", "με κέντημα λουλουδιών"),
    ("w/strauss", "με strass"),
    ("w/strass", "με strass"),
    ("w/strauss", "με strass"),
    ("w/lace", "με δαντέλα"),
    ("w/skirt", "με φούστα"),
    ("w/lining", "με φόδρα"),
    ("w/mesh", "με δίχτυ"),
    ("w/T-Strap", "με λουράκι T"),
    ("Girls’", "Κοριτσιών"),
    ("Girls'", "Κοριτσιών"),
    ("Women’s", "Γυναικείων"),
    ("Women'", "Γυναικείων"),
]
COLOUR_EL = {
    "black": "Μαύρο", "brown": "Καφέ", "blue": "Μπλε", "silver": "Ασημένιο",
    "coffee": "Καφέ", "bronze": "Μπρονζέ", "toffee": "Καραμέλα", "skin": "Δέρμα",
    "white": "Λευκό", "pink": "Ροζ", "red": "Κόκκινο", "purple": "Μοβ",
    "lavender": "Λεβάντα", "burgundy": "Μπορντό", "grey": "Γκρι", "gray": "Γκρι",
    "sky blue": "Γαλάζιο", "royal blue": "Βασιλικό μπλε", "marine blue": "Μαριν",
    "gold": "Χρυσό", "green": "Πράσινο", "mint": "Μίντ", "navy": "Μπλε navy",
    "ivory": "Ιβουάρ", "tan": "Ταν", "arctic blue": "Παγωμένο μπλε",
    "coral pink": "Κοράλ", "salmon pink": "Σομόν", "dandelion": "Πικαφλού(? )",
    "pea green": "Πρασίνη", "flamingo": "Φλαμίνγκο", "avocado": "Αβοκάντο",
    "amethyst": "Αμέθυστος", "lila": "Λιλά", "lilac": "Λιλά", "jade green": "Γιαντ",
    "light yellow": "Ανοιχτό κίτρινο", "dusty rose": "Παλ ροζ", "dusty pink": "Σκον ροζ",
    "mauve lotus": "Μωβ λωτός", "jade": "Γιαντ", "lime green": "Λαχανί",
    "ice blue": "Πάγος", "hot pink": "Φούξια", "lake blue": "Λίμνη μπλε",
    "rose purple": "Ροζ μοβ", "petrol": "Πετρόλ", "sunset red": "Κόκκινο sunset",
    "sunset red": "Κόκκινο sunset", "mirtillo": "Μυρτιλo", "laguna": "Λαγούνα",
    "orchid mist": "Ορχιδέα", "ice blue": "Πάγος μπλε", "bordeaux": "Μπορντό",
    "grey pink": "Γκρι ροζ", "misty blue": "Ομιχλώδες μπλε", "dusty pink": "Σκονισμένο ροζ",
    "grey pink": "Γκρι ροζ", "mirtillo": "Μύρτιλλο", "suntan": "Σντούν",
    "light toast": "Ανοιχτό ταν", "toast": "Ταν",
}
FABRIC_HINTS = [
    ("satin", "Satin"), ("leatheroid", "Leatheroid"), ("leather", "Leather"),
    ("canvas", "Canvas"), ("mesh", "Mesh"), ("velvet", "Velvet"),
    ("velour", "Velour"), ("lycra", "Lycra"), ("cotton", "Cotton"),
    ("microfibre", "Microfibre"), ("flyknit", "Flyknit"), ("patent", "Patent"),
    ("chiffon", "Chiffon"), ("power mesh", "Power Mesh"),
]


def greek_type(name: str) -> str:
    """Translate the garment type part of an EN catalogue name."""
    low = name.lower()
    for en, el in TYPE_EL:
        if en.lower() in low:
            return el
    # generic word fallbacks
    if "leotard" in low:
        return "Λεοκάρδα"
    if "skirt" in low:
        return "Φούστα"
    if "dress" in low:
        return "Φόρεμα"
    if "sandal" in low:
        return "Σανδάλια"
    if "shoe" in low or "pointe" in low:
        return "Παπούτσια"
    return ""


def translate_colour_desc(desc: str) -> str:
    """'Black Leatheroid w/strauss' -> 'Μαύρο Δερματίνη με strass' (word map)."""
    WORDS = {
        "black": "Μαύρο", "brown": "Καφέ", "blue": "Μπλε", "silver": "Ασημένιο",
        "coffee": "Καφέ", "bronze": "Μπρονζέ", "toffee": "Καραμέλα",
        "skin": "Δέρμα", "girls’": "Κοριτσιών", "girls'": "Κοριτσιών",
        "satin": "Σατέν", "leatheroid": "Δερματίνη", "leather": "Δερμάτινο",
        "patent": "Βερνίκι", "mesh": "Δίχτυ", "velvet": "Βελούδο",
        "canvas": "Καμβάς", "microfibre": "Μικροΐνα", "suede": "Σουέτ",
        "w/strauss": "με strass", "w/strass": "με strass", "w/mesh": "με δίχτυ",
        "w/t-strap": "με λουράκι T", "w/lace": "με δαντέλα", "w/skirt": "με φούστα",
        "w/lining": "με φόδρα", "t-strap": "λουράκι T", "strauss": "strass",
        "with": "με", "girls": "Κοριτσιών", "toffee": "Καραμέλα",
        "hunter": "Χάντερ", "green": "Πράσινο", "lavender": "Λεβάντα",
        "nude": "Δέρμα", "grey": "Γκρι", "pink": "Ροζ", "red": "Κόκκινο",
        "purplish": "Μοβ", "royal": "Βασιλικό", "sky": "Γαλάζιο", "blue": "Μπλε",
    }
    out = []
    for tok in re.split(r"(\s+|/)", desc):
        low = tok.lower().strip()
        if low in WORDS:
            out.append(WORDS[low])
        else:
            out.append(tok)
    return "".join(out).strip()


def expand_sizes(sizes_text: str) -> str:
    if not sizes_text:
        return ""
    t = sizes_text.strip()
    # numeric range: "35 - 42" or "36 - 43"
    m = re.match(r"^(\d{2})\s*-\s*(\d{2})$", t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= hi and hi - lo <= 25:
            return "|".join(str(n) for n in range(lo, hi + 1))
        return t
    # list with commas -> pipe
    if "," in t:
        return "|".join(p.strip() for p in t.split(",") if p.strip())
    return t


def main() -> int:
    inv = list(csv.DictReader(open(DY / "inventory-review.csv")))
    cat: dict[str, dict] = {}
    for r in csv.DictReader(open(DY / "catalogues/catalogue-data.csv")):
        cat.setdefault(r["code"].upper(), r)

    out_rows = []
    skipped_colours_index = []
    for row in inv:
        code = row["code"].strip()
        norm = code.upper().replace(" ", "")
        cat_row = None
        for attempt in (norm, norm.rstrip("2"), norm[:-1] if len(norm) > 3 else norm):
            if attempt in cat:
                cat_row = cat[attempt]
                break

        # ── title ────────────────────────────────────────────────────────────
        folder = row["folder"]
        if folder == "3" and re.match(r"^\d{4,6}|^7\d{3}[A-Z]{2}|^CD\d{3}", code):
            # Go Dance Latin shoe family — follow existing shop naming
            desc = row["colours"] if row["colours"] != "(single)" else ""
            if not desc and cat_row:
                desc = cat_row["name"]
            colour_desc = cat_row["name"] if (cat_row and cat_row["name"] and
                                              not re.search(r"(Leotard|Skirt|Dress|Shoe|Sandal|Short|Top|Bag)", cat_row["name"], re.I)) else desc
            title_en = f"Godance Latin Shoes {colour_desc} {code}".strip() if colour_desc else f"Godance Latin Shoes {code}"
            title_el = f"Υπόδημα Λάτιν {translate_colour_desc(colour_desc or '')} {code}".replace("  ", " ").strip()
        else:
            name = (cat_row["name"] if cat_row else code)
            title_en = f"{name} {code}".strip() if name != code else code
            gt = greek_type(name or "")
            qual = ""
            # keep EN qualifiers translated in parens if any matched word known
            title_el = f"{gt or 'Dance You'} {code}".strip()

        # ── colours ───────────────────────────────────────────────────────────
        colours = ""
        if cat_row and cat_row["colours"]:
            colours = "|".join(c.strip() for c in cat_row["colours"].split(",") if c.strip())
        elif row["colours"] not in ("(single)", ""):
            colours = row["colours"].replace(" | ", "|")
            # drop colour-index pseudo names
            colours = "|".join(
                c for c in colours.split("|")
                if not re.match(r"^Colour-[A-Z]", c, re.I)
            ) or ""

        # ── sizes ─────────────────────────────────────────────────────────────
        sizes_src = (cat_row["sizes"] if cat_row else "")
        sizes = expand_sizes(sizes_text=re.sub(r"^Sizes?\s*:\s*", "", sizes_src or "", flags=re.I))

        # ── price ────────────────────────────────────────────────────────────
        price = (cat_row["price"] if cat_row else "") or (cat_row["reduced_price"] if cat_row else "")

        # ── fabric ───────────────────────────────────────────────────────────
        hay = ((cat_row["name"] if cat_row else "") + " " + row["colours"]).lower()
        fabric = next((f for kw, f in FABRIC_HINTS if kw in hay), "")

        # ── description drafts ───────────────────────────────────────────────
        name_en = (cat_row["name"] if cat_row else title_en)
        bits_en = [name_en]
        bits_el = [title_el]
        desc_en = f"{name_en}. " if name_en else ""
        desc_el = f"{title_el}. " if title_el else ""
        if row["colours"] not in ("(single)", ""):
            desc_en += f"Colours: {row['colours'].replace(' | ', ', ')}. "
            desc_el += f"Χρώματα: {translate_colour_desc(row['colours'].replace(' | ', ', '))}. "
        if cat_row and cat_row["heel"]:
            desc_en += f"Heel: {cat_row['heel']}. "
            desc_el += f"Τακούνι: {cat_row['heel']}. "
        if sizes:
            desc_en += f"Sizes: {sizes}. "
            desc_el += f"Μέγέθη: {sizes}. "

        out_rows.append({
            "sku": code,
            "title_en": title_en,
            "description_en": desc_en.strip(),
            "title_el": title_el,
            "description_el": desc_el.strip(),
            "price": price,
            "sizes": sizes,
            "colours": colours,
            "fabric": fabric,
        })

    out = ROOT / "products.danceyou.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "sku", "title_en", "description_en", "title_el", "description_el",
            "price", "sizes", "colours", "fabric", "short_desc_en", "short_desc_el",
        ])
        w.writeheader()
        w.writerows(out_rows)
    priced = sum(1 for r in out_rows if r["price"])
    print(f"products.danceyou.csv: {len(out_rows)} rows ({priced} with catalogue price) -> {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
