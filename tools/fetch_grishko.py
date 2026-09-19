#!/usr/bin/env python3
"""Fetch official Grishko product data from grishkoshop.com (B2B shop).

  1. Crawl category pages (NextCategory P-codes, paginated ?page=N)
  2. Collect /Product/en-US/<CODE>/<slug> URLs
  3. Fetch each product page (cached):
       - article code from URL
       - title from <h1> ("0501 Fouette, with drawstring")
       - description (real copy)
       - price in USD *including VAT* (gross)
       - colours/sizes when present
  4. Output data/grishko/official-data.csv

Politeness: 0.4s sleep between fresh fetches; everything cached offline.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "grishko" / "pages"
OUT = ROOT / "data" / "grishko" / "official-data.csv"

CATEGORIES = [
    "P150/pointe-shoes", "P151/soft-ballet-shoes", "P152/lyrical-shoes",
    "P153/jazz-shoes", "P154/warm-up-booties", "P156/ballroom-latin",
    "P158/ballet-boots", "P162/tap-shoes", "P163/folk-character-shoes",
    "P181/pointe-shoe-accessories", "P182/bags-cases", "P183/hair-accessories",
    "P184/gifts", "P191/leotards", "P192/unitards", "P193/skirts-tutus",
    "P194/t-shirts-jumpers", "P195/leggings", "P196/pants-and-shorts",
    "P197/tights", "P199/heat-retention-wear-with-sauna-effect",
    "P207/bolshoi-stars-jewel", "P208/kids-dancewear",
    "P212/knitted-warm-up", "P230/bolshoi-stars-the-dream",
    "P231/kids-ballet-shoes", "P237/dance-accessories",
    "P238/kids-stage-costumes",
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


def http_get(url: str) -> str:
    r = subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A", UA,
         "-H", "Accept-Language: en-US,en;q=0.9", url],
        capture_output=True, timeout=40)
    body = r.stdout.decode("utf-8", errors="replace")
    if r.returncode != 0 or len(body) < 500:
        raise RuntimeError(f"curl rc={r.returncode} len={len(body)}")
    return body


def cached_get(url: str, cache_key: str) -> str:
    cache = Path(CACHE) / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', cache_key)[:120]}.html"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 500:
        return cache.read_text(encoding="utf-8", errors="replace")
    body = http_get(url)
    cache.write_text(body)
    time.sleep(0.4)
    return body


def strip_tags(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def main() -> int:
    product_urls: set[str] = set()
    for cat in CATEGORIES:
        page = 1
        while True:
            url = (f"https://grishkoshop.com/NextCategory/en-US/{cat}"
                   if page == 1 else
                   f"https://grishkoshop.com/NextCategory/en-US/{cat}/&page={page}")
            try:
                html = cached_get(url, f"cat_{cat.split('/')[0]}_{page}")
            except Exception as e:
                print(f"  category fail {cat} p{page}: {e}", file=sys.stderr)
                break
            found = re.findall(r'href="(/Product/en-US/[^"]+)"', html)
            new = {f"https://grishkoshop.com{u}" for u in found}
            before = len(product_urls)
            product_urls |= new
            print(f"  {cat} p{page}: +{len(new)} (total {len(product_urls)})")
            if not new and page > 1:
                break
            if not new:
                break
            page += 1
            if page > 30:
                break

    print(f"unique products: {len(product_urls)}")

    rows = []
    for i, url in enumerate(sorted(product_urls)):
        m = re.match(r"https://grishkoshop\.com/Product/en-US/([^/]+)/([^/]+)/?", url)
        if not m:
            continue
        code, slug = m.group(1), m.group(2)
        try:
            html = cached_get(url, f"p_{code}")
        except Exception as e:
            print(f"  product fail {code}: {e}", file=sys.stderr)
            continue
        title = re.findall(r"<title>([^<]*)</title>", html)
        name = ""
        if title:
            name = re.sub(r"\|\s*Grishko.*$", "", title[0].strip())
            name = re.sub(r"\s+", " ", name).strip()
        h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        prod_name = strip_tags(h1[0]) if h1 else name
        # description = real copy block (class description div second part)
        description = ""
        dm = re.search(r'class="[^"]*product-description[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if dm:
            description = strip_tags(dm.group(1))
        else:
            dm2 = re.search(r"The model has.*?(?:SIZE CHART|<|$)", html, re.S)
            if dm2:
                description = strip_tags(dm2.group(0))
        description = description[:800]
        prices = re.findall(r'class="price">\s*([\d.,]+)\s*</span>\s*<span class="dph">\s*(USD|CZK|EUR)', html)
        price = prices[0][0] if prices else ""
        currency = prices[0][1] if prices else ""
        rows.append({"code": code, "slug": slug, "name": prod_name,
                     "description": description, "price": price, "currency": currency,
                     "url": url})

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "description", "price", "currency", "url"])
        for r in rows:
            w.writerow([r["code"], r["name"], r["description"], r["price"],
                        r["currency"], r["url"]])
    print(f"official-data.csv: {len(rows)} products -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
