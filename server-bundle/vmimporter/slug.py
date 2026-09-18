"""Slug generation.

Convention observed in the dump: both language tables carry the SAME slug
(CD004 -> 'cd004'/'cd004', category 62 -> 'latin-shoes'/'latin-shoes'), and the
slug is ASCII. Therefore the slug for a new product is derived from the ENGLISH
title and written to both language tables. Uniqueness is enforced per table.
"""
from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    """Lowercase ASCII slug; falls back to 'product' for exotic input."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text or "product"


def unique_slug(base: str, taken: set[str], max_len: int = 240) -> str:
    """Return base, or base-2, base-3 ... until not in `taken`."""
    slug = base[:max_len]
    counter = 2
    while slug in taken:
        suffix = f"-{counter}"
        slug = base[: max_len - len(suffix)] + suffix
        counter += 1
    return slug
