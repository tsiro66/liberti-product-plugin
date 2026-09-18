# PRE-PRODUCTION AUDIT — VirtueMart Product Importer

Date: 2026-09-07 · Importer version: 0.1.0 (commit state of this repo)
Target: MariaDB 11.4.12 / Joomla 5.4.8 / VirtueMart 4.8.0 / DB `support_manouka_` / prefix `xhngw_`
Audit method: full code-path review + 44 automated tests + live scenario runs (§5–§9) against a
**throwaway sqlite copy of the production dump**. **No production connection was made; no
production data was modified.**

---

## 1. Safety status — PASS (one issue found and fixed)

Every code path that can touch the database:

| Path | Access | Writes? |
|---|---|---|
| `--validate-only` | none (no connection at all) | none |
| `--dry-run` (default when no mode flag) | **read-only connection**, diff + print | **impossible** (see below) |
| `--import` (after typed confirmation or `--yes`) | read + write | only inside per-product transaction |
| tests | in-memory/local sqlite fixtures only | none against anything real |
| `ProductImporter.build_plan` | SELECTs only | none — enforced by wrapper |
| `ProductImporter.execute` | one BEGIN…COMMIT/ROLLBACK per product | only planned actions |

* **No connection during `--validate-only`** ✔ (returns before the connect block).
* **Dry-run connects READ-ONLY.** A dry-run must read current state to diff; the audit found
  this was only convention, not enforcement — **fixed**. `Database.read_only` now blocks
  every write-class statement (`INSERT/UPDATE/DELETE/REPLACE/CREATE/DROP/ALTER/TRUNCATE/
  RENAME/BEGIN/SET/…`) at the wrapper level (`ReadOnlyViolation`), and for MariaDB the CLI
  additionally issues `SET SESSION TRANSACTION READ ONLY` so the **server itself** rejects
  writes. Tested: `test_read_only_wrapper_blocks_every_write_class`,
  `test_read_only_connection_blocks_product_import`.
* **`--import` is the only write path** ✔ (`do_import` flag gates `execute()`; mutually
  exclusive with `--dry-run`/`--validate-only`).
* **DELETE scope**: exactly one DELETE statement exists (`CustomFieldRepository.delete_by_ids`);
  ids come from a per-`(product_id, custom_id ∈ {6,7,10})` SELECT and are bound as parameters.
  No code path can delete outside managed custom fields. ✔
* **UPDATE scope**: every UPDATE targets an explicit primary key (product id, price-row id,
  media-join id) or `(product_id, lang)` pair; the SET-list contains only fixed strings with
  bound values. Unowned tables (manufacturers, categories tree, orders, ratings,
  vmcustomadvanced, CSVI, customs, calcs, currencies, shoppergroups) have **no** write code
  path at all — the importer has no repository for them. ✔
* **Transactions per product** ✔ — connection is in autocommit mode (fixed in this audit: it
  previously used an implicit transaction for plan-phase reads); `execute()` opens exactly one
  `BEGIN`, commits on success, rolls back on *any* exception. ✔
* **Rollback on every failure** ✔ — `try/except/rollback/re-raise` around all product ops;
  CLI catches per product and continues. Test: `test_rollback_on_failure_leaves_no_partial_product`.
* **One failed product cannot leave partial rows** ✔ (verified by test + live run).
* **Credentials never in logs/exceptions** ✔ — the CLI logs host/port/name only; the summary
  and confirmation never print `DB_PASSWORD`; PyMySQL error strings contain no password.
  Test: `test_no_credentials_in_report_or_cli_output` runs the real CLI with a fake password
  and greps stdout+stderr+logfiles.
* **Parameterized SQL** ✔ — all values are `%s`-bound; no `ON DUPLICATE KEY`, no string
  interpolation of CSV data into SQL. The only f-string substitutions in SQL are **constants**
  (table prefix, `lang` from a fixed 2-tuple, vendor id). ✔
* Image copies happen **before** the DB transaction (filesystem cannot roll back); a DB
  failure leaves at most an orphan file on the server, never a dangling media row. Reported
  per product.

Issues found & fixed during this audit:

1. dry-run was read-only by convention only → app-level + server-level enforcement added.
2. `autocommit=False` held an implicit read transaction during planning → switched to
   `autocommit=True` + explicit per-product `BEGIN`.
3. `ProductRepository.set_published` was dead code → removed.
4. `parse_csv` crashed on non-UTF-8 files / malformed CSV structure → now reported as
   validation errors.
5. Malformed multi-value cells (line breaks, >2500 chars = `customfield_value` column limit)
   now validated.

## 2. Database compatibility status — PASS for SQL; MariaDB runtime run still pending (§10)

Verified directly against the dump (not assumed):

| Item | Status |
|---|---|
| Table engines | all 8 write-target tables `ENGINE=InnoDB` → transactions work ✔ |
| AUTO_INCREMENT | `products`, `product_prices`, `product_customfields`, `medias`, `product_medias`, `product_categories` have AUTO_INCREMENT → INSERTs omit PKs and read `lastrowid` ✔ |
| Language tables | `products_en_gb`/`products_el_gr` have **NO** AUTO_INCREMENT (PK = product id) → importer inserts their PK explicitly ✔ (this was explicitly checked: inserting without it would fail under strict sql_mode) |
| Foreign keys | dump contains **zero** FK constraints → no FK ordering hazards ✔ |
| Strict sql_mode | no zero-date literals inserted (`'0000-00-00'` only via schema defaults, never explicit); empty strings/NULLs per CD004 rows ✔ |
| utf8mb4 | connection uses `charset='utf8mb4'`; tables are utf8mb4; Greek content round-trips ✔ (tested with Greek titles/descriptions/filenames) |
| Decimal precision | `product_price` decimal(15,6); net values stored verbatim (100.00 → `100`, 77.82258 → `77.82258`); `--price-mode gross` rounds to 6 dp, matching DB precision ✔ |
| Transactions | per-product `BEGIN/COMMIT/ROLLBACK`; PyMySQL `begin()` with `autocommit=True` opens an explicit InnoDB transaction ✔ |
| `ON DUPLICATE KEY` | not used anywhere ✔ |
| Timestamps | naive `YYYY-MM-DD HH:MM:SS` strings, matching existing rows' format ✔ |

**SQLite-vs-MariaDB deltas to be aware of** (SQLite was only a test harness):

1. `LIMIT 1` in two SELECTs — valid in both; no delta.
2. `UPPER()` — ASCII-only in sqlite, locale/utf8 aware in MariaDB; both fine for SKU matching.
3. `GROUP_CONCAT`/regex — not used in importer SQL.
4. Auto-increment behavior — production gets true AUTO_INCREMENT (max+1, gap-safe); the
   sqlite copies used in tests emulate it via `INTEGER PRIMARY KEY AUTOINCREMENT` after a
   one-off schema rebuild (documented in §10 procedure). Real MariaDB watermarks (e.g. next
   product id ≈ 497) come from the server, never from the importer.
5. Locking/timeout behavior — not exercised by sqlite. First real import should be a small
   batch (see §14) to observe lock waits, if any.
6. `SET SESSION TRANSACTION READ ONLY` — supported by MariaDB 11.4; wrap in try/except is
   *not* done deliberately (fail loudly if the server rejects it) — verify on first dry-run.

SQL statements to eyeball on the first real dry-run (they are also visible in
`product_medias`/`product_customfields` operations):

```sql
INSERT INTO xhngw_virtuemart_products (...) VALUES (...);          -- 43 columns, CD004-shaped
INSERT INTO xhngw_virtuemart_products_en_gb / _el_gr (...)         -- PK = product id
INSERT INTO xhngw_virtuemart_product_prices (...)                  -- tax 1, currency 47, sg 0
INSERT INTO xhngw_virtuemart_product_customfields (...)            -- published 0, price 0
INSERT INTO xhngw_virtuemart_medias (...) / product_medias (...)   -- file_type 'product'
UPDATE xhngw_virtuemart_products SET modified_on/by ...            -- + owned flags
UPDATE xhngw_virtuemart_products_en_gb/el_gr SET product_name/desc ...
UPDATE xhngw_virtuemart_product_prices SET product_price ...
UPDATE xhngw_virtuemart_product_medias SET ordering ...
DELETE FROM xhngw_virtuemart_product_customfields WHERE virtuemart_customfield_id IN (...)
```

## 3. ID generation — PASS

* Product id: `INSERT` without `virtuemart_product_id`; id read from `cursor.lastrowid`
  (= MariaDB `LAST_INSERT_ID()` semantics). Never computed from `MAX(id)`.
* Language rows: PK **explicitly set to the product id** (schema has no auto-increment there).
* Price/customfield/media/join ids: same `lastrowid` mechanism; join links reference ids
  resolved from DB lookups (`file_url`) or freshly inserted within the same transaction.
* CD004's id (494) is never hardcoded or reused; SKU is the only lookup key
  (`test_sku_lookup_case_insensitive_update`, `test_create_new_product_full_cd004_shape`).
* Live check (§5): new product got id **497** — the natural next watermark of the copy
  (494–496 exist in the dump) — proving server-style generation.

## 4. Existing-product protection — PASS (live test)

CD004 (dump copy, id 494, published=1, 3 images, manufacturer link, 10 customfield rows incl.
unowned custom 18 "Heel"):

* found by SKU (`cd004` case-variant → case-insensitive match, note in plan);
* fed its **exact current values** → plan = `Changes: none (already up to date)`, **zero
  writes** (verified with row counts before/after);
* update run with changed price/sizes/colours/fabric:
  * price updated on the SAME price row (id 1417), net value exact;
  * size 35 removed / new size added; colour/fabric rows diffed; **custom 18 heel untouched**;
  * published stayed 1, slug stayed `cd004`, customtitle/metadesc/metakey untouched;
  * 3 existing images kept with ordering intact; no manufacturer/category write path exists
    (asserted in `test_update_preserves_manufacturer_and_category_links`).

## 5. New-product test — PASS (live run)

`TEST-IMPORT-001` (net 100.00, sizes 35|36|37|38, colours BLK|RED, fabric Leather,
5 images incl. unicode + space names) imported into the throwaway dump copy:

| Check | Result |
|---|---|
| product id | 497 (server-style next id), `published = 0`, `gtin = sku`, stock 0, `has_prices=1 has_medias=1`, `has_categories=0 has_manufacturers=0`, standard `product_params` string |
| EN row | name `Test Product`, desc, `customtitle=name`, slug `test-product`, metadesc `''` |
| EL row | name `Δοκιμαστικό Προϊόν`, Greek desc, same slug `test-product` |
| price row | `100` net, `product_tax_id=1`, currency 47, shoppergroup 0, qty 0–0, override 0 |
| custom fields | 4 Size + 2 Colour + 1 Fabric rows; `customfield_price=0`, `published=0`, `ordering=0`, `customfield_params` byte-identical to the shop constant |
| media | 5 rows `file_type='product'`, `published=1`, `is_image=1`, relative `file_url`s; links `ordering 1..5`; deterministic natural order (`2 Red` → `10 White` → `Black` → `Blue` → `Μπλε`); first = main; files physically copied |
| CD004 | untouched |

## 6. Idempotency test — PASS, exact write count: **0**

Re-running the identical CSV:

```
created 0 · updated 0 · unchanged 1 · failed 0 · images copied 0
```

Row counts unchanged (1 product / 7 customfield rows / 5 media rows / 5 links / 1 price row).
The second run starts **no transaction at all** (plan has zero actions).

## 7. Update test — PASS

Second CSV for the same SKU (new title, new descriptions, price 123.45, size 35→39,
colour BLK→GREEN, fabric Leather→Suede):

* changed exactly: `product_name` (EN), `product_desc` (EN+EL), price `100 → 123.45`,
  sizes `{36,37,38,39}`, colours `{GREEN}`, fabric `{Suede}`;
* preserved exactly: slug `test-product`, `customtitle` (old value — not CSV-owned),
  published 0, gtin, stock, `has_*` flags, all 5 media links with orderings 1..5;
* `modified_on` bumped, `modified_by=119`; CD004 untouched.

## 8. Image tests — PASS

| Scenario | Behaviour (test/live) |
|---|---|
| one image | ordering 1 = main ✔ |
| multiple images | natural sort deterministic (`2` before `10`), orderings 1..N ✔ |
| repeated import | zero new media/link rows, orderings unchanged ✔ |
| same filename, same content | file reused, media row reused ✔ |
| same filename, **different** content | `FileExistsError` → product fails & rolls back; server file never overwritten ✔ |
| missing image | warning `no matching image found (import continues)`; product still imported ✔ |
| Unicode filename | `TEST-IMPORT-001 Μπλε.jpg` matched, copied, registered, ordered ✔ |
| spaces in filename | `0405 PT Orchid Mist.jpg` handled ✔ |

## 9. CSV validation — PASS

| Malformed input | Result |
|---|---|
| duplicate SKU (case-insensitive) | error, names both rows |
| missing/empty SKU | error |
| missing EN/EL title or description | error |
| invalid price (`abc`, `0`, `-5`, `1.234,56`) | error |
| empty sizes/colours cells | allowed (means "not provided") — documented |
| malformed multi-value (line break in value, >2500 chars) | error |
| unknown column | error (all problems reported together) |
| invalid UTF-8 / malformed CSV structure | error (`ValidationError`, no traceback) |
| image matching no SKU / missing images dir | warning, import continues |

## 10. MariaDB runtime test — NOT AVAILABLE locally (documented, not skipped silently)

No local MariaDB/Docker access exists on this machine (no socket permissions, no sudo), and
installing one was out of scope per instructions. Therefore:

* **Only tested under SQLite:** connection mechanics (pymysql handshake, utf8mb4 charset
  negotiation), AUTO_INCREMENT server behavior, `SET SESSION TRANSACTION READ ONLY`,
  lock/timeout behavior under concurrency, strict-mode nuances of MariaDB 11.4.
* **Manually verify on the first real dry-run/import (1–3 products only):**
  1. `SET SESSION TRANSACTION READ ONLY` is accepted by MariaDB 11.4 (it is standard syntax;
     if it errored, the dry-run aborts loudly — safe).
  2. One CREATE + one UPDATE with `SHOW WARNINGS` after each step (look for truncation or
     sql_mode complaints — expect none).
  3. `SELECT LAST_INSERT_ID()` style checks are implicit in `lastrowid` — confirm ids match
     the inserted rows (`virtuemart_product_id`, `virtuemart_product_price_id`,
     `virtuemart_customfield_id`, `virtuemart_media_id`, join `id`).
  4. Greek content appears correctly in Joomla admin (encoding round-trip).
* The SQL itself is ANSI-basic and was derived from the real dump; the dump's own schema
  (AUTO_INCREMENT columns, no FKs, InnoDB) was re-verified in this audit (§2 table).

## 11. The four open questions (unchanged behavior — no guessing)

| # | Question | Current implementation | DB evidence | Blocks import? | Dev confirmation |
|---|---|---|---|---|---|
| 1 | `customfield_price` semantics | always writes **0** for 6/7/10 rows | every distinct non-zero value ×1.24 = clean €0.50-step gross; **all 1,593 Colour rows are 0**; no row equals its product's net price | **No** (0 is the dominant convention) | **Yes** — if colours must ever carry surcharges, the CSV needs a column and the net/gross entry convention must be defined |
| 2 | `product_customfields.published = 0` | writes **0** (matches all 10,670 rows) | 10,670/10,670 rows are 0 while options render and sell → frontend does not filter in this build | **No** | **Yes** — confirm no VM/theme update will start filtering on it |
| 3 | manufacturer for new products | `has_manufacturers = 0`, no link | 429/431 products have one (CD004 → "Go Dance" id 15) | **No** (product imports, shows without brand) | **Recommended** — if a default manufacturer is wanted, it is a 2-line change (`product_manufacturers` insert + flag) |
| 4 | Greek option strings | single language-independent value row | e.g. "BLK", "9.0cm Plated Heel" shown as-is on the Greek site | **No** | **Recommended** — confirm Greek labels are acceptable for imported products |

## 12. Exact commands

Dry-run (against production, **read-only enforced at app + server level**):

```bash
.venv/bin/python importer.py products.csv --dry-run --images ./images
```

Import (writes; asks to type `yes`):

```bash
.venv/bin/python importer.py products.csv --import --images ./images
```

Small controlled first batch:

```bash
.venv/bin/python importer.py first-batch.csv --validate-only --images ./images
.venv/bin/python importer.py first-batch.csv --dry-run     --images ./images
.venv/bin/python importer.py first-batch.csv --import      --images ./images --category-id 62
```

(Add `--sku SKU1,SKU2` to restrict; `--limit N` to cap rows.)

## 13. Known limitations

1. No MariaDB round-trip executed yet (§10) — do the 1–3-product controlled import first.
2. Plan→execute window: plans are built from a pre-confirmation snapshot; concurrent admin
   edits between dry-run and import are not re-diffed. Single-operator usage assumed.
3. Image files are copied to `VM_MEDIA_DIR` directly (SSHFS/SCP mount or running on the
   server); the importer cannot upload over plain SSH by itself.
4. Custom-field surcharges (sizes/fabrics with price modifiers) are not expressible in the
   CSV format — always 0 (matches Colour convention; see §11.1).
5. New products get no manufacturer and no category unless `--category-id` is passed;
   category **creation** is out of scope (dual-stored tree documented in the analysis).
6. Slug is derived from the EN title only and written to both languages; existing slugs are
   never modified.

## 14. Recommended procedure for the FIRST real import (conservative)

1. **Backup**: `mysqldump --single-transaction support_manouka_ | gzip > backup-$(date +%F).sql.gz`
   and verify the dump file. (Also note current `AUTO_INCREMENT` values of the 6 tables.)
2. **Prepare a CSV with only 1–3 real products** (suggest: one brand-new SKU and one existing
   SKU to exercise CREATE and UPDATE paths).
3. `--validate-only` → fix every reported problem.
4. `--dry-run` → read every plan line; confirm operations match expectation
   (CREATE vs UPDATE, price, custom field values, image orderings).
5. **Review** the dry-run output; check the log file in `logs/`.
6. `--import` (type `yes`); expect a per-product `CREATED`/`UPDATED` line and a clean summary.
7. **Inspect in Joomla/VirtueMart admin** (products are unpublished, so no shop impact):
8. Verify per product:
   - EN + EL titles and descriptions render correctly (Greek included),
   - price: net value in DB; frontend shows gross = net × 1.24,
   - sizes / colours / fabric dropdowns list exactly the CSV values, in order,
   - images: correct files, correct order, first image is the main product image,
   - product is **unpublished** (not visible in shop),
   - `modified_by = 119` (or configured user), no unexpected rows in
     `product_customfields`/`product_medias` for other products.
9. Only then import the remaining products (batches of ~20–50, re-running `--dry-run` first).
10. Keep the backup + the per-run log files (`logs/import-*.log`) until the batch is verified.

**Do not run `--set-published 1` until the shop owner has reviewed the products.**

---

## Verdict

**Safe for a small controlled production test** — with three conditions:

1. Use the exact §14 procedure (backup → 1–3 products → validate → dry-run → import → verify).
2. Watch the first MariaDB dry-run specifically for `SET SESSION TRANSACTION READ ONLY`
   acceptance and encoding round-trip (§10 checklist) — these are the only two behaviors not
   reproducible outside a real server.
3. Confirm the four §11 items with the Joomla developer; none of them blocks the first test
   batch (the importer's current choices reproduce the database's own conventions exactly).
