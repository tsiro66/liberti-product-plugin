"""Image matching / copying tests."""
from __future__ import annotations

import pytest

from vmimporter.images import copy_image, match_images, natural_key, scan_images


def make_files(tmp_path, names):
    root = tmp_path / "images"
    root.mkdir(exist_ok=True)
    for n in names:
        (root / n).write_bytes(b"x" * 10)
    return root


def test_exact_and_prefix_matching(tmp_path):
    root = make_files(tmp_path, ["0405PT Black.jpg", "0412.jpg", "0406PT Front.jpg"])
    files, problems = scan_images(str(root))
    assert not problems
    grouped, warnings = match_images(files, ["0405PT", "0412", "0406PT"])
    assert grouped["0405PT"] == [root / "0405PT Black.jpg"]
    assert grouped["0412"] == [root / "0412.jpg"]
    assert grouped["0406PT"] == [root / "0406PT Front.jpg"]
    assert not warnings


def test_space_inside_sku_matches_via_tight_normalisation(tmp_path):
    # file uses "0405 PT", CSV uses "0405PT" (and vice versa) — both must match
    root = make_files(tmp_path, ["0405 PT Orchid Mist.jpg"])
    files, _ = scan_images(str(root))
    grouped, warnings = match_images(files, ["0405PT"])
    assert grouped["0405PT"] == [root / "0405 PT Orchid Mist.jpg"]
    assert not warnings


def test_longest_sku_wins(tmp_path):
    root = make_files(tmp_path, ["0510-1 Matt Ribbon.png"])
    files, _ = scan_images(str(root))
    grouped, warnings = match_images(files, ["0510", "0510-1"])
    assert grouped["0510-1"] == [root / "0510-1 Matt Ribbon.png"]
    assert grouped.get("0510") is None
    assert any("multiple SKUs" in w for w in warnings)


def test_unmatched_file_reported(tmp_path):
    root = make_files(tmp_path, ["Katya Satin.jpg"])
    files, _ = scan_images(str(root))
    grouped, warnings = match_images(files, ["0405PT"])
    assert grouped == {}
    assert any("does not match any SKU" in w for w in warnings)


def test_natural_ordering(tmp_path):
    root = make_files(tmp_path, ["SKU 10 b.jpg", "SKU 2 a.jpg", "SKU 1.jpg"])
    files, _ = scan_images(str(root))
    grouped, _ = match_images(files, ["SKU"])
    assert [p.name for p in grouped["SKU"]] == ["SKU 1.jpg", "SKU 2 a.jpg", "SKU 10 b.jpg"]


def test_natural_key_digits():
    assert natural_key("X 10.jpg") > natural_key("X 2.jpg")
    assert natural_key("a1") < natural_key("a2")


def test_scan_rejects_non_images_and_empty_files(tmp_path):
    root = make_files(tmp_path, ["ok.jpg", "note.txt", "empty.jpg"])
    (root / "empty.jpg").write_bytes(b"")
    files, problems = scan_images(str(root))
    assert [f.name for f in files] == ["ok.jpg"]
    assert len(problems) == 2


def test_missing_images_dir(tmp_path):
    files, problems = scan_images(str(tmp_path / "nope"))
    assert files == []
    assert problems and "not found" in problems[0]


def test_copy_image_never_overwrites(tmp_path):
    src = tmp_path / "a.jpg"
    src.write_bytes(b"AAAA")
    dest_dir = tmp_path / "server"
    url = copy_image(src, str(dest_dir), "images/stories/virtuemart/product")
    assert url == "images/stories/virtuemart/product/a.jpg"
    assert (dest_dir / "a.jpg").read_bytes() == b"AAAA"

    # same content -> reuse, no error
    copy_image(src, str(dest_dir), "images/stories/virtuemart/product")

    # different content with same name -> refuse
    src.write_bytes(b"BBBB")
    with pytest.raises(FileExistsError):
        copy_image(src, str(dest_dir), "images/stories/virtuemart/product")
