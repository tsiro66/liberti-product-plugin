#!/bin/bash
# Libertí importer — SERVER import (WRITES to the live database).
#
# HARD GATE: this script refuses to run until APPROVED below is flipped to YES.
# Before flipping: backup exists + dryrun-out.txt reviewed + CSV confirmed.
set -u
cd "$(dirname "$0")"

APPROVED=no          # <— EDIT THIS LINE to YES only after the dry-run is reviewed

if [ "$APPROVED" != "YES" ]; then
    echo "REFUSING: edit run-import.sh and set APPROVED=YES after reviewing dryrun-out.txt."
    echo "Also confirm: database backup exists (Hestia BACKUP tab)."
    exit 1
fi

LOG=import-out.txt
exec > >(tee -a "$LOG") 2>&1
echo "=== IMPORT start: $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="

export PYTHONPATH="$PWD/vendor"

# --yes: the APPROVED gate replaces the interactive confirmation (no TTY under cron)
python3 importer.py products.batch1.csv --import --yes --images images
RC=$?
echo "=== IMPORT end (exit $RC): $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
echo "Review $LOG + verify the products in Joomla admin before importing more."
