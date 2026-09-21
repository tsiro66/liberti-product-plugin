"""Per-product categories from the CSV `category_id` column.

Covers: CSV parsing (pipe-split, dedupe, non-numeric, empty vs missing),
CREATE with multiple categories, CLI-flag fallback, empty-cell override,
unknown-id errors, UPDATE widening (never narrowing), and idempotency.
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


def test_parse_category_ids_pipe_split(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",category_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,"62|65"')
    rows, warnings = parse_csv(p)
    assert rows[0].category_ids == [62, 65]
    assert warnings == []


def test_parse_category_ids_absent_column_is_none(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE,
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,')
    rows, _ = parse_csv(p)
    assert rows[0].category_ids is None


def test_parse_category_ids_empty_cell_is_empty_list(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",category_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,""')
    rows, _ = parse_csv(p)
    assert rows[0].category_ids == []


def test_parse_category_ids_non_numeric_is_error(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",category_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,Latin')
    with pytest.raises(ValidationError) as exc:
        parse_csv(p)
    assert any("not a category id" in pr for pr in exc.value.problems)


def test_parse_category_ids_duplicate_warns(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",category_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,,"62|62|65"')
    rows, warnings = parse_csv(p)
    assert rows[0].category_ids == [62, 65]
    assert any("duplicate category_id" in w for w in warnings)


def test_parse_category_ids_whitespace_tolerated(tmp_path):
    p = write_csv(tmp_path, HEADER_BASE + ",category_id",
                  'NEW1,Tights,<p>t</p>,Κολάν,<p>κ</p>,35.90,,,," 62 | 65 "')
    rows, _ = parse_csv(p)
    assert rows[0].category_ids == [62, 65]
    rows, _ = parse_csv(p)
    assert rows[0].category_ids == [62, 65]


# ------------------------------------------------------------------ CREATE flow


def test_create_with_multiple_categories(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(category_ids=[62, 65])
    plan = imp.build_plan(row)
    assert plan.operation == "CREATE"
    assert not plan.errors
    cat_actions = [a for a in plan.actions if a.kind == "insert_cat_link"]
    assert [(a.payload["category_id"]) for a in cat_actions] == [62, 65]
    assert "Latin" in cat_actions[0].description       # name shown for eyeballing
    assert "Ballroom Various" in cat_actions[1].description
    imp.execute(plan)

    pid = plan.product_id
    core = vm_db.query_one(
        "SELECT has_categories FROM xhngw_virtuemart_products WHERE virtuemart_product_id=?",
        (pid,))
    assert core["has_categories"] == 1
    links = vm_db.query_all(
        "SELECT virtuemart_category_id, ordering FROM xhngw_virtuemart_product_categories "
        "WHERE virtuemart_product_id=? ORDER BY id", (pid,))
    assert [l["virtuemart_category_id"] for l in links] == [62, 65]
    assert all(l["ordering"] == 0 for l in links)

    # idempotent re-run: no new links
    plan2 = imp.build_plan(make_row(sku="NEW1", category_ids=[62, 65]))
    assert plan2.operation == "UPDATE"
    cat_updates = [a for a in plan2.actions if a.kind == "insert_cat_link"]
    assert cat_updates == []


def test_create_without_any_category(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(category_ids=[])
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind == "insert_cat_link"]
    imp.execute(plan)
    core = vm_db.query_one(
        "SELECT has_categories FROM xhngw_virtuemart_products WHERE product_sku='NEW1'")
    assert core["has_categories"] == 0


def test_create_unknown_category_id_errors(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(category_ids=[62, 9999])
    plan = imp.build_plan(row)
    assert plan.errors
    assert "9999" in plan.errors[0]
    # no category link action planned for the broken row
    assert not [a for a in plan.actions if a.kind == "insert_cat_link"]


# ------------------------------------------------------------------ CLI fallback


def test_cli_flag_applies_when_column_absent(vm_db, cfg):
    cfg.category_id = 61
    imp = make_importer(vm_db, cfg)
    row = make_row(category_ids=None)
    plan = imp.build_plan(row)
    cat_actions = [a for a in plan.actions if a.kind == "insert_cat_link"]
    assert [(a.payload["category_id"]) for a in cat_actions] == [61]


def test_empty_csv_cell_overrides_cli_flag(vm_db, cfg):
    cfg.category_id = 61
    imp = make_importer(vm_db, cfg)
    row = make_row(category_ids=[])
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind == "insert_cat_link"]
    imp.execute(plan)
    core = vm_db.query_one(
        "SELECT has_categories FROM xhngw_virtuemart_products WHERE product_sku='NEW1'")
    assert core["has_categories"] == 0


def test_csv_column_overrides_cli_flag(vm_db, cfg):
    cfg.category_id = 61
    imp = make_importer(vm_db, cfg)
    row = make_row(category_ids=[62])
    plan = imp.build_plan(row)
    cat_actions = [a for a in plan.actions if a.kind == "insert_cat_link"]
    assert [(a.payload["category_id"]) for a in cat_actions] == [62]


# ------------------------------------------------------------------ UPDATE flow


def test_update_widens_categories_never_narrows(vm_db, cfg):
    """CD004 (id 494) is linked to category 62 only. A CSV row that lists
    62|61 adds 61; a row listing 61 alone must NOT remove 62."""
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   category_ids=[62, 61])
    plan = imp.build_plan(row)
    cat_actions = [a for a in plan.actions if a.kind == "insert_cat_link"]
    assert [(a.payload["category_id"]) for a in cat_actions] == [61]
    imp.execute(plan)
    links = vm_db.query_all(
        "SELECT virtuemart_category_id FROM xhngw_virtuemart_product_categories "
        "WHERE virtuemart_product_id=494 ORDER BY id")
    assert [l["virtuemart_category_id"] for l in links] == [62, 61]

    # narrowing attempt: 61 alone -> nothing removed, nothing added
    plan2 = imp.build_plan(make_row(sku="CD004", price_raw="77.82258",
                                    price_net=77.82258, category_ids=[61]))
    assert not [a for a in plan2.actions if a.kind == "insert_cat_link"]
    assert not [a for a in plan2.actions if a.kind == "delete_cat_link"]


def test_update_empty_cell_touches_nothing(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   category_ids=[])
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind == "insert_cat_link"]
    assert not [a for a in plan.actions if a.kind == "delete_cat_link"]


def test_update_unknown_category_id_errors(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   category_ids=[9999])
    plan = imp.build_plan(row)
    assert plan.errors
    assert "9999" in plan.errors[0]


# ------------------------------------------------------------------ has_categories flag fix


def test_update_sets_has_categories_flag_when_missing(vm_db, cfg):
    """Product exists with has_categories=0; adding a link flips the flag."""
    vm_db.execute(
        "UPDATE xhngw_virtuemart_products SET has_categories=0 "
        "WHERE virtuemart_product_id=494")
    vm_db.execute("DELETE FROM xhngw_virtuemart_product_categories "
                  "WHERE virtuemart_product_id=494")
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="CD004", price_raw="77.82258", price_net=77.82258,
                   category_ids=[62])
    plan = imp.build_plan(row)
    imp.execute(plan)
    core = vm_db.query_one(
        "SELECT has_categories FROM xhngw_virtuemart_products WHERE virtuemart_product_id=494")
    assert core["has_categories"] == 1
