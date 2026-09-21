---
description: VirtueMart importer next steps — categories, manufacturer, custom fields (teach slowly, one step at a time)
argument-hint: "[step-number or topic]"
---

You are working on the VirtueMart product importer at ~/Projects/liberti-product-plugin.

# How to work with me (IMPORTANT)

- I am new to most of this (CSV formats, VirtueMart database, Python). I get lost easily.
- Go SLOWLY: one step at a time, explain in plain language what each thing is and why, and wait for my confirmation before moving on or changing anything.
- When you propose a change, explain: what changes, why, what could go wrong, and how we test it before it touches the server.
- Never run anything against the production database. Dry-runs and local sqlite-copy tests are fine.
- Short answers, no walls of text. Ask me questions when a decision is mine to make.

# Context (verified — trust this, don't re-derive)

- Target: live shop MariaDB `manouka_manouka_`, prefix `xhngw_`, Joomla 5.4.8 / VirtueMart 4.8.0.
- Importer: `importer.py` CLI + `vmimporter/` package. Dry-run is the default; writes need `--import`.
- **Safety rules already decided:** products that already exist in the shop are NEVER updated — all real runs use `--create-only`. New products import unpublished (`published=0`) and with NO category unless one is configured.
- Price semantics (decided): CSV `price` column = FINAL VAT-inclusive customer price; importer mode `gross` stores net = price/1.24 (6 decimals), tax rule 1 redisplays it. (Future CSV prices may be computed from wholesale as `ceil(wholesale × 2.24)` — that happens in the spreadsheet, not in the importer.)
- Deployment: no SSH. Code goes to the server via FTP into `/home/manouka/web/libertidance.com/import-bundle/` (outside public_html). Execution = one-shot Hestia CRON jobs running `run-dry-run.sh` / `run-import.sh` (the import script has an `APPROVED=YES` gate; cron runs get deleted after firing). A first real test import already succeeded this way.
- Test state: capezio products `102` and `1130` were imported from `server-bundle/products.test2.csv` — they exist as product ids 497/498, unpublished, no category, no manufacturer, with images. They can be deleted in the admin and re-imported, or kept (create-only skips them).
- Vendored PyMySQL lives in `server-bundle/vendor/` (no pip on the server). Bundle code and repo `vmimporter/` must be kept in sync (I re-upload changed files via FTP).
- Local testing: `local/vm_analysis.db` is a sqlite copy of the DB dump — note its tables have PK constraints stripped, so full-flow sqlite imports need the tables rebuilt first (tests/conftest.py pattern). 48 tests currently pass: run `.venv/bin/pytest tests/ -q`.
- Key docs: `docs/virtuemart-database-analysis.md`, `docs/pre-production-audit.md`, `README.md`.
- Category tree with ids: Women=1, Kids=23, Shoes=24, Accessories=25; children incl. Ballet=61, Latin=62, Liberti Shoes Collection=63, Jazz Shoes=64, Ballroom Various=65, Character=60 (orphaned parent in DB), Leotards=29, Tutus=35, Tights|Gaiters=34, Skirts=31, Social Dancewear|Latin=32, etc. (full list can be queried from the local sqlite copy: `xhngw_virtuemart_categories` + `_en_gb` + `category_categories`).
- Existing manufacturers: Sheddo®=10, Merlet=11, Katz=12, G&G=13, Sansha®=14, Go Dance=15, SoDanca=16. There is NO "Dance You" yet — I may create it in the VirtueMart admin myself.
- The brand CSVs (danceyou/grishko/capezio) are NOT ready — I will redo them separately. Today's work is about making the TOOL support what I need.
- Colour values: the shop stores colours as literal strings (e.g. `09 Black`, `115-46 Masai Red`, `BLK`); there are contradictions in the colour-code list that still need the dev's answers. Do not solve colours in this chat unless I ask.

# The three goals

1. **Per-product category via CSV.** Confirm it can come from the CSV (a `category_id` column, validated against the DB), implement it (multiple categories per product should be possible, pipe-separated), with tests. Show me exactly what a CSV row looks like.
2. **Manufacturer via CSV.** I will create the manufacturers in the VirtueMart admin panel first. The importer then needs a CSV column (e.g. `manufacturer_id`) that links each NEW product to that manufacturer (`xhngw_virtuemart_product_manufacturers` + `has_manufacturers=1`), validated. Explain how I find the manufacturer id after creating it in the admin (phpMyAdmin query is fine — DB user `manouka_antima_@localhost`, read access from the server only; for local checks use the sqlite copy).
3. **Verify custom fields import correctly.** Customs are: id 6 = Size, 7 = Colour, 10 = Fabric (CSV columns `sizes`, `colours`, `fabric`, pipe-separated). Walk me through checking one imported product's custom fields in the admin and in phpMyAdmin, and point out anything the importer does that I should double-check (ordering, published=0 rows, `customfield_price=0`, what empty CSV cells mean on existing products).

# Open question you must raise early

The 2 test products (102, 1130) already exist WITHOUT category/manufacturer. Because runs are `--create-only`, re-running the CSV will skip them, not update them. Ask me how I want to handle them (delete in admin + re-import with categories, or edit manually in admin) before writing any code that assumes one path.

# Process for each goal

1. Explain the current behaviour and the gap in one short block.
2. Propose the design (CSV columns, CLI flags, DB writes) — wait for my OK.
3. Implement with tests (`tests/`, sqlite copy), run the test suite.
4. Prepare the server-bundle sync + FTP upload list + the dry-run cron command.
5. I review dry-run output with you before any `APPROVED=YES`.

Start by acknowledging, then ask me which of the three goals to start with.
