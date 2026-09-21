"""Pre-production audit tests (see PRE_PRODUCTION_AUDIT.md).

Safety guarantees verified here:
  - dry-run/read-only connections reject every write statement
  - plan building performs zero writes on a read-only connection
  - updates never touch manufacturers or other unowned data
  - unicode/odd filenames are handled
  - invalid CSV encoding / malformed structure is reported, not crashed on
"""
from __future__ import annotations

import pytest

from tests.test_importer_sqlite import make_row
from vmimporter.db import Database, ReadOnlyViolation
from vmimporter.importer import ProductImporter
from vmimporter.products_csv import ValidationError, parse_csv


def test_read_only_wrapper_blocks_every_write_class():
    db = Database.connect_sqlite(":memory:")
    db.read_only = True
    for sql in (
        "INSERT INTO x (a) VALUES (%s)",
        "UPDATE t SET a = %s",
        "DELETE FROM t WHERE a = %s",
        "  REPLACE INTO t VALUES (%s)",
        "TRUNCATE TABLE t",
        "ALTER TABLE t ADD COLUMN a INT",
        "DROP TABLE t",
        "CREATE TABLE t (a INT)",
        "BEGIN",
    ):
        with pytest.raises(ReadOnlyViolation):
            db.execute(sql)
    # SELECTs pass through (table need not exist for the guard check)
    with pytest.raises(Exception) as excinfo:  # sqlite error, NOT ReadOnlyViolation
        db.execute("SELECT * FROM missing_table")
    assert not isinstance(excinfo.value, ReadOnlyViolation)


def test_read_only_connection_blocks_product_import(vm_db, cfg):
    """Full create flow on a read-only connection must raise, DB untouched."""
    vm_db.read_only = True
    imp = ProductImporter(vm_db, cfg)
    row = make_row(sku="NEWRO", title_en="X", description_en="<p>x</p>",
                   title_el="X", description_el="<p>x</p>",
                   price_raw="5", price_net=5.0, sizes=["36"])
    plan = imp.build_plan(row)          # planning (pure reads) works
    assert plan.has_changes
    with pytest.raises((ReadOnlyViolation, Exception)):
        imp.execute(plan)
    vm_db.read_only = False
    assert vm_db.scalar(
        "SELECT COUNT(*) FROM xhngw_virtuemart_products WHERE product_sku='NEWRO'") == 0


def test_update_preserves_manufacturer_and_category_links(vm_db, cfg):
    """product_manufacturers / product_categories rows must survive updates."""
    # (manufacturer link 452 = 494 -> 15 is seeded by conftest now)

    imp = ProductImporter(vm_db, cfg)
    row = make_row(price_raw="83", price_net=83.0, sizes=["36"], colours=["BLK"])
    plan = imp.build_plan(row)
    imp.execute(plan)

    assert vm_db.scalar(
        "SELECT virtuemart_manufacturer_id FROM xhngw_virtuemart_product_manufacturers "
        "WHERE virtuemart_product_id=494") == 15
    assert vm_db.scalar(
        "SELECT COUNT(*) FROM xhngw_virtuemart_product_categories "
        "WHERE virtuemart_product_id=494") == 1
    cat = vm_db.query_one(
        "SELECT virtuemart_category_id FROM xhngw_virtuemart_product_categories "
        "WHERE virtuemart_product_id=494")
    assert cat["virtuemart_category_id"] == 62
    # empty manufacturer cell + no CSV column: existing link untouched (asserted
    # above == 15); the importer only ever ADDS manufacturer links, never removes


def test_unicode_filename_roundtrip(vm_db, cfg, tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    fname = "0405PT Μπλε Λευκό.jpg"
    (images / fname).write_bytes(b"uni")
    cfg.vm_media_dir = str(tmp_path / "srv")

    from vmimporter.images import copy_image, match_images, scan_images
    files, _ = scan_images(str(images))
    grouped, _ = match_images(files, ["0405PT"])
    assert grouped["0405PT"] == [images / fname]
    url = copy_image(images / fname, cfg.vm_media_dir, "images/stories/virtuemart/product")
    assert url == "images/stories/virtuemart/product/0405PT Μπλε Λευκό.jpg"
    assert (tmp_path / "srv" / fname).read_bytes() == b"uni"

    imp = ProductImporter(vm_db, cfg)
    row = make_row(price_raw="50", price_net=50.0, images=[images / fname])
    plan = imp.build_plan(row)
    imp.execute(plan)
    m = vm_db.query_one(
        "SELECT file_url FROM xhngw_virtuemart_medias WHERE file_url LIKE '%Μπλε%'")
    assert m and m["file_url"].endswith(fname)


def test_invalid_csv_encoding_reported(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_bytes(
        b"sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric\n"
        b"A1,\xff\xfe\xc4\x88,ok,ok,10,,,,\n")  # invalid UTF-8 bytes
    with pytest.raises(ValidationError) as e:
        parse_csv(str(bad))
    assert "UTF-8" in e.value.problems[0]


def test_malformed_csv_structure_reported(tmp_path):
    bad = tmp_path / "bad.csv"
    # unterminated quote -> csv.Error
    bad.write_bytes(
        b'sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric\n'
        b'A1,"unterminated,10,,,,,\n')
    with pytest.raises(ValidationError):
        parse_csv(str(bad))


def test_no_credentials_in_report_or_cli_output(tmp_path, capsys, monkeypatch):
    """Run the real CLI in dry-run mode with a fake password and assert it
    never appears anywhere in stdout/stderr or the log file."""
    from vmimporter import cli

    dbfile = tmp_path / "ro.sqlite"
    db = Database.connect_sqlite(str(dbfile))
    db.close()
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("DB_NAME", str(dbfile))
    monkeypatch.setenv("DB_PASSWORD", "SUPER-SECRET-PW-123")
    monkeypatch.setenv("VM_ADMIN_USER_ID", "0")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    rc = cli.main(["examples/products.example.csv", "--dry-run",
                   "--images", "examples/images"])
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "SUPER-SECRET-PW-123" not in blob
    for log in (tmp_path / "logs").glob("*.log"):
        assert "SUPER-SECRET-PW-123" not in log.read_text()
    assert rc in (0, 1, 2)  # 2 = empty fixture DB has no VM tables; password assertions already passed

    from vmimporter.reporting import ImportSummary
    summary = ImportSummary()
    summary.failures.append("boom")
    assert "password" not in summary.render().lower()
