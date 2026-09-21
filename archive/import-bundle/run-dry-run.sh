#!/bin/bash
# Libertí importer — SERVER dry-run (READ-ONLY against the live DB).
# No pip/venv needed: PyMySQL is vendored in ./vendor (pure Python).
set -u
cd "$(dirname "$0")"          # bundle dir = /home/manouka/web/libertidance.com/import-bundle

LOG=dryrun-out.txt
# batch selection: edit these two lines per batch
CSV_FILE=products.test2.csv
IMAGES_DIR=images/test2
exec > >(tee -a "$LOG") 2>&1
echo "=== DRY RUN start: $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
echo "server python: $(python3 --version 2>&1)"

# vendored dependency (pure-python PyMySQL) — no network, no pip, no venv
export PYTHONPATH="$PWD/vendor"

# dry-run (read-only enforced in code AND by SET SESSION TRANSACTION READ ONLY)
# --create-only: rows whose SKU already exists in the shop are skipped —
# existing products are NEVER updated.
python3 importer.py "$CSV_FILE" --dry-run --create-only --images "$IMAGES_DIR"
RC=$?
echo "=== DRY RUN end (exit $RC): $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
echo "IMPORTANT: review every plan line in $LOG. Nothing has been written."
