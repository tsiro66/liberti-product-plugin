"""Slug + price conversion tests."""
from __future__ import annotations

import pytest

from vmimporter.slug import slugify, unique_slug


def test_slugify_ascii():
    assert slugify("Tights 0405PT with Inside Brushing") == "tights-0405pt-with-inside-brushing"
    assert slugify("Go Dance Latin Shoes CD004 Tight Crosscut & Plated Heel") == (
        "go-dance-latin-shoes-cd004-tight-crosscut-plated-heel"
    )


def test_slugify_greek_falls_back():
    # Greek has no ASCII transliteration under NFKD -> empty -> 'product'
    assert slugify("Κολάν") == "product"


def test_slugify_mixed_greek_latin():
    assert slugify("Κολάν 0405PT") == "0405pt"


def test_unique_slug():
    taken = {"tights", "tights-2"}
    assert unique_slug("tights", taken) == "tights-3"
    assert unique_slug("fresh", taken) == "fresh"


def test_net_price_passthrough():
    from vmimporter.config import Config
    from vmimporter.importer import ProductImporter
    from vmimporter.products_csv import ProductRow

    cfg = Config(price_mode="net")
    imp = ProductImporter.__new__(ProductImporter)
    imp.cfg = cfg
    row = ProductRow(1, "X", "", "", "", "", "77.82258", [], [], [], price_net=77.82258)
    assert imp.net_price(row) == pytest.approx(77.82258)


def test_gross_price_conversion_matches_dump_rounding():
    from vmimporter.config import Config
    from vmimporter.importer import ProductImporter
    from vmimporter.products_csv import ProductRow

    cfg = Config(price_mode="gross", vat_rate=24.0)
    imp = ProductImporter.__new__(ProductImporter)
    imp.cfg = cfg
    row = ProductRow(1, "X", "", "", "", "", "96.50", [], [], [], price_net=96.50)
    # 96.50 / 1.24 = 77.822580645... -> 6 dp (decimal(15,6) precision of the DB)
    assert imp.net_price(row) == pytest.approx(77.822581)
