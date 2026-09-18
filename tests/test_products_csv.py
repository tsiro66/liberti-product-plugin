"""CSV parsing / validation tests."""
from __future__ import annotations

import pytest

from vmimporter.products_csv import ValidationError, dedupe_keep_order, parse_csv, parse_price, split_multi


def test_split_multi():
    assert split_multi("35|36|37") == ["35", "36", "37"]
    assert split_multi(" BLK | RED ") == ["BLK", "RED"]
    assert split_multi("") == []
    assert split_multi(None) == []
    assert split_multi("|") == []
    assert split_multi("Leather") == ["Leather"]


def test_dedupe_keeps_order():
    assert dedupe_keep_order(["B", "A", "B", "C", "A"]) == (["B", "A", "C"], ["B", "A"])


def test_parse_price():
    assert parse_price("96.50") == (96.5, None)
    assert parse_price("96,50") == (96.5, None)          # European comma tolerated
    assert parse_price("77.82258")[0] == pytest.approx(77.82258)
    err = parse_price("abc")[1]
    assert err and "not a number" in err
    assert "empty" in parse_price("")[1]
    assert "> 0" in parse_price("0")[1]
    assert "> 0" in parse_price("-5")[1]
    assert parse_price("1.234,56")[1] is not None         # ambiguous -> error


def test_parse_example_csv():
    rows, _warnings = parse_csv("examples/products.example.csv")
    assert [r.sku for r in rows] == ["0405PT", "0406PT", "0412"]
    assert rows[0].sizes == ["36", "38", "40", "42", "44"]
    assert rows[0].colours == ["BLK", "NAVY", "MICRO"]
    assert rows[0].fabric == []
    assert rows[2].fabric == ["Satin"]
    assert rows[2].sizes == []
    assert rows[0].price_net == 96.5
    assert "Κολάν" in rows[0].description_el


def test_validation_duplicate_sku(tmp_path):
    csv = tmp_path / "d.csv"
    csv.write_text(
        "sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric\n"
        "A1,T,D,T,D,10,,,,\n"
        "A2,T,D,T,D,10,,,,\n"
        "a1,T,D,T,D,10,,,,\n",  # case-insensitive duplicate
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as e:
        parse_csv(str(csv))
    assert any("duplicate SKU" in p for p in e.value.problems)


def test_validation_collects_all_errors(tmp_path):
    csv = tmp_path / "d.csv"
    csv.write_text(
        "sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric,oops\n"
        ",T,D,T,D,10,,,,,\n"
        "A1,,D,T,D,not-a-price,,,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as e:
        parse_csv(str(csv))
    msgs = "\n".join(e.value.problems)
    assert "unknown column" in msgs
    assert "sku is empty" in msgs
    assert "title_en is empty" in msgs
    assert "not a number" in msgs


def test_validation_missing_required_column(tmp_path):
    csv = tmp_path / "d.csv"
    csv.write_text("sku,title_en\nA1,T\n", encoding="utf-8")
    with pytest.raises(ValidationError) as e:
        parse_csv(str(csv))
    assert "missing required column" in str(e.value)


def test_malformed_multi_value_detection(tmp_path):
    csv = tmp_path / "d.csv"
    csv.write_text(
        "sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric\n"
        'A1,T,D,T,D,10,"36\n38",,,\n',  # line break inside a size value
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as e:
        parse_csv(str(csv))
    assert any("malformed value" in p for p in e.value.problems)

    long_val = "X" * 2501
    csv2 = tmp_path / "d2.csv"
    csv2.write_text(
        "sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric\n"
        f"A1,T,D,T,D,10,{long_val},,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as e:
        parse_csv(str(csv2))
    assert any("2500 characters" in p for p in e.value.problems)
