"""Manufacturer via the CSV `manufacturer_id` column.

Covers: CSV parsing (single id, pipe rejected, non-numeric, empty vs absent),
CREATE with link + has_manufacturers=1, unknown-id errors, UPDATE widening
(never narrowing), and idempotency.
"""
from __future__ import annotations

import pytest

from vmimporter.importer import ProductImporter
from vmimporter.products_csv import ProductRow, ValidationError, parse_csv


def make_row(sku="NEW1", **kw) -> ProductRow:
    defaults = {
        "row_number": 1, "sku": sku,
        "title_en": "Tights NEW1 Pro", "description_en": "<p>Pro tights.</p>",
        "title_el": "Κολάν NEW1 Pro", "description_el": "<p>Κολάν pro.</p>",
        "price_raw": "35.90", "price_net": 35.90,
        "sizes": [], "colours": [], "fabric": [],
    }
    defaults.update(kw)
    return ProductRow(**defaults)


def make_importer(vm_db, cfg) -> ProductImporter:
    return ProductImporter(vm_db, cfg)


def write_csv(tmp_path, header, body) -> str:
    p = tmp_path / "products.csv"
    p.write_text(header + "\n" + body, encoding="utf-8")
    return str(p)


HEADER_BASE = "sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric"


# ------------------------------------------------------------------ CSV parsing


def test_parse_manufacturer_id_single(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",manufacturer_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,16')
    rows, _ = parse_csv(p)
    assert rows[0].manufacturer_id == 16


def test_parse_manufacturer_id_absent_column(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE,
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,')
    rows, _ = parse_csv(p)
    assert rows[0].manufacturer_id is None


def test_parse_manufacturer_id_empty_cell(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",manufacturer_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,""')
    rows, _ = parse_csv(p)
    assert rows[0].manufacturer_id is None


def test_parse_manufacturer_id_pipe_rejected(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",manufacturer_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,15|16')
    with pytest.raises(ValidationError) as exc:
        parse_csv(p)
    assert any("single id" in pr for pr in exc.value.problems)


def test_parse_manufacturer_id_non_numeric_rejected(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",manufacturer_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,SoDanca')
    with pytest.raises(ValidationError) as exc:
        parse_csv(p)
    assert any("not a manufacturer id" in pr for pr in exc.value.problems)


# ------------------------------------------------------------------ CREATE flow


def test_create_with_manufacturer(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(manufacturer_id=16)
    plan = imp.build_plan(row)
    assert plan.operation == "CREATE"
    assert not plan.errors
    mf_actions = [a for a in plan.actions if a.kind == "insert_mf_link"]
    assert len(mf_actions) == 1
    assert mf_actions[0].payload["manufacturer_id"] == 16
    assert "SoDanca" in mf_actions[0].description
    imp.execute(plan)

    pid = plan.product_id
    core = vm_db.query_one(
        "SELECT has_manufacturers FROM xhngw_virtuemart_products WHERE virtuemart_product_id=?",
        (pid,))
    assert core["has_manufacturers"] == 1
    link = vm_db.query_one(
        "SELECT virtuemart_manufacturer_id FROM xhngw_virtuemart_product_manufacturers "
        "WHERE virtuemart_product_id=?", (pid,))
    assert link["virtuemart_manufacturer_id"] == 16

    # idempotent re-run: no duplicate link
    plan2 = imp.build_plan(make_row(sku="NEW1", manufacturer_id=16))
    assert plan2.operation == "UPDATE"
    assert not [a for a in plan2.actions if a.kind == "insert_mf_link"]


def test_create_without_manufacturer(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(manufacturer_id=None)
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind == "insert_mf_link"]
    imp.execute(plan)
    core = vm_db.query_one(
        "SELECT has_manufacturers FROM xhngw_virtuemart_products WHERE product_sku='NEW1'")
    assert core["has_manufacturers"] == 0


def test_create_unknown_manufacturer_errors(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(manufacturer_id=999)
    plan = imp.build_plan(row)
    assert plan.errors
    assert "999" in plan.errors[0]
    assert not [a for a in plan.actions if a.kind == "insert_mf_link"]


# ------------------------------------------------------------------ UPDATE flow


def test_update_adds_manufacturer_never_removes(vm_db, cfg):
    """CD004 (494) has manufacturer 15. A row with manufacturer_id=16 adds the
    link; a row with an EMPTY cell keeps 15 untouched."""
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   manufacturer_id=16)
    plan = imp.build_plan(row)
    mf_actions = [a for a in plan.actions if a.kind == "insert_mf_link"]
    assert [(a.payload["manufacturer_id"]) for a in mf_actions] == [16]
    imp.execute(plan)
    links = vm_db.query_all(
        "SELECT virtuemart_manufacturer_id FROM xhngw_virtuemart_product_manufacturers "
        "WHERE virtuemart_product_id=494 ORDER BY id")
    assert [l["virtuemart_manufacturer_id"] for l in links] == [15, 16]
    core = vm_db.query_one(
        "SELECT has_manufacturers FROM xhngw_virtuemart_products WHERE virtuemart_product_id=494")
    assert core["has_manufacturers"] == 1


def test_update_empty_cell_keeps_existing_manufacturer(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   manufacturer_id=None)
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind == "insert_mf_link"]
    imp.execute(plan)
    links = vm_db.query_all(
        "SELECT virtuemart_manufacturer_id FROM xhngw_virtuemart_product_manufacturers "
        "WHERE virtuemart_product_id=494")
    assert [l["virtuemart_manufacturer_id"] for l in links] == [15]


def test_update_unknown_manufacturer_errors(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   manufacturer_id=999)
    plan = imp.build_plan(row)
    assert plan.errors
    assert "999" in plan.errors[0]


def test_update_flips_has_manufacturers_flag_when_missing(vm_db, cfg):
    vm_db.execute(
        "UPDATE xhngw_virtuemart_products SET has_manufacturers=0 "
        "WHERE virtuemart_product_id=494")
    vm_db.execute("DELETE FROM xhngw_virtuemart_product_manufacturers "
                  "WHERE virtuemart_product_id=494")
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   manufacturer_id=15)
    plan = imp.build_plan(row)
    imp.execute(plan)
    core = vm_db.query_one(
        "SELECT has_manufacturers FROM xhngw_virtuemart_products "
        "WHERE virtuemart_product_id=494")
    assert core["has_manufacturers"] == 1
