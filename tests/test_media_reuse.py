"""Media-row reuse on re-import.

Real-world case (2026-09-21): products 102/1130 were imported, deleted in the
admin, then re-imported. Deleting a product keeps its `virtuemart_medias` rows
and its files on disk, so the second import planned INSERT_MEDIA again and
created duplicate media rows for the same file_url. The importer must instead
REUSE the existing media row and only (re)create the product link.

Seeds mirror that state: orphaned media rows exist, no product links.
"""
from __future__ import annotations

from vmimporter.importer import ProductImporter
from vmimporter.products_csv import ProductRow


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


def seed_orphan_media(vm_db, media_id: int, filename: str) -> None:
    """A medias row whose product was deleted: file exists, no links point here."""
    url = f"images/stories/virtuemart/product/{filename}"
    vm_db.execute(
        "INSERT INTO xhngw_virtuemart_medias VALUES ("
        "?, 1, ?, '', '', '', 'image/jpeg', 'product', ?, '', 0, 0, 0, '', '', 0, 1, 1, "
        "'2026-09-21 07:30:01', 119, '2026-09-21 07:30:01', 119, NULL, 0)",
        (media_id, filename, url),
    )


def test_reimport_reuses_orphan_media_row(vm_db, cfg, tmp_path):
    """Product deleted in admin, medias row + file still there. Re-import must
    NOT insert a duplicate medias row — it links to the existing one."""
    seed_orphan_media(vm_db, 9001, "102 Glisse.jpg")
    cfg.vm_media_dir = str(tmp_path / "srv")
    image = tmp_path / "images" / "102 Glisse.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"a")

    imp = ProductImporter(vm_db, cfg)
    row = make_row(sku="102", title_en="102 Glisse",
                   description_en="<p>Pointe shoe.</p>",
                   title_el="102 Glisse", description_el="<p>Παπούτσι.</p>",
                   images=[image])
    plan = imp.build_plan(row)
    assert plan.operation == "CREATE"
    assert [a.kind for a in plan.actions if a.kind == "insert_media"] == []
    link_actions = [a for a in plan.actions if a.kind == "insert_link"]
    assert len(link_actions) == 1
    assert f"reuses existing media row 9001" in link_actions[0].description
    imp.execute(plan)

    pid = plan.product_id
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_medias "
                        "WHERE file_url LIKE '%102 Glisse%'") == 1
    link = vm_db.query_one(
        "SELECT virtuemart_media_id FROM xhngw_virtuemart_product_medias "
        "WHERE virtuemart_product_id=?", (pid,))
    assert link["virtuemart_media_id"] == 9001

    # idempotent re-run: nothing to do
    plan2 = imp.build_plan(make_row(sku="102", title_en="102 Glisse",
                                    description_en="<p>Pointe shoe.</p>",
                                    title_el="102 Glisse", description_el="<p>Παπούτσι.</p>",
                                    images=[image]))
    assert not [a for a in plan2.actions if a.kind in ("insert_media", "insert_link")]


def test_mixed_new_and_existing_media(vm_db, cfg, tmp_path):
    """One file already registered, one brand new: reuse + insert respectively."""
    seed_orphan_media(vm_db, 9001, "102 Glisse.jpg")
    cfg.vm_media_dir = str(tmp_path / "srv")
    images = tmp_path / "images"
    images.mkdir(parents=True)
    (images / "102 Glisse.jpg").write_bytes(b"a")
    (images / "102 Glisse back.jpg").write_bytes(b"b")

    imp = ProductImporter(vm_db, cfg)
    row = make_row(sku="102", title_en="102 Glisse",
                   description_en="<p>Pointe shoe.</p>",
                   title_el="102 Glisse", description_el="<p>Παπούτσι.</p>",
                   images=[images / "102 Glisse.jpg", images / "102 Glisse back.jpg"])
    plan = imp.build_plan(row)
    inserts = [a.payload["url"] for a in plan.actions if a.kind == "insert_media"]
    links = [a.payload["url"] for a in plan.actions if a.kind == "insert_link"]
    # only the new file gets a medias row; both get links (order is the
    # importer's natural filename order, covered by the media tests)
    assert inserts == ["images/stories/virtuemart/product/102 Glisse back.jpg"]
    assert set(links) == {"images/stories/virtuemart/product/102 Glisse.jpg",
                          "images/stories/virtuemart/product/102 Glisse back.jpg"}
    assert links[0].endswith("102 Glisse back.jpg")  # main image = first in order
def test_mixed_new_and_existing_media_counts(vm_db, cfg, tmp_path):
    seed_orphan_media(vm_db, 9001, "102 Glisse.jpg")
    before = vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_medias")
    cfg.vm_media_dir = str(tmp_path / "srv")
    images = tmp_path / "images"
    images.mkdir(parents=True)
    (images / "102 Glisse.jpg").write_bytes(b"a")
    (images / "102 Glisse back.jpg").write_bytes(b"b")
    imp = ProductImporter(vm_db, cfg)
    row = make_row(sku="102", title_en="102 Glisse",
                   description_en="<p>Pointe shoe.</p>",
                   title_el="102 Glisse", description_el="<p>Παπούτσι.</p>",
                   images=[images / "102 Glisse.jpg", images / "102 Glisse back.jpg"])
    plan = imp.build_plan(row)
    imp.execute(plan)
    after = vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_medias")
    assert after - before == 1  # only the genuinely new file


def test_duplicate_media_rows_in_db_reuse_lowest_id(vm_db, cfg, tmp_path):
    """If duplicates already exist (created by the old bug), the importer
    deterministically reuses the lowest media id and adds nothing."""
    seed_orphan_media(vm_db, 9001, "102 Glisse.jpg")
    seed_orphan_media(vm_db, 9002, "102 Glisse.jpg")  # duplicate from the old bug
    cfg.vm_media_dir = str(tmp_path / "srv")
    image = tmp_path / "images" / "102 Glisse.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"a")
    imp = ProductImporter(vm_db, cfg)
    row = make_row(sku="102", title_en="102 Glisse",
                   description_en="<p>Pointe shoe.</p>",
                   title_el="102 Glisse", description_el="<p>Παπούτσι.</p>",
                   images=[image])
    plan = imp.build_plan(row)
    assert not [a for a in plan.actions if a.kind == "insert_media"]
    assert "media row 9001" in [a.description for a in plan.actions
                                if a.kind == "insert_link"][0]
    imp.execute(plan)
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_medias "
                        "WHERE file_url LIKE '%102 Glisse%'") == 2  # unchanged


def test_fresh_media_still_inserts_normally(vm_db, cfg, tmp_path):
    """No regression: a brand-new file still gets a new medias row."""
    cfg.vm_media_dir = str(tmp_path / "srv")
    images = tmp_path / "images"
    images.mkdir(parents=True)
    (images / "BRANDNEW Black.jpg").write_bytes(b"a")
    before = vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_medias")
    imp = ProductImporter(vm_db, cfg)
    row = make_row(sku="NEW9", title_en="Tights NEW9", description_en="<p>t.</p>",
                   title_el="Κολάν NEW9", description_el="<p>κ.</p>",
                   images=[images / "BRANDNEW Black.jpg"])
    plan = imp.build_plan(row)
    assert [a.payload["url"] for a in plan.actions if a.kind == "insert_media"] == [
        "images/stories/virtuemart/product/BRANDNEW Black.jpg"]
    imp.execute(plan)
    assert vm_db.scalar("SELECT COUNT(*) FROM xhngw_virtuemart_medias") - before == 1
