"""Author and book name normalisation for book-level deduplication."""

from __future__ import annotations

import re
import unicodedata

from absorg.constants import AUDIBLE_ID_RE, ROLE_QUALIFIERS_RE, TRANSLITERATE_MAP


def _strip_accents(text: str) -> str:
    """Remove combining marks after NFKD decomposition, then transliterate."""
    nfkd = unicodedata.normalize("NFKD", text)
    # Strip combining marks (category M)
    stripped = "".join(ch for ch in nfkd if unicodedata.category(ch)[0] != "M")
    # Apply manual transliteration for chars that don't decompose via NFKD
    return stripped.translate(TRANSLITERATE_MAP)


def normalise_author(name: str) -> str:
    """Return a canonical grouping key for an author name.

    Handles: case, accents, separator variants (``; `` vs ``, ``),
    name ordering, and role qualifiers (``- introductions``, etc.).
    """
    if not name:
        return ""
    s = name.casefold()
    s = _strip_accents(s)
    # Normalise separator: ; → ,
    s = s.replace(";", ",")
    # Strip role qualifiers (e.g. "- introductions", "- narrator")
    s = re.sub(ROLE_QUALIFIERS_RE, "", s, flags=re.IGNORECASE)
    # Strip parenthetical annotations (e.g. "(narrator)")
    s = re.sub(r"\s*\([^)]*\)", "", s)
    # Split on comma, sort, rejoin for order-independence
    parts = [p.strip() for p in s.split(",") if p.strip()]
    parts.sort()
    s = ", ".join(parts)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalise_book(name: str) -> str:
    """Return a canonical grouping key for a book title.

    Handles: case, accents, Audible IDs, subtitles, leading articles.
    """
    if not name:
        return ""
    s = name.casefold()
    s = _strip_accents(s)
    # Strip Audible IDs like [B0743JTTWQ]
    s = re.sub(AUDIBLE_ID_RE, "", s, flags=re.IGNORECASE)
    # Strip numeric IDs like [1338589016]
    s = re.sub(r"\s*\[\d{10,}\]", "", s)
    # Strip subtitles after : or  -  (only if result would be 3+ chars)
    for sep in (":", " - "):
        if sep in s:
            candidate = s[: s.index(sep)].strip()
            if len(candidate) >= 3:
                s = candidate
                break
    # Strip leading articles
    for article in ("the ", "a ", "an "):
        if s.startswith(article):
            candidate = s[len(article):]
            # Don't strip if result would be too short
            if len(candidate) >= 2:
                s = candidate
            break
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s
