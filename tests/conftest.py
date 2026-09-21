"""Shared fixtures: a sqlite copy of the relevant VirtueMart tables, seeded
with the real CD004 data from the production dump (product id 494).

The column lists mirror the production schema exactly so the repository SQL
runs unchanged. Tests never need MariaDB or production credentials.
"""
from __future__ import annotations

import sqlite3

import pytest

from vmimporter.config import PRODUCT_PARAMS_DEFAULT, Config
from vmimporter.db import Database

CF_PARAMS = 'product_sku=""|product_gtin=""|product_mpn=""||'

SCHEMA = """
CREATE TABLE xhngw_virtuemart_products (
  virtuemart_product_id INTEGER PRIMARY KEY,
  virtuemart_vendor_id INTEGER NOT NULL DEFAULT 1,
  product_parent_id INTEGER NOT NULL DEFAULT 0,
  product_sku TEXT, product_gtin TEXT, product_mpn TEXT,
  product_weight REAL, product_weight_uom TEXT,
  product_length REAL, product_width REAL, product_height REAL, product_lwh_uom TEXT,
  product_url TEXT, product_in_stock INTEGER NOT NULL DEFAULT 0,
  product_ordered INTEGER NOT NULL DEFAULT 0, product_stockhandle TEXT NOT NULL DEFAULT '0',
  low_stock_notification INTEGER NOT NULL DEFAULT 0, product_available_date TEXT,
  product_availability TEXT, product_special INTEGER NOT NULL DEFAULT 0,
  product_discontinued INTEGER NOT NULL DEFAULT 0, product_sales INTEGER NOT NULL DEFAULT 0,
  product_unit TEXT, product_packaging REAL,
  product_params TEXT NOT NULL DEFAULT '',
  product_canon_category_id INTEGER, hits INTEGER, intnotes TEXT,
  metarobot TEXT, metaauthor TEXT, layout TEXT,
  published INTEGER NOT NULL DEFAULT 0, pordering INTEGER NOT NULL DEFAULT 0,
  has_categories INTEGER, has_manufacturers INTEGER, has_medias INTEGER,
  has_prices INTEGER, has_shoppergroups INTEGER,
  created_on TEXT, created_by INTEGER NOT NULL DEFAULT 0,
  modified_on TEXT, modified_by INTEGER NOT NULL DEFAULT 0,
  locked_on TEXT, locked_by INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_products_en_gb (
  virtuemart_product_id INTEGER PRIMARY KEY,
  product_s_desc TEXT NOT NULL DEFAULT '', product_desc TEXT,
  product_name TEXT NOT NULL DEFAULT '', metadesc TEXT NOT NULL DEFAULT '',
  metakey TEXT NOT NULL DEFAULT '', customtitle TEXT NOT NULL DEFAULT '',
  slug TEXT NOT NULL DEFAULT ''
);
CREATE TABLE xhngw_virtuemart_products_el_gr (
  virtuemart_product_id INTEGER PRIMARY KEY,
  product_s_desc TEXT NOT NULL DEFAULT '', product_desc TEXT,
  product_name TEXT NOT NULL DEFAULT '', metadesc TEXT NOT NULL DEFAULT '',
  metakey TEXT NOT NULL DEFAULT '', customtitle TEXT NOT NULL DEFAULT '',
  slug TEXT NOT NULL DEFAULT ''
);
CREATE TABLE xhngw_virtuemart_product_prices (
  virtuemart_product_price_id INTEGER PRIMARY KEY,
  virtuemart_product_id INTEGER NOT NULL DEFAULT 0,
  virtuemart_shoppergroup_id INTEGER NOT NULL DEFAULT 0,
  product_price REAL, override INTEGER, product_override_price REAL,
  product_tax_id INTEGER, product_discount_id INTEGER, product_currency INTEGER,
  product_price_publish_up TEXT, product_price_publish_down TEXT,
  price_quantity_start INTEGER NOT NULL DEFAULT 0, price_quantity_end INTEGER NOT NULL DEFAULT 0,
  created_on TEXT, created_by INTEGER NOT NULL DEFAULT 0,
  modified_on TEXT, modified_by INTEGER NOT NULL DEFAULT 0,
  locked_on TEXT, locked_by INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_product_customfields (
  virtuemart_customfield_id INTEGER PRIMARY KEY,
  virtuemart_product_id INTEGER NOT NULL DEFAULT 0,
  virtuemart_custom_id INTEGER NOT NULL DEFAULT 1,
  customfield_value TEXT, customfield_price REAL,
  disabler INTEGER NOT NULL DEFAULT 0, override INTEGER NOT NULL DEFAULT 0,
  noninheritable INTEGER NOT NULL DEFAULT 0, customfield_params TEXT,
  product_sku TEXT, product_gtin TEXT, product_mpn TEXT,
  published INTEGER NOT NULL DEFAULT 1,
  created_on TEXT NOT NULL DEFAULT '0000-00-00 00:00:00',
  created_by INTEGER NOT NULL DEFAULT 0,
  modified_on TEXT NOT NULL DEFAULT '0000-00-00 00:00:00',
  modified_by INTEGER NOT NULL DEFAULT 0,
  locked_on TEXT NOT NULL DEFAULT '0000-00-00 00:00:00',
  locked_by INTEGER NOT NULL DEFAULT 0, ordering INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_medias (
  virtuemart_media_id INTEGER PRIMARY KEY,
  virtuemart_vendor_id INTEGER NOT NULL DEFAULT 1,
  file_title TEXT NOT NULL DEFAULT '', file_description TEXT NOT NULL DEFAULT '',
  file_meta TEXT NOT NULL DEFAULT '', file_class TEXT NOT NULL DEFAULT '',
  file_mimetype TEXT NOT NULL DEFAULT '', file_type TEXT NOT NULL DEFAULT '',
  file_url TEXT NOT NULL DEFAULT '', file_url_thumb TEXT NOT NULL DEFAULT '',
  file_is_product_image INTEGER NOT NULL DEFAULT 0,
  file_is_downloadable INTEGER NOT NULL DEFAULT 0,
  file_is_forSale INTEGER NOT NULL DEFAULT 0,
  file_params TEXT NOT NULL DEFAULT '', file_lang TEXT NOT NULL DEFAULT '',
  shared INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 1,
  is_image INTEGER, created_on TEXT, created_by INTEGER NOT NULL DEFAULT 0,
  modified_on TEXT, modified_by INTEGER NOT NULL DEFAULT 0,
  locked_on TEXT, locked_by INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_product_medias (
  id INTEGER PRIMARY KEY,
  virtuemart_product_id INTEGER NOT NULL DEFAULT 0,
  virtuemart_media_id INTEGER NOT NULL DEFAULT 0,
  ordering INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_product_categories (
  id INTEGER PRIMARY KEY,
  virtuemart_product_id INTEGER NOT NULL DEFAULT 0,
  virtuemart_category_id INTEGER NOT NULL DEFAULT 0,
  ordering INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_categories (
  virtuemart_category_id INTEGER PRIMARY KEY,
  virtuemart_vendor_id INTEGER NOT NULL DEFAULT 1,
  category_parent_id INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1,
  created_on TEXT, created_by INTEGER NOT NULL DEFAULT 0,
  modified_on TEXT, modified_by INTEGER NOT NULL DEFAULT 0,
  locked_on TEXT, locked_by INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_categories_en_gb (
  id INTEGER PRIMARY KEY,
  virtuemart_category_id INTEGER NOT NULL DEFAULT 0,
  category_name TEXT NOT NULL DEFAULT '',
  slug TEXT NOT NULL DEFAULT ''
);
CREATE TABLE xhngw_virtuemart_product_manufacturers (
  id INTEGER PRIMARY KEY,
  virtuemart_product_id INTEGER NOT NULL DEFAULT 0,
  virtuemart_manufacturer_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_manufacturers (
  virtuemart_manufacturer_id INTEGER PRIMARY KEY,
  virtuemart_manufacturercategories_id INTEGER,
  metarobot TEXT, metaauthor TEXT,
  hits INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1,
  created_on TEXT, created_by INTEGER NOT NULL DEFAULT 0,
  modified_on TEXT, modified_by INTEGER NOT NULL DEFAULT 0,
  locked_on TEXT, locked_by INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE xhngw_virtuemart_manufacturers_en_gb (
  id INTEGER PRIMARY KEY,
  virtuemart_manufacturer_id INTEGER NOT NULL DEFAULT 0,
  mf_name TEXT NOT NULL DEFAULT '',
  slug TEXT NOT NULL DEFAULT ''
);
"""

# Real category rows from the production dump (analysis section 5).
CATEGORIES = [
    (1, 0, "Women"),
    (23, 0, "Kids"),
    (24, 0, "Shoes"),
    (25, 0, "Accessories"),
    (60, 1, "Character"),
    (61, 24, "Ballet"),
    (62, 24, "Latin"),
    (63, 24, "Liberti Shoes Collection"),
    (64, 24, "Jazz Shoes"),
    (65, 24, "Ballroom Various"),
    (29, 1, "Leotards"),
    (34, 1, "Tights|Gaiters"),
    (35, 1, "Tutus"),
    (31, 1, "Skirts"),
]

CD004_EN_NAME = "Go Dance Latin Shoes CD004 Tight Crosscut & Plated Heel"
CD004_EN_DESC = (
    "<p>Women's Latin dance boots Go Dance CD004 with tight cross straps design "
    "in black colour and a plated heel. Soft and comfortable line, latex sole.</p>\r\n"
    "<p>Available in 9.0cm Plated Heel.</p>"
)
CD004_EN_SDESC = (
    "Women's Latin dance boots Go Dance CD004 with tight cross straps design."
)
CD004_EL_NAME = "Go Dance Υπόδημα Λάτιν CD004 Χιαστί Λουράκια με Plated Heels"
CD004_EL_DESC = (
    "<p>Γυναικεία μποτάκια λάτιν χορού Go Dance CD004 με σχέδιο με σφιχτά σταυρωτά "
    "λουράκια σε μαύρο χρώμα και επιμεταλλωμένο τακούνι. Μαλακή και άνετη γραμμή, "
    "σόλα από λάτεξ.</p>\r\n"
    "<p>Διατίθενται σε επιμεταλλωμένο τακούνι 9,0cm.</p>"
)


def make_db(path: str | None = None) -> Database:
    con = sqlite3.connect(path or ":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return Database(con, "sqlite")


def seed_cd004(db: Database) -> None:
    """Insert CD004 exactly as found in the production dump."""
    # manufacturers as in the dump (ids 10..16, all published; CD004 -> 15)
    for mid, name in ((10, "Sheddo®"), (11, "Merlet"), (12, "Katz Dancewear"),
                      (13, "G&G Dance Shoes"), (14, "Sansha®"), (15, "Go Dance"),
                      (16, "SoDanca")):
        db.execute(
            "INSERT INTO xhngw_virtuemart_manufacturers (virtuemart_manufacturer_id, "
            "published) VALUES (?, 1)",
            (mid,),
        )
        db.execute(
            "INSERT INTO xhngw_virtuemart_manufacturers_en_gb (virtuemart_manufacturer_id, "
            "mf_name, slug) VALUES (?, ?, ?)",
            (mid, name, name.lower().replace("®", "").replace("&", "-")
                .replace(" ", "-")),
        )
    db.execute(
        "INSERT INTO xhngw_virtuemart_product_manufacturers VALUES (452, 494, 15)")
    for cid, parent, name in CATEGORIES:
        db.execute(
            "INSERT INTO xhngw_virtuemart_categories (virtuemart_category_id, "
            "virtuemart_vendor_id, category_parent_id, published) VALUES (?, 1, ?, 1)",
            (cid, parent),
        )
        db.execute(
            "INSERT INTO xhngw_virtuemart_categories_en_gb (virtuemart_category_id, "
            "category_name, slug) VALUES (?, ?, ?)",
            (cid, name, name.lower().replace("|", "-").replace(" ", "-")),
        )
    db.execute(
        "INSERT INTO xhngw_virtuemart_products VALUES ("
        "494, 1, 0, 'CD004', 'CD004', NULL, 0.45, 'KG', NULL, NULL, NULL, 'M', '', 30, 0,"
        "'0', 0, '2026-02-14 00:00:00', '', 0, 0, 0, 'KG', NULL, ?, NULL, NULL, '', '', '',"
        "'', 1, 0, 1, 1, 1, 1, 0, '2026-02-26 17:16:13', 119, '2026-02-26 17:21:28', 119,"
        "NULL, 0)",
        (PRODUCT_PARAMS_DEFAULT,),
    )
    db.execute(
        "INSERT INTO xhngw_virtuemart_products_en_gb VALUES (494, ?, ?, ?, ?, ?, ?, 'cd004')",
        (CD004_EN_SDESC, CD004_EN_DESC, CD004_EN_NAME, CD004_EN_SDESC, CD004_EN_SDESC,
         CD004_EN_NAME),
    )
    db.execute(
        "INSERT INTO xhngw_virtuemart_products_el_gr VALUES (494, "
        "'Γυναικεία μποτάκια λάτιν χορού Go Dance CD004 με σχέδιο με σφιχτά σταυρωτά λουράκια.', "
        "?, ?, ?, ?, ?, 'cd004')",
        (CD004_EL_DESC, CD004_EL_NAME, CD004_EL_NAME, CD004_EL_NAME, CD004_EL_NAME),
    )
    db.execute(
        "INSERT INTO xhngw_virtuemart_product_prices VALUES ("
        "1417, 494, 0, 77.82258, 0, 0, 0, 0, 47, NULL, NULL, 0, 0, "
        "'2026-02-26 17:16:13', 119, '2026-02-26 17:21:28', 119, NULL, 0)"
    )
    rows = [
        (11708, 7, "BLK"),
        (11709, 6, "35"), (11710, 6, "36"), (11711, 6, "37"), (11712, 6, "38"),
        (11713, 6, "39"), (11714, 6, "40"), (11715, 6, "41"), (11716, 6, "42"),
        (11717, 18, "9.0cm Plated Heel"),
    ]
    for cfid, custom_id, value in rows:
        db.execute(
            "INSERT INTO xhngw_virtuemart_product_customfields VALUES ("
            "?, 494, ?, ?, 0, 0, 0, 0, ?, NULL, NULL, NULL, 0, "
            "'0000-00-00 00:00:00', 0, '0000-00-00 00:00:00', 0, "
            "'0000-00-00 00:00:00', 0, 0)",
            (cfid, custom_id, value, CF_PARAMS),
        )
    medias = [
        (1281, "CD004 Black 0.jpg", "image/jpeg", "images/stories/virtuemart/product/CD004 Black 0.jpg"),
        (1282, "CD004 Black.jpg", "image/jpeg", "images/stories/virtuemart/product/CD004 Black.jpg"),
        (1283, "CD004 Black A.jpg", "image/jpeg", "images/stories/virtuemart/product/CD004 Black A.jpg"),
    ]
    for mid, title, mime, url in medias:
        db.execute(
            "INSERT INTO xhngw_virtuemart_medias VALUES ("
            "?, 1, ?, '', '', '', ?, 'product', ?, '', 0, 0, 0, '', '', 0, 1, 1, "
            "'2026-02-26 17:12:21', 119, '2026-02-26 17:21:28', 119, NULL, 0)",
            (mid, title, mime, url),
        )
    for jid, mid, ordering in ((1277, 1281, 1), (1276, 1283, 2), (1275, 1282, 3)):
        db.execute(
            "INSERT INTO xhngw_virtuemart_product_medias VALUES (?, 494, ?, ?)",
            (jid, mid, ordering),
        )
    db.execute(
        "INSERT INTO xhngw_virtuemart_product_categories VALUES (585, 494, 62, 0)"
    )


@pytest.fixture()
def vm_db():
    db = make_db()
    seed_cd004(db)
    return db


@pytest.fixture()
def cfg(tmp_path):
    return Config(
        db_backend="sqlite",
        db_name=str(tmp_path / "db.sqlite"),
        vm_media_dir=str(tmp_path / "media"),
        images_path=str(tmp_path / "images"),
        vm_admin_user_id=119,
        price_mode="net",
    )
