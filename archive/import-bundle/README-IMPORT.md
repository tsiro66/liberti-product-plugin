# Libertí import — server bundle instructions

Upload `import-bundle.tar.gz` to the FTP root (`/home/manouka_ftp/`), NOT into
public_html — everything here except the images must not be web-accessible.

## Files

| File | Purpose |
|---|---|
| `vmimporter/`, `importer.py`, `requirements.txt` | importer code |
| `.env` | server DB config (**fill DB_PASSWORD before uploading**) |
| `products.test2.csv` | test batch: capezio `102` + `1130`, placeholder prices (25/30 €) — **unpublished test import** |
| `images/test2/` | 2 matching product images |
| `run-dry-run.sh` | read-only: prints the plan (PyMySQL is vendored — nothing is installed) |
| `run-import.sh` | writes to DB — hard-gated by `APPROVED=no` until flipped to `YES` |

## Run order (Hestia CRON tab, one-shot jobs)

Both scripts run with `--create-only`: ONLY SKUs missing from the shop are
created; existing products are never updated. New products get NO category
(uncategorised — decide placement later in the admin, if at all).

Cron runs as user `manouka`. Schedule each job 2 minutes into the future,
delete it after its output file appears.

**0. (precondition)** Hestia BACKUP shows a completed backup.

**1. Install + dry-run (READ-ONLY):**

```
Minute/Hour/etc: now + 3 minutes (all five fields filled)
Command:
/bin/bash /home/manouka/web/libertidance.com/import-bundle/run-dry-run.sh
```

Then FTP-download `import-bundle/dryrun-out.txt`, review every plan line
(titles, prices, sizes, colours, fabric, image order). Delete the cron job.

**2. Confirm `products.test2.csv`:** placeholder prices 25.00 / 30.00 (final
VAT-inclusive prices — the customer pays exactly these); change freely before
import. CSV `price` is the FINAL VAT-inclusive shop price (what the customer
pays); the importer stores net = price/1.24 and tax rule 1 redisplays it
(`PRICE_MODE=gross`). Delete the cron job after it fires.

**3. Import (WRITES):** download `run-import.sh`, edit `APPROVED=no` → `YES`,
upload back, create cron job with the same command but `run-import.sh`.
Then FTP-download `import-out.txt`, delete the cron job.

**4. Verify** in Joomla/VirtueMart admin + phpMyAdmin:
2 products exist with `published=0` (unpublished), EN+EL names, stored net
20.16129 / 24.193548 ×1.24 = 25.00 / 30.00, main image
`images/stories/virtuemart/product/102 Glisse.jpg` (and 1130), no category
links. When verified: delete the 2 test products in the admin (or keep them
and let later real imports skip them via `--create-only`).

## Safety properties

- dry-run: connection is read-only (app-enforced + `SET SESSION TRANSACTION READ ONLY`).
- import: one transaction per product; failure = rollback, next product continues.
- no CD004 (or any existing product) is touched by this batch — CSV contains only new SKUs.
- logs: `logs/import-*.log` + `dryrun-out.txt`/`import-out.txt` — keep them.
