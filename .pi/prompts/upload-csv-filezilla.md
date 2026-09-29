You are guiding me through uploading product CSVs from my laptop to my shop
server using FileZilla. I am new to this. Go SLOWLY: one step at a time, plain
language, wait for my confirmation before moving on. If a decision is mine to
make, ask me. Use plain ASCII text only (no unicode symbols like multiplication
signs or smart quotes - they break my setup).

## Context (verified - trust this, do not re-derive)

- Project on my laptop: ~/Projects/liberti-product-plugin
- Shop: Joomla 5.4.8 + VirtueMart 4.8.0 on shared hosting (HestiaCP).
  No SSH access. Deployment is FTP + one-shot cron jobs only.
- Server target directory: /home/manouka/web/libertidance.com/import-bundle/
  (outside public_html, so nothing is publicly downloadable)
- The importer code lives on the server inside that folder:
  - import-bundle/importer.py (CLI launcher) - goes at the bundle ROOT
  - import-bundle/vmimporter/ (the package, 10 .py files) - goes INSIDE
    the vmimporter/ SUBFOLDER, never at the root
  - import-bundle/vendor/ (PyMySQL) - never touch, never re-upload
  - import-bundle/run-dry-run.sh and run-import.sh (cron scripts)
- CSV files go to the bundle ROOT: import-bundle/products.<name>.csv
- Product images go to: import-bundle/images/<batchname>/ (one folder per CSV)
- Before every upload I must run on my laptop:
  cd ~/Projects/liberti-product-plugin && python3 tools/sync-bundle.py
  It copies repo code into server-bundle/, verifies it is byte-identical, and
  prints the exact FTP upload list. I upload from server-bundle/, never from
  anywhere else.

## My mistakes to watch for (I have made these)

1. Uploading vmimporter/*.py files to the bundle ROOT instead of the
   vmimporter/ subfolder. This overwrites the CLI launcher and breaks
   everything with "ImportError: attempted relative import".
2. Uploading stale local copies instead of freshly synced ones.
3. Code and CSV must be uploaded together: a new CSV with old code fails
   validation; old CSV with new code silently skips the new features.

## What I need from you

Guide me through, in this order, one step at a time:

1. Connect to the server in FileZilla (host/user/password/port come from my
   hosting panel - help me find where, do not ask me to paste the password).
2. Navigate to the server directory /home/manouka/web/libertidance.com/import-bundle/
   in the remote pane, and to ~/Projects/liberti-product-plugin/server-bundle/
   in the local pane.
3. Upload the CSV (and the images folder for this batch, plus any code files
   the sync script listed) to the exact right paths. Double-check with me that
   each file lands in the right subfolder BEFORE I click anything.
4. Optionally edit run-dry-run.sh on the server (or guide me to edit it locally
   and re-upload it) so CSV_FILE= and IMAGES_DIR= point at this batch.
5. Create a one-shot cron job in HestiaCP that runs:
   /home/manouka/web/libertidance.com/import-bundle/run-dry-run.sh
   Then I delete the cron job after it fires.

## Safety rules (non-negotiable)

- run-dry-run.sh is READ-ONLY (enforced in code and by a read-only DB session).
  It appends its output to import-bundle/dryrun-out.txt.
- run-import.sh WRITES to the live shop database. It refuses to run unless
  APPROVED=YES inside the script is edited. Never guide me to flip that gate
  unless I explicitly say: "the dry-run is reviewed, backup exists, proceed".
- The importer always runs with --create-only: existing products are NEVER
  updated or deleted. New products import unpublished and without category,
  unless the CSV's category_id / manufacturer_id columns say otherwise.
- CSV price column = final VAT-inclusive customer price (VAT 24%). The
  importer divides by 1.24 and stores the net price. I do the retail math in
  the spreadsheet: retail = wholesale x 2.24, rounded up to whole euros.
- Never modify anything under public_html/ except product image files, which
  the importer itself copies - I never upload there manually.

Start by asking me whether this batch needs a code upload (did I change any
importer code since the last upload?) or only CSV + images. Then walk me
through step 1.
