# Project map — what lives where, what to touch

One page. If something isn't listed here, ask before touching it.

## The importer (production code — edit carefully, always with tests)

| Path | Role |
|---|---|
| `vmimporter/` | The importer package. **Single source of truth.** `products_csv.py` (CSV parsing/validation), `importer.py` (plan building + execution), `repos.py` (all SQL), `config.py` (constants + env), `db.py` (connection, read-only enforcement), `images.py` (image discovery + SKU matching), `slug.py`, `cli.py` (arg parsing), `reporting.py` (console/summary output). |
| `importer.py` | Thin CLI launcher at repo root. |
| `tests/` | sqlite test suite. Run: `.venv/bin/pytest tests/ -q`. 81 tests. **Run after every change.** |
| `docs/virtuemart-database-analysis.md` | Reverse-engineered VM schema — the reason every SQL insert looks the way it does. |
| `docs/csv-format.md` | How to build a products CSV (plain-language). |
| `docs/pre-production-audit.md` | Safety audit before first real import. |

## Deployment to the server

| Path | Role |
|---|---|
| `server-bundle/` | FTP staging area. Upload from here to `/home/manouka/web/libertidance.com/import-bundle/`. |
| `tools/sync-bundle.py` | **Run before every upload**: copies repo code into the bundle, verifies byte-identical, prints the exact FTP list. `--check` = verify only. |
| `server-bundle/run-dry-run.sh` | One-shot cron script (read-only). |
| `server-bundle/run-import.sh` | One-shot cron script (writes; `APPROVED=YES` gate). |
| `server-bundle/vendor/` | Vendored PyMySQL (no pip on the server). Never touched. |

**The one rule:** never edit `server-bundle/vmimporter/*` by hand, and never
FTP a `vmimporter/` file to the bundle root. `sync-bundle.py` detects both mistakes.

## Working data (not code)

| Path | Role |
|---|---|
| `csv/` | Brand product CSVs in progress. `products.danceyou.csv` = generated baseline; `.catalogue-filled` / `.formula` = intermediate variants. |
| `real-images/capezio/`, `real-images/grishko/` | Image banks — importer scans these **top-level only**, one `--images` dir per run. |
| `real-images/dance-you/{1,2,3,4}/` | Same, in subfolders — run the importer once per subfolder. |
| `data/grishko/pages/` | Scraped supplier HTML (input to `tools/merge_grishko.py`). |
| `data/identified/` | Manually identified Dance You SKUs + sheet photos. |
| `data/inventory/` | Inventory review / deferred items per brand. |
| `data/catalogues/` | Supplier catalogue PDFs + extracted text. |
| `local/vm_analysis.db` | Local sqlite copy of the DB dump (tests read its *shape*, not this file directly). |
| `support_antima_.sql` | Live DB dump. **Never commit, never share.** |

## Tools (`tools/`) — one-off vs reusable

| Script | Status | What it does |
|---|---|---|
| `sync-bundle.py` | **reusable** | Bundle sync + FTP list (see above). |
| `dump2sqlite.py` | reusable | Rebuild `local/vm_analysis.db` from a fresh dump (strips PKs, see `tests/conftest.py`). |
| `brand_inventory.py` | reusable | Image-folder → `products.<brand>.csv` skeleton. |
| `dy_inventory.py` | one-off (Dance You) | Folder-specific inventory pass. |
| `dy_catalogues.py` | one-off (Dance You) | Catalogue text → code mapping (`data/catalogues/`). |
| `dy_csv.py` | one-off (Dance You) | Generates `csv/products.danceyou.csv`. |
| `apply_identified.py` | one-off (Dance You) | Applies manual identifications to the CSV. |
| `fetch_capezio.py` | one-off (Capezio) | Scrapes capezio.com pages for the CSV. |
| `fetch_grishko.py` + `merge_grishko.py` | one-off (Grishko) | Scrape + merge grishkoshop.com data. |

## Known loose ends (deliberately not done)

1. **15 BMP/GIF images** in `real-images/dance-you/{3,4}/` — importer only
   matches `.jpg/.jpeg/.png/.webp`, so these SKUs get no image until converted
   (`for f in *.bmp; do magick "$f" "${f%.*}.jpg"; done` — needs ImageMagick).
2. **Duplicate media rows on the server** for `102 Glisse.jpg` / `1130 Airess.jpg`
   (old + new import). Harmless; importer now reuses rows, so no new ones appear.
   Optional cleanup query exists on request (backup first).
3. **Colour code contradictions** — waiting on supplier/dev answers, per project decision.
4. **Test products 499/500** (`102`, `1130`) live in the shop, unpublished,
   category Ballet, no manufacturer. Keep or delete in admin; create-only skips them.
