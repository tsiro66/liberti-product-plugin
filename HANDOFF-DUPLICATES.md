# Session handoff: duplicate check + product-by-product corrections

Read this first. It carries the verified context from the previous session so nothing
needs to be re-derived.

## Where we are

The importer (this repo) has run 5 batches against the live shop
(libertidance.com, Joomla 5.4.8 + VirtueMart 4.8.0, HestiaCP shared hosting, FTP +
one-shot cron only):

| Batch | Date | Created | Skipped | Photos |
|---|---|---|---|---|
| test (102, 1130) | Sep 21 | 2 unique (imported twice; duplicate records deleted in admin later) | 0 | 2 |
| 1 danceyou-1 | Sep 22 | 51 (IDs 501-551) | 39 | 88 |
| 2 danceyou-2 | Sep 22 | 24 (IDs 552-575) | 0 | 28 |
| 3 capezio-grishko | Sep 29 | 87 (IDs 576-662) | 14 | 115 |
| 4 godance | Oct 5 | 103 (IDs 663-765) | 55 | 196 |

Total: 267 products created by the importer (264 unique after test cleanup),
429 photos copied into public_html/images/stories/virtuemart/product/.
All products imported UNPUBLISHED (published=0).

The "skipped" rows were SKUs that already existed in the shop and were left untouched
by --create-only: 39 (batch 1) + 14 (batch 3) + 55 (batch 4) = 108 skips. IMPORTANT:
the DB backup file in the repo (support_antima_.sql) is OUTDATED - the client has
modified the shop since (they deleted the test products, and appear to have imported
products themselves - 55 Go Dance SKUs already existed on Oct 5 that are not in the
old dump).

## New problem (this session)

The client reports DUPLICATES in the shop. Unknown cause. Two hypotheses:

1. Products already existed on the site with a SIMILAR sku or name (e.g. an old
   Capezio product "B203" vs our "B203 Technique Backpack"), so ours duplicated them
   visually even though the SKU was new.
2. Our importer created genuine duplicates (e.g. the double test import on Sep 21
   created 102/1130 twice - those duplicates were deleted by the client, but there
   may be others we do not know about).
3. Also possible: the client's own imports (they had inventory.xlsx with 1,520 rows,
   retail prices and stock - they may have imported products themselves via admin).

## Plan for this session

1. BACKUP. Ask the user to create a fresh DB backup in HestiaCP (BACKUP tab) and
   download it to the project root as support_new.sql (or similar). NOT into git
   (it is git-ignored via support_antima_.sql pattern - add the new name to
   .gitignore or overwrite the old file).

2. CONVERT. Run: python3 tools/dump2sqlite.py local/vm_analysis_new.db
   (the tool converts the SQL dump into sqlite; local/*.db is git-ignored).

3. EXTRACT. Produce a review CSV of everything the importer created - all products
   with virtuemart_product_id in 497..765 (the id ranges of our batches), with:
   id, sku (product_gtin), EN title, EL title, slug, net price, published flag,
   created_on, category ids, media file urls. Save as reports/created-products.csv.
   SQL: join xhngw_virtuemart_products (p), _en_gb (en), _el_gr (el),
   _product_prices (pr, shoppergroup 0), _product_categories (pc), _product_medias
   (pm) + _medias (m). Known schema details are in docs/virtuemart-database-analysis.md.

4. DUPLICATE HUNT. Three checks on the NEW dump:
   a. exact-duplicate SKUs: same product_gtin/product_sku on more than one product id
      (catches importer double-imports and client imports).
   b. duplicate slugs across _en_gb / _el_gr (url collisions, both languages).
   c. near-duplicate NAMES: same normalized EN title (case/punctuation-insensitive)
      and also fuzzy pairs (difflib ratio > 0.92) among ALL shop products (not only
      ours) - this catches "already existed with a similar name" cases. Include the
      old Capezio products in the comparison (their names are Greek in _el_gr and
      English in _en_gb).
   For each duplicate pair, report: both product ids, skus, titles, created_on dates,
   published flags. created_on tells us who made it: our imports write
   created_by = VM_ADMIN_USER_ID (119) and created_on = import date; the client's
   manual products will have different dates/users.

5. CLASSIFY + REPORT. Write reports/duplicates-analysis.md: for each pair, verdict
   (our fault / pre-existing / client import) and recommended action (delete one,
   unpublish, merge, keep both). DO NOT change anything in the shop - the importer
   never updates or deletes; corrections in the admin are done BY THE CLIENT, or
   discussed first.

6. CORRECTION LIST. The user also wants to review products one by one for content
   mistakes (typos, wrong prices, wrong categories, wrong sizes). Produce
   reports/created-products.csv (step 3) as their checklist; they mark corrections;
   changes then go to the CLIENT's admin hands or - if a future importer feature is
   requested - a new "update mode" would be needed (currently only --create-only
   exists; updates were never enabled in production).

## Hard rules (non-negotiable, from the campaign)

- The live DB is only ever written by the importer with explicit approval gates.
  Never guide the user to run anything against the live DB without the gate ritual
  (dry-run reviewed + backup exists + explicit phrase "the dry-run is reviewed,
  backup exists, proceed").
- --create-only is the production mode. Existing products are NEVER updated or deleted.
- No manual writes to public_html except what the importer itself copies.
- The user is non-technical: one step at a time, plain language, wait for confirmation
  between steps. ASCII only in chat (their terminal setup).
- Prices: CSV price = final VAT-inclusive retail (importer divides by 1.24 with
  PRICE_MODE=gross). Retail = wholesale x 2.24 rounded up.

## Repo layout (current)

- vmimporter/ = the importer package; importer.py = CLI launcher
- server-bundle/ = FTP staging (mirror of server /home/manouka/web/libertidance.com/import-bundle/)
- staging/ = local batch payloads mirror (staging/images/<batch>/)
- real-images/ = supplier image banks (git-ignored), scanned recursively
- reports/ = client-facing reports generated so far
- data/inbound/ = client source files (go-dance-prices.txt = the 2026 wholesale price
  list with discount columns; inventory.xlsx = client's full stock list 1,520 rows
  with retail prices; elegmenoi_...xlsx = client's corrected Greek titles for batch 4)
- data/catalogues-text/ = 4 supplier catalogues (cat-3 Go Dance has NO prices)
- tests/ = 81 tests (sqlite-based, run: .venv/bin/pytest tests/ -q)
- tools/sync-bundle.py = deploy verification; tools/dump2sqlite.py = dump converter

## Operational conventions

- Batch CSVs: products.<batch>.csv at bundle ROOT; images in images/<batch>/ (flat,
  one folder per batch; importer is NOT recursive).
- Filenames start with the SKU; natural sort; first = main image.
- Batch names so far: danceyou-1, danceyou-2, capezio-grishko, godance.
- Run scripts: run-dry-run.sh / run-import.sh (CSV_FILE= and IMAGES_DIR= point at the
  current batch; APPROVED gate inside run-import.sh, currently APPROVED=NO).
- After every import: gate reset to NO, script re-uploaded, cron job deleted.
