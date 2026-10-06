# VirtueMart Product Importer
A production-proven Python CLI that bulk-imports products from CSV files **directly into the
MariaDB database** of a live Joomla 5 + VirtueMart 4 shop - no Joomla extension, no HTTP API,
no third-party migration tool. Built for a real deployment (libertidance.com, shared hosting
with FTP-only access) where it has imported **267 products and 429 photos across five batches
with zero failed products and zero database errors**.
**Safe by default.** Without an explicit `--import` flag nothing is ever written. `--dry-run`
prints the exact per-product plan - every INSERT it would execute - for human review before
anything touches the live database.
```
python importer.py products.csv --dry-run        # plan only, zero writes
python importer.py products.csv --import         # writes, after typed confirmation
python importer.py products.csv --validate-only  # CSV + image checks, no database
```
---
## Why it exists
The shop had to go live with ~700 products from four supplier catalogues (Dance You, Dux,
Go Dance, plus Capezio/Grishko), but the constraints were unusual:
- **No SSH access.** Shared hosting (HestiaCP) allows FTP uploads and one-shot cron jobs only.
- **No import tooling.** No CSVI, no REST API, no SSH for migrations.
- **Live shop.** An existing database (Capezio product codes) must never be damaged:
  existing products are never updated or deleted, only new SKUs are created.
- **Bilingual shop** (Greek/English): every product needs both language rows, matched slugs
  and no broken characters.
- **Non-technical operator.** The whole workflow must be executable by one person via
  FileZilla and the hosting panel, with hard safety gates against mistakes.
So the importer talks to the database directly, replicating VirtueMart's exact schema
conventions - which were first **reverse-engineered from a database dump** and documented in
[`docs/virtuemart-database-analysis.md`](docs/virtuemart-database-analysis.md).
## Results in production
| Batch | Date | CSV rows | Created | Skipped (already in shop) | Photos copied |
|---|---|---|---|---|---|
| Test (2 capezio SKUs) | Sep 21 | 2 | 2 | 0 | 2 |
| 1 - Dance You catalogue | Sep 22 | 90 | 51 | 39 | 88 |
| 2 - Dance You apparel | Sep 22 | 24 | 24 | 0 | 28 |
| 3 - Capezio / Grishko / character shoes | Sep 29 | 101 | 87 | 14 | 115 |
| 4 - Go Dance full catalogue | Oct 5 | 158 | 103 | 55 | 196 |
| **Total** | | **375** | **267** | **108** | **429** |
Zero failed products, zero database errors, zero lost data. Every product arrives
**unpublished** for manual review before going live - the shop owner stays in control.
## Architecture
```
                     laptop (dev/operator)
  -------------------------------------------------------------
  vmimporter/            the Python package (single source of truth)
  tools/sync-bundle.py   mirrors code into server-bundle/, verifies
                         byte-identical, prints the exact FTP upload list
  server-bundle/         the FTP staging area (code + vendor + scripts)
  real-images/           supplier image banks, scanned by SKU prefix
  reports/               client-facing status reports (generated)
  data/inbound/          client files: price lists, catalogues, sheets
                     deployment = FTP only
  -------------------------------------------------------------
  /home/<user>/web/<shop>/import-bundle/        (outside public_html)
     importer.py + vmimporter/ + vendor/ (pymysql, no pip needed)
     run-dry-run.sh / run-import.sh          cron entry points
     products.<batch>.csv, images/<batch>/   per-batch payload
     dryrun-out.txt / import-out.txt         review artifacts
                     execution = one-shot cron
  -------------------------------------------------------------
  1. dry-run cron  -> appends plan to dryrun-out.txt -> human review
  2. Hestia backup -> undo path
  3. import cron   -> per-product transactions -> import-out.txt
  4. cron job deleted immediately after firing
```
## The safety model (the interesting part)
Bulk-importing into a live e-commerce database is mostly a risk-management problem. Layers:
1. **Read-only by default.** Every mode except `--import` opens the DB session with
   `SET SESSION TRANSACTION READ ONLY` *and* refuses writes at application level.
2. **Explicit double gate.** `run-import.sh` (the cron entry point) refuses to run unless
   `APPROVED=YES` was edited in by hand, after a checklist: dry-run reviewed + backup exists.
3. **`--create-only`.** Rows whose SKU already exists in the shop are skipped, never updated.
   Re-running any batch is a no-op; wrong CSVs cannot damage existing products.
4. **Per-product transactions.** One `BEGIN ... COMMIT` per product; a failing product is
   reported and the import continues. No partial product is ever left behind.
5. **Dry-run output is a contract.** The plan lists every INSERT (core row, both language
   rows, price, each custom field, each media row, category links) with resolved slugs and
   net/gross prices - what you see is exactly what gets written.
6. **Never-overwrite media.** Same name + same content = reuse the existing media row;
   same name + different content = abort that product. The importer never modifies anything
   under `public_html/` except copying new image files.
7. **New products are invisible until reviewed:** `published = 0`, explicit category only
   from validated `category_id` (unknown id = hard error, nothing imports).
## What it handles
**CSV ingestion** - strict header validation, unknown column = error, all problems reported
together (never fails on the first), multi-value cells (`36|37|38`), per-row
`category_id`/`manufacturer_id` validated against the live DB, decimal-comma tolerance,
duplicate-SKU detection.
**Bilingual data** - both `products_en_gb` and `products_el_gr` rows are always written,
with a shared slug derived from the English title (`latin-shoes`), uniquified per table
(`-2`, `-3`) when taken. Greek titles flow through the same pipeline UTF-8-safe.
**VAT-correct pricing** - the CSV holds the final customer-facing price; with
`PRICE_MODE=gross` the stored net is `price / 1.24` at 6 decimals, so VirtueMart's existing
tax rule redisplays the exact CSV price. Verified end-to-end: a 56 EUR CSV price stores
45.161290 net and redisplays 56.00.
**Image pipeline** - a file belongs to the SKU that starts its filename (`0405PT Black.jpg`,
`0405 PT Orchid Mist.jpg` and `0412.jpg` all resolve; longest SKU wins). Natural sort keeps
ordering deterministic (`X 2.jpg` before `X 10.jpg`); the first image becomes the main
product image. Media rows are deduplicated by URL and reused when the file already exists on
the server; execution order per product is files-first-then-transaction, so a DB failure can
leave an orphan file (reported) but never a dangling media row.
**Operator workflow** - `tools/sync-bundle.py` guarantees the FTP upload always matches the
reviewed code (byte-identical verification + exact upload list), cron scripts carry the batch
selection, and every run appends to human-readable output files that double as the audit log.
## Testing
**81 tests, all green, no database credentials needed:**
```bash
.venv/bin/pytest tests/ -q        # 81 passed
```
- Unit: CSV parsing/validation, image matching and ordering, slug generation, price
  conversion, category/manufacturer validation.
- Integration: the full plan/execute flow runs against an in-memory sqlite replica of the
  VirtueMart tables seeded with real production reference data - CD004-shape assertions,
  idempotency (re-import = no-op), dry-run purity (zero writes), rollback behaviour,
  owned-fields-only updates, media reuse and dedup.
`DB_BACKEND=sqlite` makes the whole stack runnable against a converted dump copy locally -
the production code path is exercised without touching anything real.
## Repository map
| Path | What it is |
|---|---|
| `vmimporter/` | the importer package: `cli.py` (flags, plan/execute), `products_csv.py`, `importer.py` (plan build + SQL), `repos.py`, `images.py`, `slug.py`, `config.py`, `db.py`, `reporting.py` |
| `importer.py` | CLI launcher |
| `tests/` | 81-test suite (unit + sqlite integration) |
| `tools/` | data-prep scripts + `sync-bundle.py` (deploy verification) |
| `server-bundle/` | FTP staging area: launcher, scripts, vendored pymysql, batch CSVs |
| `docs/` | `virtuemart-database-analysis.md` (full reverse-engineering), `csv-format.md`, `pre-production-audit.md`, `project-map.md` |
| `reports/` | client-facing reports generated during the campaign |
| `data/inbound/` | client-supplied inputs: price lists, catalogue texts, translations |
| `examples/` | working sample CSV + images |
## Configuration
Everything deployment-specific lives in one screen of constants plus a `.env`:
| Variable | Purpose |
|---|---|
| `DB_HOST/PORT/NAME/USER/PASSWORD` | MariaDB credentials (localhost on the shared host) |
| `DB_BACKEND` | `mysql` (production) or `sqlite` (local rehearsal) |
| `VM_MEDIA_DIR` | absolute path of the VM product media directory |
| `VM_ADMIN_USER_ID` | Joomla user id written to `created_by`/`modified_by` |
| `PRICE_MODE` / `VM_VAT_RATE` | `net`/`gross` + VAT percent (24) |
| `IMAGES_PATH`, `LOG_DIR` | local paths |
Installation constants in `vmimporter/config.py`: table prefix, vendor id, currency id,
tax-rule id, custom-field ids (6=Size, 7=Colour, 10=Fabric). **Porting to another
Joomla+VirtueMart shop = edit these constants + fill `.env`** - the whole pipeline (CSV,
matching, dry-run, gates, media dedup) is shop-independent.
## Runbook (as used in production)
1. `python3 tools/sync-bundle.py` - sync code into `server-bundle/`, get the upload list.
2. FTP-upload CSV + batch images + scripts to `import-bundle/`.
3. One-shot cron: `run-dry-run.sh` - read-only plan appended to `dryrun-out.txt`.
4. Review every plan line; delete the cron job.
5. Hestia backup (the undo path).
6. Flip `APPROVED=YES` in `run-import.sh`, upload it.
7. One-shot cron: `run-import.sh` - per-product transactions.
8. Review `import-out.txt`; delete the cron job.
9. Verify new products in the Joomla admin; publish manually.
Every step is doable by a non-developer through FileZilla and the hosting panel, with the
safety gates making wrong moves fail loudly instead of silently.
## Stack
Python 3.11+; runtime deps: `pymysql` (vendored on the server - no pip/venv needed there) +
`python-dotenv`; `pytest` for the suite; standard library for everything else.