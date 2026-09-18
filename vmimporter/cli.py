"""Command line interface."""
from __future__ import annotations

import argparse
import logging
import sys

from .config import Config, load_config
from .db import Database
from .images import scan_images
from .importer import ProductImporter
from .products_csv import ValidationError, parse_csv
from .reporting import ImportSummary, setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="importer.py",
        description=(
            "Import products from CSV directly into the VirtueMart database "
            "(Joomla 5.4.8 / VM 4.8.0, prefix xhngw_). Safe by default: nothing "
            "is written without --import."
        ),
        epilog=(
            "examples:\n"
            "  python importer.py products.csv --dry-run\n"
            "  python importer.py products.csv --import\n"
            "  python importer.py products.csv --import --limit 10\n"
            "  python importer.py products.csv --dry-run --sku CD004\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("csv", help="path to the products CSV file")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=False,
                      help="diff against the DB and print the plan; no writes (default)")
    mode.add_argument("--import", dest="do_import", action="store_true", default=False,
                      help="execute the plan against the database (asks for confirmation)")
    mode.add_argument("--validate-only", action="store_true", default=False,
                      help="validate CSV + images without touching any database")
    p.add_argument("--yes", "-y", action="store_true",
                   help="skip the interactive confirmation (for scripted runs)")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="process at most N CSV rows (after --sku filtering)")
    p.add_argument("--sku", default=None,
                   help="only import this SKU (comma-separated list allowed)")
    p.add_argument("--images", default=None, metavar="DIR",
                   help="local images directory (default: ./images or IMAGES_PATH)")
    p.add_argument("--category-id", type=int, default=None, metavar="ID",
                   help="link NEW products to this virtuemart_category_id "
                        "(existing products are never re-categorised)")
    p.add_argument("--set-published", type=int, choices=(0, 1), default=None,
                   help="force published state on ALL imported products "
                        "(default: new=0, existing=keep)")
    p.add_argument("--price-mode", choices=("net", "gross"), default=None,
                   help="net: store CSV price verbatim (DB convention). "
                        "gross: store price/(1+VAT). default: net")
    p.add_argument("--vat-rate", type=float, default=None, metavar="PCT",
                   help="VAT percent for --price-mode gross (default 24)")
    p.add_argument("--log-dir", default=None, metavar="DIR", help="log directory")
    p.add_argument("--env-file", default=None, metavar="FILE", help="alternative .env file")
    p.add_argument("--db-host", default=None)
    p.add_argument("--db-port", type=int, default=None)
    p.add_argument("--db-name", default=None)
    p.add_argument("--db-user", default=None)
    p.add_argument("--db-password", default=None)
    p.add_argument("--db-backend", choices=("mysql", "sqlite"), default=None,
                   help="mysql (production) or sqlite (testing against a dump copy)")
    p.add_argument("--verbose", "-v", action="store_true", help="debug console output")
    return p


def _filter_rows(rows, sku_filter, limit):
    if sku_filter:
        wanted = {s.strip().lower() for s in sku_filter.split(",") if s.strip()}
        rows = [r for r in rows if r.sku.lower() in wanted]
    if limit is not None and limit >= 0:
        rows = rows[:limit]
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    overrides = {
        "images_path": args.images,
        "category_id": args.category_id,
        "set_published": args.set_published,
        "price_mode": args.price_mode,
        "vat_rate": args.vat_rate,
        "log_dir": args.log_dir,
        "db_host": args.db_host,
        "db_port": args.db_port,
        "db_name": args.db_name,
        "db_user": args.db_user,
        "db_password": args.db_password,
        "db_backend": args.db_backend,
    }
    try:
        cfg: Config = load_config(env_file=args.env_file, cli_overrides=overrides)
    except Exception as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    logfile = setup_logging(cfg.log_dir, args.verbose)
    log = logging.getLogger("vmimporter")
    log.info("log file: %s", logfile)

    # ---- 1. parse + validate CSV -------------------------------------------
    try:
        rows, csv_warnings = parse_csv(args.csv)
    except ValidationError as exc:
        log.error("CSV validation FAILED — nothing was touched.")
        for problem in exc.problems:
            log.error("  - %s", problem)
        return 2
    for w in csv_warnings:
        log.warning("%s", w)

    rows = _filter_rows(rows, args.sku, args.limit)
    if not rows:
        log.error("no rows left after filtering (--sku/--limit)")
        return 2
    log.info("CSV OK: %d row(s) to process", len(rows))

    # ---- 2. match images -------------------------------------------------------
    image_files, image_problems = scan_images(cfg.images_path)
    for problem in image_problems:
        log.warning("%s", problem)

    from .images import match_images
    grouped, match_warnings = match_images(image_files, [r.sku for r in rows])
    for w in match_warnings:
        log.warning("%s", w)

    summary = ImportSummary(total_rows=len(rows))
    summary.warnings.extend(match_warnings)
    missing = 0
    for row in rows:
        row.images = grouped.get(row.sku, [])
        if not row.images:
            missing += 1
            log.warning("SKU %s: no matching image found (import continues)", row.sku)
    summary.missing_images = missing

    if args.validate_only:
        log.info("validate-only mode: CSV + images OK, no database connection made")
        for row in rows:
            log.info("  %-20s images=%d price=%s", row.sku, len(row.images), row.price_raw)
        print(summary.render())
        return 0

    # ---- 3. connect DB ----------------------------------------------------------
    if cfg.db_backend == "sqlite":
        if not cfg.db_name:
            log.error("DB_NAME must hold the sqlite file path when DB_BACKEND=sqlite")
            return 2
    elif not cfg.db_name or not cfg.db_user:
        log.error("database credentials missing (DB_NAME/DB_USER); "
                  "use --validate-only for CSV-only checks")
        return 2
    try:
        if cfg.db_backend == "sqlite":
            db = Database.connect_sqlite(cfg.db_name, read_only=not args.do_import)
        else:
            db = Database.connect_mysql(
                cfg.db_host, cfg.db_port, cfg.db_user, cfg.db_password, cfg.db_name,
                read_only=not args.do_import,
            )
        if not args.do_import:
            log.info("read-only connection (dry-run): write statements are blocked "
                     "by the application and by the server")
    except Exception as exc:
        log.error("database connection failed: %s", exc)
        return 2

    importer = ProductImporter(db, cfg)

    # ---- 4. plan everything (read-only) -----------------------------------------
    plans = []
    plan_failures = 0
    try:
        for row in rows:
            plan = importer.build_plan(row)
            if plan.errors:
                plan_failures += 1
                log.error("SKU %s: %s", row.sku, "; ".join(plan.errors))
            plans.append((row, plan))
    except Exception as exc:
        log.error("planning failed: %s", exc)
        log.debug("traceback:", exc_info=True)
        db.close()
        return 2

    n_create = sum(1 for _, p in plans if p.operation == "CREATE" and not p.errors)
    n_update = sum(1 for _, p in plans
                   if p.operation == "UPDATE" and p.has_changes and not p.errors)

    if args.dry_run or not args.do_import:
        mode = "DRY RUN (no changes were made)"
        for row, plan in plans:
            log.info("-" * 62)
            for line in plan.summary_lines():
                log.info("%s", line)
        log.info("-" * 62)
        log.info(mode)
        db.close()
        return 1 if plan_failures else 0

    # ---- 5. confirm ---------------------------------------------------------------
    print()
    print(f"Target database : {cfg.db_backend} {cfg.db_host}:{cfg.db_port}/{cfg.db_name}")
    print(f"Products        : {len(plans)} ({n_create} create, {n_update} update, "
          f"{plan_failures} with planning errors)")
    print(f"Media directory : {cfg.vm_media_dir or '(NOT SET — file copies will fail)'}")
    print()
    if not cfg.vm_media_dir and any(p.copies for _, p in plans):
        log.error("VM_MEDIA_DIR is not set but images need copying; aborting")
        db.close()
        return 2
    if not args.yes:
        answer = input("Type 'yes' to write to the database: ")
        if answer.strip().lower() != "yes":
            log.info("aborted by user — nothing was written")
            db.close()
            return 1

    # ---- 6. execute -----------------------------------------------------------------
    for row, plan in plans:
        if plan.errors:
            summary.skipped += 1
            summary.validation_errors += 1
            summary.failures.append(f"{row.sku}: planning error: {'; '.join(plan.errors)}")
            continue
        try:
            importer.execute(plan)
            n_copied = len(plan.copies)
            summary.images_copied += n_copied
            if plan.operation == "CREATE":
                summary.created += 1
                log.info("SKU %s: CREATED product id %s (%d image(s) copied)",
                         row.sku, plan.product_id, n_copied)
            elif plan.has_changes:
                summary.updated += 1
                log.info("SKU %s: UPDATED product id %s (%d change(s), %d image(s) copied)",
                         row.sku, plan.product_id, len(plan.actions), n_copied)
            else:
                summary.unchanged += 1
                log.info("SKU %s: no changes (idempotent re-run)", row.sku)
        except Exception as exc:
            summary.failed += 1
            summary.database_errors += 1
            msg = f"{row.sku}: FAILED and rolled back: {exc}"
            summary.failures.append(msg)
            log.error("%s", msg)
            log.debug("traceback:", exc_info=True)

    db.close()
    print(summary.render())
    return 1 if (summary.failed or summary.skipped) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
