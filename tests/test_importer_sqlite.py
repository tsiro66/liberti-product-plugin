"""Integration tests: full plan/execute flow against a sqlite copy of the
relevant VirtueMart tables, seeded with the real CD004 data.

These verify the exact database shapes established in
virtuemart-database-analysis.md and the importer's safety properties
(dry-run purity, idempotency, rollback, owned-fields-only updates).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import (
    CD004_EL_DESC,
    CD004_EL_NAME,
    CD004_EN_DESC,
    CD004_EN_NAME,
)
from vmimporter.config import (
    CURRENCY_ID,
    CUSTOMFIELD_PARAMS,
    PRODUCT_PARAMS_DEFAULT,
    TAX_CALC_ID,
)
from vmimporter.importer import ProductImporter
from vmimporter.products_csv import ProductRow


def make_row(sku="CD004", **kw) -> ProductRow:
    defaults = {
        "row_number": 1, "sku": sku,
        "title_en": CD004_EN_NAME, "description_en": CD004_EN_DESC,
        "title_el": CD004_EL_NAME, "description_el": CD004_EL_DESC,
        "price_raw": "77.82258", "sizes": [], "colours": [], "fabric": [],
    }
    defaults.update(kw)
    return ProductRow(**defaults)


def make_importer(vm_db, cfg) -> ProductImporter:
    return ProductImporter(vm_db, cfg)


def counts(db):
    def q(sql):
        return db.scalar(sql)
    return {
        "products": q("SELECT COUNT(*) FROM xhngw_virtuemart_products"),
        "en": q("SELECT COUNT(*) FROM xhngw_virtuemart_products_en_gb"),
        "el": q("SELECT COUNT(*) FROM xhngw_virtuemart_products_el_gr"),
        "prices": q("SELECT COUNT(*) FROM xhngw_virtuemart_product_prices"),
        "cf": q("SELECT COUNT(*) FROM xhngw_virtuemart_product_customfields"),
        "media": q("SELECT COUNT(*) FROM xhngw_virtuemart_medias"),
        "links": q("SELECT COUNT(*) FROM xhngw_virtuemart_product_medias"),
    }


# ---------------------------------------------------------------- CD004 update


def test_identical_update_is_noop(vm_db, cfg):
    """Feeding CD004's own data back must produce zero actions."""
    imp = make_importer(vm_db, cfg)
    before = counts(vm_db)
    row = make_row(price_raw="77.82258", price_net=77.82258,
                   sizes=["35", "36", "37", "38", "39", "40", "41", "42"],
                   colours=["BLK"])
    plan = imp.build_plan(row)
    assert plan.operation == "UPDATE"
    assert plan.product_id == 494
    assert plan.actions == []
    assert not plan.has_changes
    imp.execute(plan)  # must not start a transaction / write anything
    assert counts(vm_db) == before


def test_update_diffs_and_preserves_unowned_data(vm_db, cfg, tmp_path):
    """Price/size/colour/fabric changes apply; heel (custom 18), published,
    slug, language SEO fields and manufacturers stay untouched."""
    imp = make_importer(vm_db, cfg)
    row = make_row(
        price_raw="80", price_net=80.0,
        sizes=["36", "37", "38", "39", "40", "41", "42", "43"],  # 35 removed, 43 added
        colours=["BLK", "RED"],
        fabric=["Cotton"],
    )
    plan = imp.build_plan(row)
    imp.execute(plan)

    # price updated on the SAME row, net value kept exact
    price = vm_db.query_one(
        "SELECT * FROM xhngw_virtuemart_product_prices WHERE virtuemart_product_id=494")
    assert price["virtuemart_product_price_id"] == 1417
    assert price["product_price"] == pytest.approx(80.0)
    assert price["product_tax_id"] == 0          # untouched on update
    assert price["product_currency"] == 47

    cf = vm_db.query_all(
        "SELECT virtuemart_custom_id, customfield_value, customfield_price, published "
        "FROM xhngw_virtuemart_product_customfields WHERE virtuemart_product_id=494 "
        "ORDER BY virtuemart_custom_id, customfield_value")
    by_custom = {}
    for r in cf:
        by_custom.setdefault(r["virtuemart_custom_id"], []).append(r["customfield_value"])
    assert by_custom[6] == ["36", "37", "38", "39", "40", "41", "42", "43"]
    assert by_custom[7] == ["BLK", "RED"]
    assert by_custom[10] == ["Cotton"]
    assert by_custom[18] == ["9.0cm Plated Heel"]          # unowned field preserved
    for r in cf:
        assert r["customfield_price"] == 0                 # DB convention
        assert r["published"] == 0                         # DB convention

    core = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products WHERE virtuemart_product_id=494")
    assert core["published"] == 1                          # preserved
    en = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products_en_gb WHERE virtuemart_product_id=494")
    assert en["slug"] == "cd004"                           # preserved
    assert en["customtitle"] == CD004_EN_NAME              # SEO fields preserved
    # identical title/desc -> no language UPDATE happened, modified_on untouched


def test_update_language_and_missing_lang_row(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(title_en="Go Dance CD004 (new cut)",
                   description_en="<p>Updated.</p>", short_desc_en="Short.")
    plan = imp.build_plan(row)
    kinds = {(a.kind, a.payload.get("lang")) for a in plan.actions}
    assert ("update_lang", "en_gb") in kinds
    imp.execute(plan)
    en = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products_en_gb WHERE virtuemart_product_id=494")
    assert en["product_name"] == "Go Dance CD004 (new cut)"
    assert en["product_desc"] == "<p>Updated.</p>"
    assert en["product_s_desc"] == "Short."
    assert en["slug"] == "cd004"                            # never changed
    el = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products_el_gr WHERE virtuemart_product_id=494")
    assert el["product_name"] == CD004_EL_NAME              # el unchanged by en diff

    # missing-language-row repair: delete el row, re-import
    vm_db.execute("DELETE FROM xhngw_virtuemart_products_el_gr WHERE virtuemart_product_id=494")
    plan2 = imp.build_plan(row)
    assert any(a.kind == "insert_lang" and a.payload["lang"] == "el_gr" for a in plan2.actions)
    imp.execute(plan2)
    el2 = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products_el_gr WHERE virtuemart_product_id=494")
    assert el2 is not None and el2["slug"] == "cd004"


# ---------------------------------------------------------------- images


def test_media_ordering_and_keep_unmanaged(vm_db, cfg, tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "CD004 New 1.jpg").write_bytes(b"new1")
    (images / "CD004 New 2.jpg").write_bytes(b"new2")

    cfg.vm_media_dir = str(tmp_path / "servermedia")
    imp = make_importer(vm_db, cfg)
    row = make_row(images=[images / "CD004 New 2.jpg", images / "CD004 New 1.jpg"])
    plan = imp.build_plan(row)
    imp.execute(plan)

    links = vm_db.query_all(
        "SELECT pm.ordering, m.file_url FROM xhngw_virtuemart_product_medias pm "
        "JOIN xhngw_virtuemart_medias m ON m.virtuemart_media_id=pm.virtuemart_media_id "
        "WHERE pm.virtuemart_product_id=494 ORDER BY pm.ordering")
    urls = [l["file_url"] for l in links]
    # CSV images first (natural order), then the 3 pre-existing ones, nothing deleted
    assert urls == [
        "images/stories/virtuemart/product/CD004 New 1.jpg",
        "images/stories/virtuemart/product/CD004 New 2.jpg",
        "images/stories/virtuemart/product/CD004 Black 0.jpg",
        "images/stories/virtuemart/product/CD004 Black A.jpg",
        "images/stories/virtuemart/product/CD004 Black.jpg",
    ]
    assert len(links) == 5
    # files physically copied, existing server files not touched
    assert (Path(cfg.vm_media_dir) / "CD004 New 1.jpg").read_bytes() == b"new1"
    # media row shape matches CD004's existing rows
    m = vm_db.query_one(
        "SELECT * FROM xhngw_virtuemart_medias WHERE file_url LIKE '%CD004 New 1.jpg'")
    assert m["file_type"] == "product"
    assert m["file_mimetype"] == "image/jpeg"
    assert m["file_url_thumb"] == ""
    assert m["published"] == 1
    assert m["is_image"] == 1
    assert m["file_meta"] == CD004_EN_NAME  # first image carries the EN title

    # idempotent rerun: no changes at all
    plan2 = imp.build_plan(make_row(images=[images / "CD004 New 1.jpg", images / "CD004 New 2.jpg"]))
    media_ops = [a for a in plan2.actions if a.kind in ("insert_media", "insert_link", "update_link")]
    assert media_ops == []


def test_missing_image_does_not_break_import(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(price_raw="81", price_net=81.0, images=[])
    plan = imp.build_plan(row)
    assert plan.has_changes and not plan.errors
    imp.execute(plan)
    price = vm_db.query_one("SELECT product_price FROM xhngw_virtuemart_product_prices "
                            "WHERE virtuemart_product_id=494")
    assert price["product_price"] == pytest.approx(81.0)


# ---------------------------------------------------------------- CREATE


def test_create_new_product_full_cd004_shape(vm_db, cfg, tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "NEW1 Black.jpg").write_bytes(b"a")
    (images / "NEW1 Blue.jpg").write_bytes(b"b")
    cfg.vm_media_dir = str(tmp_path / "servermedia")
    cfg.category_id = 62

    imp = make_importer(vm_db, cfg)
    row = ProductRow(
        row_number=2, sku="NEW1",
        title_en="Tights NEW1 Pro", description_en="<p>Pro tights.</p>",
        title_el="Κολάν NEW1 Pro", description_el="<p>Κολάν pro.</p>",
        price_raw="96.50", price_net=96.50,
        sizes=["36", "38", "40"], colours=["BLK", "NAVY"], fabric=[],
        short_desc_en="Pro.", short_desc_el="Pro el.",
        images=[images / "NEW1 Black.jpg", images / "NEW1 Blue.jpg"],
    )
    plan = imp.build_plan(row)
    assert plan.operation == "CREATE"
    imp.execute(plan)

    pid = plan.product_id
    assert pid and pid != 494

    core = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products WHERE virtuemart_product_id=?", (pid,))
    assert core["published"] == 0                      # imported products are hidden
    assert core["product_sku"] == "NEW1"
    assert core["product_gtin"] == "NEW1"              # CD004 convention
    assert core["product_params"] == PRODUCT_PARAMS_DEFAULT
    assert core["virtuemart_vendor_id"] == 1
    assert core["product_parent_id"] == 0
    assert (core["has_prices"], core["has_medias"], core["has_categories"]) == (1, 1, 1)
    assert core["has_manufacturers"] == 0
    assert core["product_stockhandle"] == "0"

    for lang, name, desc, sdesc in (
        ("en_gb", "Tights NEW1 Pro", "<p>Pro tights.</p>", "Pro."),
        ("el_gr", "Κολάν NEW1 Pro", "<p>Κολάν pro.</p>", "Pro el."),
    ):
        r = vm_db.query_one(f"SELECT * FROM xhngw_virtuemart_products_{lang} WHERE virtuemart_product_id=?", (pid,))
        assert r["product_name"] == name
        assert r["product_desc"] == desc
        assert r["product_s_desc"] == sdesc
        assert r["slug"] == "tights-new1-pro"          # EN-derived, shared
        assert r["metadesc"] == sdesc                  # CD004 convention
        assert r["customtitle"] == name

    price = vm_db.query_one("SELECT * FROM xhngw_virtuemart_product_prices WHERE virtuemart_product_id=?", (pid,))
    assert price["product_price"] == pytest.approx(96.50)
    assert price["product_tax_id"] == TAX_CALC_ID
    assert price["product_currency"] == CURRENCY_ID
    assert price["virtuemart_shoppergroup_id"] == 0

    cfs = vm_db.query_all("SELECT * FROM xhngw_virtuemart_product_customfields WHERE virtuemart_product_id=?", (pid,))
    got = {(r["virtuemart_custom_id"], r["customfield_value"]) for r in cfs}
    assert got == {(6, "36"), (6, "38"), (6, "40"), (7, "BLK"), (7, "NAVY")}
    for r in cfs:
        assert r["customfield_params"] == CUSTOMFIELD_PARAMS
        assert r["customfield_price"] == 0
        assert r["published"] == 0
        assert r["ordering"] == 0
        assert r["disabler"] == r["override"] == r["noninheritable"] == 0

    links = vm_db.query_all(
        "SELECT pm.ordering, m.file_url, m.file_type FROM xhngw_virtuemart_product_medias pm "
        "JOIN xhngw_virtuemart_medias m ON m.virtuemart_media_id=pm.virtuemart_media_id "
        "WHERE pm.virtuemart_product_id=? ORDER BY pm.ordering", (pid,))
    assert [l["file_url"] for l in links] == [
        "images/stories/virtuemart/product/NEW1 Black.jpg",
        "images/stories/virtuemart/product/NEW1 Blue.jpg",
    ]
    assert all(l["file_type"] == "product" for l in links)
    assert (Path(cfg.vm_media_dir) / "NEW1 Black.jpg").exists()

    cat = vm_db.query_one("SELECT * FROM xhngw_virtuemart_product_categories WHERE virtuemart_product_id=?", (pid,))
    assert cat["virtuemart_category_id"] == 62 and cat["ordering"] == 0

    # rerun of identical data: no duplicate anything
    before = counts(vm_db)
    plan2 = imp.build_plan(row)
    assert plan2.operation == "UPDATE"
    assert not plan2.has_changes
    imp.execute(plan2)
    assert counts(vm_db) == before


def test_create_without_category_and_images(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="NEW2", title_en="Belt NEW2", description_en="<p>b</p>",
                   title_el="Ζώνη NEW2", description_el="<p>ζ</p>",
                   price_raw="10,50", price_net=10.50)
    plan = imp.build_plan(row)
    imp.execute(plan)
    core = vm_db.query_one("SELECT * FROM xhngw_virtuemart_products WHERE product_sku='NEW2'")
    assert core["has_categories"] == 0
    assert core["has_medias"] == 0
    assert core["published"] == 0


def test_create_refuses_case_variant_of_existing_sku(vm_db, cfg):
    """A case-variant SKU must NOT create a duplicate: the importer matches
    case-insensitively and updates the existing product (SKU spelling in the
    DB is preserved)."""
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="cd004", price_raw="95", price_net=95.0)
    plan = imp.build_plan(row)
    assert plan.operation == "UPDATE"
    assert plan.product_id == 494
    imp.execute(plan)
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_products") == 1
    assert vm_db.scalar("SELECT product_sku FROM xhngw_virtuemart_products") == "CD004"


def test_sku_lookup_case_insensitive_update(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    row = make_row(sku="cd004", price_raw="90", price_net=90.0)
    plan = imp.build_plan(row)
    assert plan.product_id == 494
    assert plan.note and "case-insensitively" in plan.note
    imp.execute(plan)
    price = vm_db.query_one("SELECT product_price FROM xhngw_virtuemart_product_prices "
                            "WHERE virtuemart_product_id=494")
    assert price["product_price"] == pytest.approx(90.0)


# ---------------------------------------------------------------- safety


def test_dry_run_never_writes(vm_db, cfg, tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "NEW1 Black.jpg").write_bytes(b"a")
    cfg.vm_media_dir = str(tmp_path / "servermedia")
    imp = make_importer(vm_db, cfg)
    before = counts(vm_db)

    row = make_row(price_raw="99", price_net=99.0, sizes=["33"], colours=["WHITE"],
                   images=[images / "NEW1 Black.jpg"])
    plan = imp.build_plan(row)
    assert plan.has_changes
    # build_plan must not write; execute is simply never called
    assert counts(vm_db) == before
    assert plan.copies        # copy planned, not performed
    assert not (Path(cfg.vm_media_dir)).exists()


def test_rollback_on_failure_leaves_no_partial_product(vm_db, cfg):
    imp = make_importer(vm_db, cfg)
    before = counts(vm_db)
    row = make_row(sku="NEWX", title_en="X", description_en="<p>x</p>",
                   title_el="X", description_el="<p>x</p>",
                   price_raw="5", price_net=5.0, sizes=["36"], colours=["BLK"])

    original = imp.customfields.insert
    calls = {"n": 0}

    def exploding_insert(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated DB failure")
        return original(*a, **kw)

    imp.customfields.insert = exploding_insert
    plan = imp.build_plan(row)
    with pytest.raises(RuntimeError):
        imp.execute(plan)
    assert counts(vm_db) == before          # fully rolled back

    # and the same row can be imported after the failure is fixed
    imp.customfields.insert = original
    plan2 = imp.build_plan(row)
    imp.execute(plan2)
    assert vm_db.query_one("SELECT virtuemart_product_id FROM xhngw_virtuemart_products "
                           "WHERE product_sku='NEWX'") is not None


def test_set_published_forces_state_on_unchanged_product(vm_db, cfg):
    """--set-published applies even when the row is otherwise identical."""
    cfg.set_published = 0
    imp = make_importer(vm_db, cfg)
    row = make_row(price_raw="77.82258", price_net=77.82258,
                   sizes=["35", "36", "37", "38", "39", "40", "41", "42"],
                   colours=["BLK"])
    plan = imp.build_plan(row)
    assert any(a.kind == "update_core" for a in plan.actions)
    imp.execute(plan)
    core = vm_db.query_one("SELECT published FROM xhngw_virtuemart_products WHERE virtuemart_product_id=494")
    assert core["published"] == 0


def test_unrelated_customfields_of_other_products_untouched(vm_db, cfg):
    """Deletions are scoped to (product, custom_id) — other products' rows stay."""
    imp = make_importer(vm_db, cfg)
    row = make_row(sizes=["36"])   # only sizes provided -> 35 removed, colours/fabric untouched
    plan = imp.build_plan(row)
    imp.execute(plan)
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_product_customfields "
                        "WHERE virtuemart_custom_id=7 AND virtuemart_product_id=494") == 1
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_product_customfields "
                        "WHERE virtuemart_custom_id=18 AND virtuemart_product_id=494") == 1


def test_empty_csv_field_leaves_existing_values(vm_db, cfg):
    """Empty sizes cell = 'not provided' -> nothing removed, nothing added."""
    imp = make_importer(vm_db, cfg)
    row = make_row(price_raw="82", price_net=82.0)   # all multi-value cells empty
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind in ("insert_cf", "delete_cf")]
    imp.execute(plan)
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_product_customfields "
                        "WHERE virtuemart_product_id=494 AND virtuemart_custom_id=6") == 8
