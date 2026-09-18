# Libertí import — server bundle instructions

Upload `import-bundle.tar.gz` to the FTP root (`/home/manouka_ftp/`), NOT into
public_html — everything here except the images must not be web-accessible.

## Files

| File | Purpose |
|---|---|
| `vmimporter/`, `importer.py`, `requirements.txt` | importer code |
| `.env` | server DB config (**fill DB_PASSWORD before uploading**) |
| `products.batch1.csv` | first batch: 0405PT, 0406PT, 0412 — **titles/prices are DRAFTS, confirm before import** |
| `images/` | 17 matching product images (upload copies go to the VirtueMart media dir automatically) |
| `run-dry-run.sh` | read-only: prints the plan, installs deps on first run |
| `run-import.sh` | writes to DB — hard-gated by `APPROVED=no` until flipped to `YES` |

## Run order (Hestia CRON tab, one-shot jobs)

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

**2. Confirm `products.batch1.csv`:** fix any title/description/price drafts.
If prices are shop-display (VAT-inclusive) numbers, tell me — we flip
`PRICE_MODE=gross`. Delete the cron job after it fires.

**3. Import (WRITES):** download `run-import.sh`, edit `APPROVED=no` → `YES`,
upload back, create cron job with the same command but `run-import.sh`.
Then FTP-download `import-out.txt`, delete the cron job.

**4. Verify** in Joomla/VirtueMart admin + phpMyAdmin:
products exist with `published=0`, EN+EL names, net price ×1.24 = expected gross,
sizes/colours dropdowns, image order, `images/stories/virtuemart/product/` files.

## Safety properties

- dry-run: connection is read-only (app-enforced + `SET SESSION TRANSACTION READ ONLY`).
- import: one transaction per product; failure = rollback, next product continues.
- no CD004 (or any existing product) is touched by this batch — CSV contains only new SKUs.
- logs: `logs/import-*.log` + `dryrun-out.txt`/`import-out.txt` — keep them.
