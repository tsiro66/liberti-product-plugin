# VirtueMart Product Importer (Libertí / VirtueMart 4.8.0)

A reusable Python CLI that imports products from a CSV file **directly into the MariaDB
database** of a Joomla 5.4.8 + VirtueMart 4.8.0 shop (table prefix `xhngw_`). No Joomla
extension, no VirtueMart plugin, no HTTP API, no CSVI — plain SQL driven by the exact schema
documented in [`virtuemart-database-analysis.md`](virtuemart-database-analysis.md).

**Safe by default:** without an explicit `--import` flag nothing is ever written.
`--dry-run` prints the exact per-product plan (every INSERT/UPDATE/DELETE it would run).

```
python importer.py products.csv --dry-run     # plan only, zero writes
python importer.py products.csv --import      # writes, after typed confirmation
python importer.py products.csv --validate-only
```

---

## 1. Installation

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill in credentials (see below)
```

The only runtime dependency is `pymysql` (pure Python MariaDB/MySQL driver) plus
`python-dotenv`. Tests additionally use `pytest`.

## 2. Configuration

Credentials come **only** from environment variables or a `.env` file (never hard-coded):

| Variable | Meaning |
|---|---|
| `DB_HOST`, `DB_PORT` | MariaDB host/port |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | database + credentials |
| `DB_BACKEND` | `mysql` (production) or `sqlite` (testing against a restored dump copy; `DB_NAME` is then the sqlite file path) |
| `IMAGES_PATH` | local images directory (default `images`) |
| `VM_MEDIA_DIR` | **absolute** path of the VirtueMart product media directory on the server (default from the analysis: `/home/support/web/libertidance.com/public_html/images/stories/virtuemart/product`) |
| `VM_ADMIN_USER_ID` | Joomla user id written to `created_by`/`modified_by` (shop uses `119` = *Liberti Dancewear*) |
| `VM_VAT_RATE` | VAT percent of calc rule 1 (24) — used for `--price-mode gross` |
| `PRICE_MODE` | `net` (default) or `gross` (server bundle default: `gross`) |
| `LOG_DIR` | log directory (default `logs`) |

CLI flags override the environment (`--db-host`, `--images`, `--category-id`, …).
The `.env` file is git-ignored; `.env.example` documents every key.

Fixed installation constants (verified in the dump, see analysis §3): table prefix
`xhngw_`, vendor 1, currency 47 (EUR), tax calc rule 1 (VAT 24%), custom fields
6=Size / 7=Colour / 10=Fabric.

## 3. CSV format

Header row (columns may be in any order; unknown columns are a validation error):

```csv
sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric
CD004,Go Dance Latin Shoes CD004,...,<p>...</p>,<p>...</p>,77.82258,35|36|37|38,BLK,Leather
```

| Column | Required | Notes |
|---|---|---|
| `sku` | ✔ | identity of the product; matched against `product_sku` case-insensitively |
| `title_en`, `description_en` | ✔ | `products_en_gb.product_name` / `product_desc` (HTML allowed) |
| `title_el`, `description_el` | ✔ | `products_el_gr` equivalents — both language rows are always written |
| `price` | ✔ | the **FINAL VAT-inclusive shop price** (server default `PRICE_MODE=gross`): stored net = price / (1 + VAT/100), rounded to 6 decimals into `product_prices.product_price` (decimal(15,6)); tax rule 1 redisplays the CSV price on the frontend. With `PRICE_MODE=net` the value is stored verbatim as the net price. A single decimal comma is tolerated (`96,50`) |
| `sizes` | – | multi-value, `|` separated → one `product_customfields` row per value (custom 6). Empty cell = **not provided** → existing values untouched |
| `colours` | – | same pattern, custom 7. Empty cell = untouched |
| `fabric` | – | same pattern, custom 10 (1..N values supported; the DB contains multi-fabric products) |
| `short_desc_en`, `short_desc_el` | – | optional → `product_s_desc` |
| `category_id` | – | optional, per-product category: one virtuemart_category_id, or several pipe-separated (`62|65`). Validated against `xhngw_virtuemart_categories` (unknown id = error, nothing imported). **Empty cell = no category for this row** (overrides `--category-id`). Column absent entirely = `--category-id` CLI flag applies to every new product. Existing products: links are only ever ADDED, never removed. UPDATE rows also validate ids |
| `manufacturer_id` | – | optional, single virtuemart_manufacturer_id (shop convention: one manufacturer per product; pipe-separated values are rejected). Validated against `xhngw_virtuemart_manufacturers` (unknown id = error — create the manufacturer in the shop admin first). Empty/absent = no manufacturer. Writes `virtuemart_product_manufacturers` + `has_manufacturers=1`; existing links are never removed |

`description_en`/`description_el` may be quoted multi-line HTML. Duplicate values inside one
cell collapse (with a warning). Empty optional cell = leave what the DB has.

See `examples/products.example.csv` for a working sample.

## 4. Image naming convention

Images live in one local directory (`./images` or `--images` / `IMAGES_PATH`). A file belongs
to the SKU that **starts** its filename; everything after it is free-form description:

```
0405PT Black.jpg          → SKU 0405PT   (main image: natural-sort first)
0405PT Blue.jpg           → SKU 0405PT
0405 PT Orchid Mist.jpg   → SKU 0405PT   (spaces/hyphens/underscores in the SKU are normalised)
0412.png                  → SKU 0412     (exact stem = SKU)
0510-1 Matt Ribbon.png    → SKU 0510-1   (hyphens are legitimate in SKUs; longest SKU wins)
```

Matching is case-insensitive and tolerant of separator differences; when one file matches
several CSV SKUs the longest SKU wins. Files that match no SKU are reported as warnings and
skipped — the import never crashes on them. `.jpg`, `.jpeg`, `.png`, `.webp` are supported
(`file_mimetype` is derived from the extension). Ordering within a SKU is deterministic
(natural sort: `X 2.jpg` before `X 10.jpg`); **the first image becomes the main image**
(`product_medias.ordering = 1`, VirtueMart convention).

## 5. Dry-run usage

```bash
python importer.py products.csv --dry-run
python importer.py products.csv --dry-run --sku CD004
```

Reads the database, diffs every row and prints the plan — no writes, no file copies, no
transaction. Per product:

```
SKU: 0405PT
Operation: CREATE
  [INSERT_CORE ] virtuemart_products: core row (published=0, gtin=sku)
  [INSERT_LANG ] virtuemart_products_en_gb: name='...', slug='...'
  [INSERT_PRICE] virtuemart_product_prices: net price 96.5 (tax rule 1, EUR, shoppergroup 0)
  [INSERT_CF   ] virtuemart_product_customfields: Size = '36' (custom 6, price 0, published 0)
  [INSERT_MEDIA] virtuemart_medias: '0405PT Black.jpg' (image/jpeg), file_meta = EN title (main image)
  [INSERT_LINK ] virtuemart_product_medias: link ordering 1: 0405PT Black.jpg
```

`--validate-only` skips the database entirely (CSV + image checks only).
All validation problems are reported **together** before any work starts.

## 6. Import usage

```bash
python importer.py products.csv --import                 # asks to type 'yes'
python importer.py products.csv --import --yes           # scripted runs
python importer.py products.csv --import --limit 10
python importer.py products.csv --import --sku CD004,0405PT
python importer.py products.csv --import --category-id 62        # category for NEW products
python importer.py products.csv --import --set-published 0       # force published on all
python importer.py products.csv --import --price-mode gross      # CSV holds final VAT-inclusive prices
python importer.py products.csv --import --create-only           # never touch existing products
```

Useful flags: `--limit N`, `--sku LIST`, `--images DIR`, `--category-id ID`,
`--set-published {0,1}`, `--price-mode {net,gross}`, `--vat-rate PCT`, `--log-dir DIR`,
`--env-file FILE`, `--verbose`.

Exit codes: `0` success · `1` some products failed/skipped or aborted · `2` validation or
configuration error.

## 7. How existing products are updated

Matched by SKU (exact first, then case-insensitive; ambiguous SKUs abort that row). Only
**owned fields** are changed — everything else in VirtueMart is preserved:

| Owned (updated) | Preserved (never touched) |
|---|---|
| core row `modified_on/by`, `has_medias`/`has_categories` flag fixes | `published` (unless `--set-published`), `product_sku`, `product_gtin`, stock |
| `products_en_gb` / `products_el_gr`: `product_name`, `product_desc`, `product_s_desc` (when optional column filled) | `slug`, `customtitle`, `metadesc`, `metakey` (SEO/URL stability) |
| the default price row (shoppergroup 0, qty 0–0) | shoppergroup-specific price rows, discounts |
| custom-field rows for **ids 6/7/10 only** (set-diff) | all other custom fields (e.g. custom 18 “Heel”) and plugin fields |
| product↔media links + `ordering`, media rows for newly registered files | manufacturer links, other media metadata |

Custom-field set-diff: values present in DB but absent from a non-empty CSV cell are removed
(scoped to that product + custom id); values absent from DB are inserted. **An empty CSV cell
means “not provided” — nothing is removed.** `customfield_price` is always written as `0`,
reproducing the observed convention (all 1,593 existing Colour rows are 0; the CSV format has
no surcharge column — see analysis §6).

## 8. How new products are created

Replicates the CD004 reference shape exactly (verified by tests):

* `virtuemart_products`: vendor 1, parent 0, `product_gtin = sku` (shop convention),
  `published = 0`, stock 0, `product_stockhandle '0'`, the standard `product_params` string,
  `has_prices = 1`, `has_medias = 1` iff images exist, `has_categories = 1` iff
  `--category-id` given, `has_manufacturers = 0`, empty `metarobot/metaauthor/intnotes/layout`.
* One row in **both** `products_en_gb` and `products_el_gr` (slug derived from the EN title,
  shared by both languages like `cd004`/`latin-shoes`; uniquified per table if taken).
  `metadesc`/`metakey` = short description (CD004 convention), `customtitle` = product name.
* One `product_prices` row: NET price, `product_tax_id = 1` (existing VAT rule — no new rules),
  `product_currency = 47`, shoppergroup 0, quantity 0–0.
* One `product_customfields` row per Size/Colour/Fabric value: `customfield_params`
  `product_sku=""|product_gtin=""|product_mpn=""||`, `published = 0`, `ordering = 0`
  (exact convention of all 10,670 existing rows), `customfield_price = 0`.

## 9. How images are handled

Files are copied to `VM_MEDIA_DIR` (e.g. via an SSHFS mount or SCP beforehand); the database
stores **relative** URLs only (`images/stories/virtuemart/product/<name>`), exactly like the
existing rows — no binary data in the DB, no thumbnails to generate (VM builds them at
runtime). Existing files on the server are never overwritten; same-name + same-content is
reused, same-name + different-content aborts that product. Media rows are deduplicated by
`file_url` (reuse the existing `virtuemart_media_id`). Pre-existing product images not managed
by the CSV are **kept** and ordered after the CSV images; ordering is renumbered 1..N, which
keeps repeated imports idempotent. Execution order per product: files copied first, then the
DB transaction — a DB failure can therefore leave an orphan image file (harmless, reported)
but never a dangling media row.

## 10. How rollback works

One SQL transaction per product (`BEGIN … COMMIT`, `ROLLBACK` on any failure). A failing
product is reported and the import continues with the next; no partial product ever remains.
Image-file copies happen before the transaction (the filesystem cannot roll back) and are
reported separately. Never-touched tables: orders/invoices/ratings/carts, the
`vmcustomadvanced` plugin tables, `virtuemart_customs`, `virtuemart_calcs`, `virtuemart_currencies`,
`virtuemart_shoppergroups`, CSVI tables.

## 11. How to test safely

```bash
.venv/bin/pytest tests/ -q          # 35 tests, no DB credentials needed
```

Unit tests cover CSV parsing/validation, image matching/ordering, slugs and price conversion.
Integration tests run the **full plan/execute flow** against an in-memory sqlite copy of the
relevant tables seeded with the real CD004 data: CD004-shaped row assertions, idempotency,
dry-run purity, rollback, owned-fields-only updates.

For a full end-to-end dry-run/import rehearsal, restore the production dump into a **local**
MariaDB (or use `DB_BACKEND=sqlite` with a converted copy of the dump), then:

```bash
python importer.py examples/products.example.csv --dry-run \
    --db-backend sqlite --db-name /path/to/dump-copy.sqlite --images examples/images
```

Nothing in this repository touches the production database unless you run `--import` with real
credentials and confirm the prompt.

## 12. VirtueMart-specific assumptions (from the reverse-engineering phase)

1. **Prices are NET in the DB.** VAT comes from the single global calc rule (id 1, `VatTax +24%`,
   unrestricted). The importer never stores gross prices and never creates calc rules.
   Server default `PRICE_MODE=gross`: the CSV `price` column holds the FINAL VAT-inclusive
   shop price; the stored net is price / 1.24 (6 dp) so the frontend redispers it exactly.
   Set `PRICE_MODE=net` to store CSV prices verbatim as net instead.
2. **`customfield_price` is a net surcharge** — every distinct existing value ×1.24 is a clean
   €0.50-step gross amount, and no row ever equals its product's net price. Because all
   existing Colour rows are 0 and the CSV carries no surcharges, the importer always writes 0.
   The developer's earlier “colour price = product price minus VAT” statement remains
   **UNKNOWN — needs confirmation** (contradicted by the dump in its literal reading).
3. **`product_customfields.published = 0` everywhere** (10,670/10,670 rows) while the shop
   renders those options — the frontend does not filter on it in this installation. New rows
   write `0` to match. *UNKNOWN — needs confirmation* (would a VM upgrade start filtering?).
4. **Custom fields 6/7/10 are plain string fields** (`field_type='S'`, no plugin). The
   “VM Custom Advanced” plugin system (customs 13/14/19/20, `xhngw_vmcustomadvanced_*` tables)
   is deliberately untouched.
5. **Both language rows always exist** (431/431/431 in the dump); slugs are shared across
   languages and derived from the English title.
6. `product_gtin` duplicates the SKU (CD004 convention). Stock defaults to 0 for new products.
7. `created_by`/`modified_by` use `VM_ADMIN_USER_ID` (119 in this shop).

### Remaining items for the Joomla developer (from the analysis, §12)

* Confirm custom-field price entry semantics (gross in admin UI vs net in DB) and whether
  imported Colours must ever carry surcharges.
* Confirm the `published=0` custom-field convention is safe long-term.
* Decide whether imported products need a manufacturer (429/431 products have one; new
  products get `has_manufacturers = 0` unless links are added manually).
* Confirm Greek translations of Size/Colour/Fabric option strings are not required (values
  are stored once, language-independently).
