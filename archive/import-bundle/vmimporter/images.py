"""Local image discovery and SKU matching.

Naming convention (documented in README): a file inside the images directory
belongs to the SKU that starts its filename, e.g.

    0405PT Black.jpg          -> SKU 0405PT
    0405 PT Orchid Mist.jpg   -> SKU "0405 PT" (or "0405PT", both match)
    0412.jpg                  -> SKU 0412 (exact)
    1022C-503 Detail.jpg      -> SKU 1022C-503 (hyphens are legitimate in SKUs)

Matching is robust against spaces/hyphens/underscores inside the SKU and
arbitrary descriptive text after it. When one file matches several CSV SKUs
(e.g. SKUs 0510 and 0510-1 both present), the LONGEST SKU wins.

Ordering within one SKU is deterministic: natural sort of the full filename
(digits compared numerically), so "X 2.jpg" sorts before "X 10.jpg".
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_SEP_RE = re.compile(r"[\s\-_]+")
_DIGITS_RE = re.compile(r"(\d+)")


def _norm(text: str) -> str:
    """Collapse spaces/hyphens/underscores to single spaces, casefolded."""
    return _SEP_RE.sub(" ", text).casefold().strip()


def _tight(text: str) -> str:
    """Remove all separators entirely (used as last-resort matching)."""
    return _SEP_RE.sub("", text).casefold()


def natural_key(name: str) -> list:
    key: list = []
    for part in _DIGITS_RE.split(name):
        if part.isdigit():
            key.append((1, int(part), ""))
        else:
            key.append((0, 0, part.casefold()))
    return key


@dataclass
class ImageFile:
    path: Path
    #: SKU this file was matched to
    sku: str
    #: quality of the match: 1 = exact stem, 2 = prefix, 3 = tight prefix
    match_rank: int


def scan_images(images_dir: str) -> tuple[list[Path], list[str]]:
    """Return (image_files, problems). Missing dir -> problem, not crash."""
    root = Path(images_dir)
    if not root.is_dir():
        return [], [f"images directory not found: {images_dir}"]
    files: list[Path] = []
    problems: list[str] = []
    for p in sorted(root.iterdir()):
        if p.is_dir():
            continue
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            problems.append(f"skipping non-image file: {p.name}")
            continue
        if p.stat().st_size == 0:
            problems.append(f"skipping empty file: {p.name}")
            continue
        files.append(p)
    return files, problems


def match_images(files: list[Path], skus: list[str]) -> tuple[dict[str, list[Path]], list[str]]:
    """Assign files to SKUs.

    Returns ({sku: [paths in deterministic order]}, warnings).
    A file matching no SKU is reported in warnings (the import continues).
    """
    warnings: list[str] = []
    # candidate evaluation: (rank, -len(sku), sku, path)
    best: dict[Path, tuple] = {}
    for path in files:
        stem = path.stem
        candidates: list[tuple] = []
        stem_tight = _tight(stem)
        for sku in skus:
            if stem.casefold() == sku.casefold():
                rank = 1
            elif _norm(stem).startswith(_norm(sku) + " ") or _norm(stem) == _norm(sku):
                rank = 2
            elif (_tight(sku) and stem_tight.startswith(_tight(sku))
                  # tight-prefix guard: "1022W Ava" must NOT match SKU "102"
                  # — a digit directly after the SKU means a DIFFERENT number,
                  # not descriptive text (e.g. "0510-1" is fine, "05101" is not)
                  and not stem_tight[len(_tight(sku)):][:1].isdigit()):
                rank = 3
            else:
                continue
            candidates.append((rank, -len(sku), sku, path))
        if not candidates:
            warnings.append(f"image does not match any SKU, ignored: {path.name}")
            continue
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))
        rank, _, sku, _ = candidates[0]
        beaten = [c[2] for c in candidates if c[2] != sku]
        if beaten:
            warnings.append(
                f"image {path.name} matched multiple SKUs ({', '.join(sorted(set(beaten + [sku])))}); "
                f"assigned to '{sku}'"
            )
        best[path] = (rank, -len(sku), sku)

    grouped: dict[str, list[Path]] = {}
    for path, (_, _, sku) in best.items():
        grouped.setdefault(sku, []).append(path)

    for paths in grouped.values():
        paths.sort(key=lambda p: natural_key(p.name))
    return grouped, warnings


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_image(src: Path, media_dir: str, url_prefix: str) -> str:
    """Copy the file into the VM media directory if not already present.

    Returns the relative file_url (the DB convention). An existing file with
    identical content is reused; an existing file with DIFFERENT content under
    the same name is refused (never overwrite server content).
    """
    dest_dir = Path(media_dir)
    dest = dest_dir / src.name
    if not dest.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    elif _file_hash(dest) != _file_hash(src):
        raise FileExistsError(
            f"destination exists with different content, refusing to overwrite: {dest}"
        )
    return f"{url_prefix}/{src.name}"
