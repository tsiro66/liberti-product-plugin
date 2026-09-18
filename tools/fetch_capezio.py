#!/usr/bin/env python3
"""Fetch official product data from capezio.com per style code.

For each code from products.capezio.csv:
  1. GET https://www.capezio.com/search?q=CODE  -> product slugs
  2. GET each /products/<slug> page (cached) -> JSON-LD Product:
     name ("Hanami® Canvas Ballet Shoe - Child | Light Pink"),
     description (official marketing copy), offers (sku -> sizes, price)
  3. Aggregate per style code: official name, description, colours (from names),
     sizes (from offer sku suffixes), price (USD retail — reference only)

Politeness: 0.35s sleep, pages cached under data/capezio/ so re-runs are offline.

Output:
  data/capezio/official-data.csv (code, official_name, description, colours, sizes, price, sources)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "capezio"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

DESCRIPTION_LIMIT_SENTENCES = 6


def http_get(url: str) -> str:
    # urllib gets soft-blocked by Capezio's CDN (served a wrong product page);
    # curl with browser-ish headers works reliably
    import subprocess
    r = subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A",
         "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
         "-H", "Accept-Language: en-US,en;q=0.9", url],
        capture_output=True, timeout=40)
    body = r.stdout.decode("utf-8", errors="replace")
    if r.returncode != 0 or len(body) < 500:
        raise RuntimeError(f"curl failed rc={r.returncode} len={len(body)}")
    return body


def cached_get(url: str, cache_key: str) -> str:
    cache = Path(CACHE := ROOT / "data" / "capezio" / "pages" / f"{cache_key}.html")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 500:
        return cache.read_text(encoding="utf-8", errors="replace")
    html = http_get(url)
    cache.write_text(html)
    time.sleep(0.55)
    return html


def search_slugs(code: str) -> list[str]:
    q = urllib.parse.quote(code)
    try:
        html = cached_get(f"https://www.capezio.com/search?q={q}", f"search_{norm(code)}")
    except Exception as e:
        print(f"  search fail {code}: {e}", file=sys.stderr)
        return []
    slugs = []
    for m in re.finditer(r'href="/products/([a-z0-9-]{8,})', html):
        slug = m.group(1)
        if slug not in slugs:
            slugs.append(slug)
    return slugs[:8]


def norm(code: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", code.upper()).strip("-")


def extract_ld(html: str, slug: str = "") -> dict | None:
    """Pick the Product LD block matching the requested slug (pages may embed
    recommendation LDs for other products)."""
    candidates = []
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        if j.get("@type") != "Product":
            continue
        url = (j.get("url") or "")
        if slug and url.rstrip("/").endswith(f"/products/{slug}"):
            return j
        candidates.append(j)
    # fall back: the block with the longest description is the real page product
    return max(candidates, key=lambda j: len(j.get("description") or ""), default=None)


def strip_tags(html: str) -> str:
    t = re.sub(r"<br\s*/?>", ". ", html, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;|&#174;|®", "®", t)
    t = re.sub(r"\s+", " ", t)
    # keep the first N sentences
    parts = re.split(r"(?<=[.!?])\s+", t.strip())
    return " ".join(parts[:DESCRIPTION_LIMIT_SENTENCES]).replace("Watch your favorite dancer glide effortlessly across the dance floor in ", "").strip()


def fetch_product_page(slug: str) -> dict:
    key = norm(slug)
    try:
        html = cached_get(f"https://www.capezio.com/products/{slug}", f"p_{key}")
    except Exception as e:
        print(f"  product fail {slug}: {e}", file=sys.stderr)
        return {}
    ld = extract_ld(html, slug)
    if not ld:
        return {}
    meta = re.search(r"Style\s*#:\s*([A-Z0-9]+)", html, re.I)
    style = meta.group(1) if meta else (ld.get("sku") or slug)
    name = ld.get("name", "")
    desc = strip_tags(ld.get("description", "") or "")
    colours = set()
    sizes = set()
    price = ""
    offers = ld.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    for o in offers:
        sku = o.get("sku", "")
        price = o.get("price") or price
        # suffix after style + colour = size (e.g. 2037C-LPK8N -> 8N)
        rest = re.sub(rf"^{re.escape(style.upper())}[-_]?", "", sku, flags=re.I) if style else sku
        sizes.add(rest)
    if name and "|" in name:
        style_name, colour = name.split("|", 1)
        colours.add(colour.strip())
    else:
        style_name = name
    return {"style": style, "style_name": style_name.strip(),
            "description": desc, "colours": colours, "sizes": sizes,
            "price": price, "url": ld.get("url", "")}


def main() -> int:
    csv_path = ROOT / "products.capezio.csv"
    codes = sorted({r["sku"].upper() for r in csv.DictReader(open(csv_path))})
    print(f"fetching official data for {len(codes)} Capezio codes (cached)...")
    styles: dict[str, dict] = defaultdict(lambda: {
        "names": set(), "descriptions": set(), "colours": set(),
        "sizes": set(), "prices": set(), "urls": set(), "fetched": False})

    # name map for fallback searches
    names = {}
    for r in csv.DictReader(open(csv_path)):
        names[r["sku"].upper()] = r["title_en"]

    style_rows: dict[str, dict] = {}

    for i, code in enumerate(codes):
        print(f"[{i+1}/{len(codes)}] {code}")
        queries = [code]
        t = (names.get(code) or "").replace(code, "").strip()
        if t:
            for word in re.split(r"[-\s]+", t):
                if len(word) >= 4 and word.lower() not in {
                        "ballet", "shoe", "leotard", "tight", "dress", "with",
                        "black", "pink", "blue", "caramel", "grey", "purple",
                        "white", "nude", "suntan", "toast", "coffee", "violet",
                        "hunter", "green", "purple", "blue", "pink", "black",
                        "canvas", "leather", "satin"}:
                    queries.append(word)
        slugs = []
        for q in queries:
            try:
                html = cached_get(f"https://www.capezio.com/search?q={urllib.parse.quote(q)}",
                                  f"search_{norm(q)}")
            except Exception as e:
                print(f"  search fail: {e}", file=sys.stderr)
                continue
            new = []
            for m in re.finditer(r'href="/products/([a-z0-9-]{8,})', html):
                slug = m.group(1)
                if slug not in slugs and slug not in new:
                    # prefer slugs that mention the query term
                    rank = 0 if (len(q) >= 4 and q.lower() in slug) else 1
                    new.append((rank, slug))
            for _rank, slug in sorted(new)[:6]:
                slugs.append(slug)
            if len(slugs) >= 3:
                break
        slugs = slugs[:6]
        if not slugs:
            print(f"  no products found for {code}")
            continue
        for slug in slugs[:6]:
            rec = fetch_product_page(slug)
            if not rec or not rec.get("style"):
                continue
            style_rows.setdefault(rec["style"], {
                "style_name": rec["style_name"], "description": rec["description"],
                "colours": set(), "sizes": set(), "prices": set(), "urls": set()})
            sr = style_rows[rec["style"]]
            sr["urls"].add(rec["url"])
            if rec["description"]:
                sr["description"] = rec["description"] if not sr["description"] else sr["description"]
            sr["colours"] |= rec["colours"]
            sr["sizes"] |= rec["sizes"]
            if rec["price"]:
                sr["prices"].add(str(rec["price"]))

    out = ROOT / "data" / "capezio" / "official-data.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "official_name", "description", "colours", "sizes", "price", "urls"])
        for style, sr in sorted(style_rows.items()):
            # official_name = slug title-case minus colour tail
            slug = sorted(sr["urls"])[0].rsplit("/", 1)[-1] if sr["urls"] else ""
            base_slug = re.sub(r"-(child|adult|women|men)(-[a-z-]+)?$", "", slug)
            official_name = " ".join(w.capitalize() for w in base_slug.split("-") if w)
            w.writerow([style, official_name, sr["description"],
                        " | ".join(sorted(sr["colours"])),
                        "|".join(sorted(sr["sizes"], key=lambda s: (len(s), s))),
                        " ; ".join(sorted(sr["prices"])),
                        " ; ".join(sorted(sr["urls"]))[:600]])
    print(f"official-data.csv: {len(style_rows)} styles -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
