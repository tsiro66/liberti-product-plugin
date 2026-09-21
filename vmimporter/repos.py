"""Repository layer — all SQL lives here.

Column lists and default values mirror the production schema exactly
(see virtuemart-database-analysis.md). Conventions reproduced from CD004:

  products          vendor 1, parent 0, product_params default string,
                    gtin = sku, metarobot/metaauthor/intnotes/product_url/layout
                    = '' (empty strings, as in the dump), product_unit/packaging/
                    canon_category/hits NULL, locked_on/locked_by unused
  product_prices    shoppergroup 0, override 0, tax rule 1, currency 47,
                    quantity range 0..0, publish up/down NULL
  product_customfields  customfield_params constant, disabler/override/
                    noninheritable 0, published 0, ordering 0
  medias            file_type 'product', file_url relative, file_url_thumb '',
                    file_is_product_image 0, is_image 1, published 1, shared 0
  product_medias    1-based ordering, UNIQUE(product, media)

All SQL is deliberately portable (plain ANSI + %s placeholders) so the same
code runs against MariaDB in production and against a sqlite copy of the dump
in tests. Zero-dates are never inserted explicitly: columns keep their schema
defaults instead (strict MariaDB sql_mode rejects '0000-00-00' literals).
"""
from __future__ import annotations

from .config import (
    CURRENCY_ID,
    CUSTOMFIELD_PARAMS,
    PRODUCT_PARAMS_DEFAULT,
    TABLE_PREFIX,
    TAX_CALC_ID,
    VENDOR_ID,
)

P = TABLE_PREFIX  # table prefix from the analysis; single installation


class ProductRepository:
    def __init__(self, db) -> None:
        self.db = db

    # -- lookups ---------------------------------------------------------------

    def find_id_by_sku(self, sku: str) -> tuple[int | None, str | None]:
        """Find product id by exact SKU, falling back to case-insensitive match.

        Returns (product_id, note). note explains a case-insensitive fallback.
        If several rows share the SKU the situation is ambiguous and an error is
        raised — the importer never guesses.
        """
        row = self.db.query_one(
            f"SELECT virtuemart_product_id FROM {P}virtuemart_products WHERE product_sku = %s",
            (sku,),
        )
        if row:
            return int(row["virtuemart_product_id"]), None
        rows = self.db.query_all(
            f"SELECT virtuemart_product_id, product_sku FROM {P}virtuemart_products "
            f"WHERE UPPER(product_sku) = UPPER(%s)",
            (sku,),
        )
        if not rows:
            return None, None
        if len(rows) > 1:
            raise RuntimeError(
                f"SKU '{sku}' matches {len(rows)} products "
                f"({[r['product_sku'] for r in rows]}); refusing to guess"
            )
        return int(rows[0]["virtuemart_product_id"]), (
            f"matched case-insensitively to existing SKU '{rows[0]['product_sku']}'"
        )

    def get_core(self, product_id: int) -> dict | None:
        return self.db.query_one(
            f"SELECT * FROM {P}virtuemart_products WHERE virtuemart_product_id = %s",
            (product_id,),
        )

    def sku_exists(self, sku: str) -> bool:
        return self.db.query_one(
            f"SELECT virtuemart_product_id FROM {P}virtuemart_products WHERE product_sku = %s",
            (sku,),
        ) is not None

    # -- writes -----------------------------------------------------------------

    def insert_core(
        self,
        *,
        sku: str,
        published: int,
        has_categories: int,
        has_manufacturers: int,
        has_medias: int,
        now: str,
        user_id: int,
    ) -> int:
        """INSERT the core product row, CD004-shaped. Returns the new id."""
        sql = (
            f"INSERT INTO {P}virtuemart_products ("
            "virtuemart_vendor_id, product_parent_id, product_sku, product_gtin, product_mpn, "
            "product_weight, product_weight_uom, product_length, product_width, product_height, "
            "product_lwh_uom, product_url, product_in_stock, product_ordered, product_stockhandle, "
            "low_stock_notification, product_available_date, product_availability, "
            "product_special, product_discontinued, product_sales, product_unit, product_packaging, "
            "product_params, product_canon_category_id, hits, intnotes, metarobot, metaauthor, "
            "layout, published, pordering, has_categories, has_manufacturers, has_medias, "
            "has_prices, has_shoppergroups, created_on, created_by, modified_on, modified_by, "
            "locked_on, locked_by"
            ") VALUES ("
            f"{VENDOR_ID}, 0, %s, %s, NULL, "          # sku, gtin(=sku), mpn
            "NULL, NULL, NULL, NULL, NULL, "            # weight + dimensions (not in CSV)
            "NULL, %s, 0, 0, '0', "                     # lwh_uom, product_url, in_stock, ordered, stockhandle
            "0, %s, '', "                               # low_stock, available_date, availability
            "0, 0, 0, NULL, NULL, "                     # special, discontinued, sales, unit, packaging
            f"%s, NULL, NULL, '', '', '', '', "         # params, canon, hits, intnotes, metarobot, metaauthor, layout
            "%s, 0, %s, %s, %s, "                      # published, pordering, has_categories, has_manuf, has_medias
            "1, 0, %s, %s, %s, %s, "                    # has_prices, has_shoppergroups, created_on/by
            "NULL, 0)"                                  # locked_on, locked_by
        )
        cur = self.db.execute(
            sql,
            (
                sku, sku,                       # sku, gtin
                "",                             # product_url
                now,                            # available_date
                PRODUCT_PARAMS_DEFAULT,         # product_params
                published, has_categories, has_manufacturers, has_medias,
                now, user_id, now, user_id,     # created_on/by, modified_on/by
            ),
        )
        return int(cur.lastrowid)

    def touch(
        self, product_id: int, now: str, user_id: int,
        extra_sets: list[str] = (), extra_params: list = (),
    ) -> None:
        """UPDATE modified_on/by plus optional flag columns (has_medias etc.)."""
        sets = ["modified_on = %s", "modified_by = %s"] + list(extra_sets)
        params: list = [now, user_id, *extra_params, product_id]
        self.db.execute(
            f"UPDATE {P}virtuemart_products SET {', '.join(sets)} "
            f"WHERE virtuemart_product_id = %s",
            tuple(params),
        )


class LanguageRepository:
    #: language table suffixes discovered in the dump (Joomla lang ids 1=en-GB, 3=el-GR)
    LANGS = ("en_gb", "el_gr")

    def __init__(self, db) -> None:
        self.db = db

    def get(self, product_id: int, lang: str) -> dict | None:
        return self.db.query_one(
            f"SELECT * FROM {P}virtuemart_products_{lang} WHERE virtuemart_product_id = %s",
            (product_id,),
        )

    def taken_slugs(self, lang: str) -> dict[str, int]:
        rows = self.db.query_all(
            f"SELECT virtuemart_product_id, slug FROM {P}virtuemart_products_{lang}"
        )
        return {r["slug"]: int(r["virtuemart_product_id"]) for r in rows}

    def insert(
        self, product_id: int, lang: str, *, name: str, description: str,
        s_desc: str, metadesc: str, metakey: str, customtitle: str, slug: str,
    ) -> None:
        self.db.execute(
            f"INSERT INTO {P}virtuemart_products_{lang} "
            "(virtuemart_product_id, product_s_desc, product_desc, product_name, "
            "metadesc, metakey, customtitle, slug) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (product_id, s_desc, description, name, metadesc, metakey, customtitle, slug),
        )

    def update_owned_fields(
        self, product_id: int, lang: str, *, name: str, description: str, s_desc: str | None,
    ) -> None:
        """UPDATE only CSV-owned text fields. s_desc None = leave unchanged.

        slug / customtitle / metadesc / metakey are NOT touched on update:
        changing slugs breaks product URLs and the CSV does not own SEO fields.
        """
        sets = ["product_name = %s", "product_desc = %s"]
        params: list = [name, description]
        if s_desc is not None:
            sets.append("product_s_desc = %s")
            params.append(s_desc)
        params.append(product_id)
        self.db.execute(
            f"UPDATE {P}virtuemart_products_{lang} SET {', '.join(sets)} "
            f"WHERE virtuemart_product_id = %s",
            tuple(params),
        )


class PriceRepository:
    def __init__(self, db) -> None:
        self.db = db

    def get_default_price_row(self, product_id: int) -> dict | None:
        """The default price row: shoppergroup 0, quantity 0..0, lowest id."""
        return self.db.query_one(
            f"SELECT * FROM {P}virtuemart_product_prices WHERE virtuemart_product_id = %s "
            "AND virtuemart_shoppergroup_id = 0 AND price_quantity_start = 0 "
            "AND price_quantity_end = 0 ORDER BY virtuemart_product_price_id LIMIT 1",
            (product_id,),
        )

    def count_default_price_rows(self, product_id: int) -> int:
        return int(self.db.scalar(
            f"SELECT COUNT(*) FROM {P}virtuemart_product_prices WHERE virtuemart_product_id = %s "
            "AND virtuemart_shoppergroup_id = 0 AND price_quantity_start = 0 "
            "AND price_quantity_end = 0",
            (product_id,),
        ) or 0)

    def insert(self, product_id: int, net_price: float, *, now: str, user_id: int) -> int:
        cur = self.db.execute(
            f"INSERT INTO {P}virtuemart_product_prices ("
            "virtuemart_product_id, virtuemart_shoppergroup_id, product_price, override, "
            "product_override_price, product_tax_id, product_discount_id, product_currency, "
            "product_price_publish_up, product_price_publish_down, price_quantity_start, "
            "price_quantity_end, created_on, created_by, modified_on, modified_by, "
            "locked_on, locked_by"
            ") VALUES (%s, 0, %s, 0, 0, %s, 0, %s, NULL, NULL, 0, 0, %s, %s, %s, %s, NULL, 0)",
            (product_id, net_price, TAX_CALC_ID, CURRENCY_ID, now, user_id, now, user_id),
        )
        return int(cur.lastrowid)

    def update_price(self, price_row_id: int, net_price: float, *, now: str, user_id: int) -> None:
        self.db.execute(
            f"UPDATE {P}virtuemart_product_prices SET product_price = %s, modified_on = %s, "
            f"modified_by = %s WHERE virtuemart_product_price_id = %s",
            (net_price, now, user_id, price_row_id),
        )


class CustomFieldRepository:
    def __init__(self, db) -> None:
        self.db = db

    def list_for(self, product_id: int, custom_id: int) -> list[dict]:
        return self.db.query_all(
            f"SELECT virtuemart_customfield_id, customfield_value, customfield_price, published, "
            f"ordering FROM {P}virtuemart_product_customfields "
            f"WHERE virtuemart_product_id = %s AND virtuemart_custom_id = %s",
            (product_id, custom_id),
        )

    def insert(
        self, product_id: int, custom_id: int, value: str, *, now: str, user_id: int
    ) -> int:
        """One row per option value.

        published=0 and ordering=0 reproduce the shop-wide convention (all
        10,670 existing rows carry these values; the frontend does not filter
        on them in this installation). customfield_price=0 reproduces the
        observed data: Colour rows are always 0, and CSV input carries no
        surcharge amounts. locked_on is omitted so the schema default applies
        (strict MariaDB rejects explicit zero-date literals).
        """
        cur = self.db.execute(
            f"INSERT INTO {P}virtuemart_product_customfields ("
            "virtuemart_product_id, virtuemart_custom_id, customfield_value, customfield_price, "
            "disabler, override, noninheritable, customfield_params, product_sku, product_gtin, "
            "product_mpn, published, created_on, created_by, modified_on, modified_by, "
            "locked_by, ordering"
            ") VALUES (%s, %s, %s, 0, 0, 0, 0, %s, NULL, NULL, NULL, 0, %s, %s, %s, %s, 0, 0)",
            (product_id, custom_id, value, CUSTOMFIELD_PARAMS, now, user_id, now, user_id),
        )
        return int(cur.lastrowid)

    def delete_by_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        marks = ", ".join(["%s"] * len(ids))
        self.db.execute(
            f"DELETE FROM {P}virtuemart_product_customfields "
            f"WHERE virtuemart_customfield_id IN ({marks})",
            tuple(ids),
        )


class ManufacturerRepository:
    def __init__(self, db) -> None:
        self.db = db

    def get(self, manufacturer_id: int) -> dict | None:
        """The manufacturer core row (published flag included), or None."""
        return self.db.query_one(
            f"SELECT virtuemart_manufacturer_id, published FROM {P}virtuemart_manufacturers "
            f"WHERE virtuemart_manufacturer_id = %s",
            (manufacturer_id,),
        )

    def name_for(self, manufacturer_id: int) -> str:
        row = self.db.query_one(
            f"SELECT mf_name FROM {P}virtuemart_manufacturers_en_gb "
            f"WHERE virtuemart_manufacturer_id = %s",
            (manufacturer_id,),
        )
        return (row["mf_name"] if row else "") or ""

    def link_exists(self, product_id: int, manufacturer_id: int) -> bool:
        return self.db.query_one(
            f"SELECT id FROM {P}virtuemart_product_manufacturers "
            f"WHERE virtuemart_product_id = %s AND virtuemart_manufacturer_id = %s",
            (product_id, manufacturer_id),
        ) is not None

    def insert_link(self, product_id: int, manufacturer_id: int) -> int:
        cur = self.db.execute(
            f"INSERT INTO {P}virtuemart_product_manufacturers "
            "(virtuemart_product_id, virtuemart_manufacturer_id) VALUES (%s, %s)",
            (product_id, manufacturer_id),
        )
        return int(cur.lastrowid)


class MediaRepository:
    def __init__(self, db) -> None:
        self.db = db

    def find_id_by_url(self, file_url: str) -> int | None:
        """Lowest-id media row for this file_url (deterministic even when the
        table already contains duplicate rows for the same file)."""
        row = self.db.query_one(
            f"SELECT virtuemart_media_id FROM {P}virtuemart_medias WHERE file_url = %s "
            "ORDER BY virtuemart_media_id LIMIT 1",
            (file_url,),
        )
        return int(row["virtuemart_media_id"]) if row else None

    def insert(
        self, *, file_title: str, file_url: str, mimetype: str, file_meta: str,
        now: str, user_id: int,
    ) -> int:
        cur = self.db.execute(
            f"INSERT INTO {P}virtuemart_medias ("
            "virtuemart_vendor_id, file_title, file_description, file_meta, file_class, "
            "file_mimetype, file_type, file_url, file_url_thumb, file_is_product_image, "
            "file_is_downloadable, file_is_forSale, file_params, file_lang, shared, published, "
            "is_image, created_on, created_by, modified_on, modified_by, locked_on, locked_by"
            ") VALUES (%s, %s, '', %s, '', %s, 'product', %s, '', 0, 0, 0, '', '', 0, 1, "
            "1, %s, %s, %s, %s, NULL, 0)",
            (VENDOR_ID, file_title, file_meta, mimetype, file_url, now, user_id, now, user_id),
        )
        return int(cur.lastrowid)

    def list_product_images(self, product_id: int) -> list[dict]:
        """Product image links joined with medias, ordered by (ordering, join id)."""
        return self.db.query_all(
            f"SELECT pm.id AS join_id, pm.virtuemart_media_id AS media_id, pm.ordering, "
            f"m.file_url FROM {P}virtuemart_product_medias pm "
            f"JOIN {P}virtuemart_medias m ON m.virtuemart_media_id = pm.virtuemart_media_id "
            f"WHERE pm.virtuemart_product_id = %s AND m.file_type = 'product' "
            f"ORDER BY pm.ordering, pm.id",
            (product_id,),
        )

    def insert_link(self, product_id: int, media_id: int, ordering: int) -> int:
        cur = self.db.execute(
            f"INSERT INTO {P}virtuemart_product_medias "
            "(virtuemart_product_id, virtuemart_media_id, ordering) VALUES (%s, %s, %s)",
            (product_id, media_id, ordering),
        )
        return int(cur.lastrowid)

    def update_link_ordering(self, join_id: int, ordering: int) -> None:
        self.db.execute(
            f"UPDATE {P}virtuemart_product_medias SET ordering = %s WHERE id = %s",
            (ordering, join_id),
        )


class CategoryRepository:
    def __init__(self, db) -> None:
        self.db = db

    def get_by_ids(self, ids: list[int]) -> dict[int, dict]:
        """Category rows by id (any order). Missing ids are simply absent."""
        if not ids:
            return {}
        marks = ", ".join(["%s"] * len(ids))
        rows = self.db.query_all(
            f"SELECT virtuemart_category_id, published FROM {P}virtuemart_categories "
            f"WHERE virtuemart_category_id IN ({marks})",
            tuple(ids),
        )
        return {int(r["virtuemart_category_id"]): dict(r) for r in rows}

    def names_for(self, ids: list[int]) -> dict[int, str]:
        """EN names for a list of category ids (missing ids are absent)."""
        if not ids:
            return {}
        marks = ", ".join(["%s"] * len(ids))
        rows = self.db.query_all(
            f"SELECT c.virtuemart_category_id, l.category_name "
            f"FROM {P}virtuemart_categories c "
            f"LEFT JOIN {P}virtuemart_categories_en_gb l "
            f"ON l.virtuemart_category_id = c.virtuemart_category_id "
            f"WHERE c.virtuemart_category_id IN ({marks})",
            tuple(ids),
        )
        return {int(r["virtuemart_category_id"]): (r["category_name"] or "") for r in rows}

    def link_exists(self, product_id: int, category_id: int) -> bool:
        return self.db.query_one(
            f"SELECT id FROM {P}virtuemart_product_categories "
            f"WHERE virtuemart_product_id = %s AND virtuemart_category_id = %s",
            (product_id, category_id),
        ) is not None

    def insert_link(self, product_id: int, category_id: int) -> int:
        cur = self.db.execute(
            f"INSERT INTO {P}virtuemart_product_categories "
            "(virtuemart_product_id, virtuemart_category_id, ordering) VALUES (%s, %s, 0)",
            (product_id, category_id),
        )
        return int(cur.lastrowid)
