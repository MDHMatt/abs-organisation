# pyright: reportAttributeAccessIssue=false, reportPrivateImportUsage=false
"""Mutagen-based metadata extraction for audiobook files.

Reads audio file tags using mutagen and resolves them into a structured
MetadataResult via the priority chains defined in constants.METADATA_TAG_CHAINS.
Handles format-specific quirks across ID3 (MP3), MP4/M4A/M4B, Vorbis
(FLAC/OGG/Opus), and ASF (WMA).

The file-level pyright pragma silences two categories of diagnostics
that stem from mutagen shipping without type stubs:

* ``reportAttributeAccessIssue`` — frame attributes like ``text``,
  ``desc``, ``FrameID``, and ``data`` are populated dynamically by
  mutagen's ``_framespec`` mechanism, which pyright cannot see.
* ``reportPrivateImportUsage`` — mutagen exports many public names
  (``FileType``, ``TXXX``, ``TextFrame``, ``ASFBaseAttribute``, etc.)
  via re-export rather than via ``__all__``, so pyright treats them
  as private imports.

Runtime narrowing of ``file.tags`` is done with :func:`typing.cast`
rather than ``isinstance`` asserts because pyright infers
``FileType.tags`` as ``None`` (from the mutagen class-level default
``tags = None``) so ``isinstance`` would narrow to ``Never``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any, cast

import mutagen
import mutagen.asf
import mutagen.id3
import mutagen.mp4
from mutagen._vorbis import VComment

from absorg.constants import METADATA_TAG_CHAINS
from absorg.constants import parse_int as _parse_int

if TYPE_CHECKING:
    from mutagen._file import FileType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Format-specific tag normalisation
# ---------------------------------------------------------------------------

# MP4 iTunes atom key -> normalised tag name
_MP4_KEY_MAP: dict[str, str] = {
    "\xa9ART": "artist",
    "\xa9art": "artist",
    "aART": "album_artist",
    "aart": "album_artist",
    "\xa9alb": "album",
    "\xa9nam": "title",
    "\xa9wrt": "composer",
    "\xa9grp": "grouping",
    "\xa9day": "date",
    "\xa9gen": "genre",
    "\xa9wrk": "work",
    "\xa9mvn": "movement_name",
    "\xa9mvi": "movementnumber",
    "trkn": "trkn",
    "disk": "disk",
    "soar": "sort_artist",
    "soal": "sort_album",
}

# ASF (WMA) attribute name -> normalised tag name
_ASF_KEY_MAP: dict[str, str] = {
    "author": "artist",
    "title": "title",
    "wm/albumtitle": "album",
    "wm/albumartist": "album_artist",
    "wm/year": "date",
    "wm/genre": "genre",
    "wm/tracknumber": "track",
    "wm/track": "track",
    "wm/composer": "composer",
    "wm/subtitle": "subtitle",
    "wm/partofset": "disc",
}


def _normalise_id3(file: FileType) -> dict[str, str]:
    """Normalise ID3 tags (MP3) to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    # Narrow file.tags from mutagen's abstract Tags base to the concrete
    # ID3 dict-like view so the type checker sees .values() / .getall().
    # cast() is required rather than `isinstance` because mutagen declares
    # FileType.tags with a None default and no annotation, so pyright
    # narrows it to `None` and any `isinstance` assert would land at Never.
    id3_tags = cast("mutagen.id3.ID3", file.tags)

    for frame in id3_tags.values():
        frame_id = getattr(frame, "FrameID", "") or ""

        if isinstance(frame, mutagen.id3.TXXX):
            # Custom text frames: store as txxx:{description}
            key = f"txxx:{frame.desc}".lower()
            value = str(frame.text[0]) if frame.text else ""
            tags[key] = value
            continue

        if isinstance(frame, mutagen.id3.TextFrame):
            key = frame_id.lower()
            value = str(frame.text[0]) if frame.text else ""
            tags[key] = value
            continue

        # Numeric frames (track, disc) also derive from TextFrame in mutagen,
        # but just in case a subclass isn't caught above:
        text = getattr(frame, "text", None)
        if text:
            tags[frame_id.lower()] = str(text[0])

    return tags


def _normalise_mp4(file: FileType) -> dict[str, str]:
    """Normalise MP4/M4A/M4B tags to a flat lowercase-keyed dict.

    MP4 atoms come in three flavours that all need different handling:

    1. **Freeform atoms** (``----:com.apple.iTunes:SERIES``) — vendor-
       specific tags. Stored under the ``txxx:`` namespace so they share
       a key space with ID3 custom frames in :data:`METADATA_TAG_CHAINS`.
    2. **Numeric pair atoms** (``trkn``, ``disk``) — return ``(number,
       total)`` tuples; we keep just the leading number as a string so
       the post-processing in :func:`resolve_metadata` can extract digits.
    3. **Standard atoms** (``\\xa9alb``, ``aART`` etc.) — looked up in
       ``_MP4_KEY_MAP`` and stored under their normalised name.
    """
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    # See _normalise_id3 for why cast() is used here instead of isinstance.
    mp4_tags = cast("mutagen.mp4.MP4Tags", file.tags)

    for key, value in mp4_tags.items():
        # Freeform atoms: ----:com.apple.iTunes:SERIES -> txxx:series
        if key.startswith("----:"):
            parts = key.split(":")
            if len(parts) >= 3:
                norm_key = f"txxx:{parts[2]}".lower()
                raw = value[0] if value else b""
                tags[norm_key] = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            continue

        # Track/disc atoms: flatten the (number, total) tuple to just the number,
        # so resolve_metadata's _parse_int can extract leading digits uniformly
        # across formats.
        if key in ("trkn", "disk"):
            if value and isinstance(value[0], tuple):
                tags[key] = str(value[0][0])
            continue

        # Skip cover art — it's a binary blob, not a string tag, and the
        # cover-extraction module reads it directly via mutagen.
        if key == "covr":
            continue

        # Standard atoms
        norm_key = _MP4_KEY_MAP.get(key) or _MP4_KEY_MAP.get(key.lower()) or key.lower()
        if value:
            raw = value[0]
            tags[norm_key] = str(raw)

    return tags


def _normalise_vorbis(file: FileType) -> dict[str, str]:
    """Normalise Vorbis comments (FLAC, OGG, Opus) to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    # VComment is the shared base for VCFLACDict / OggVCommentDict / etc.
    # See _normalise_id3 for why cast() is used instead of isinstance.
    vc_tags = cast("VComment", file.tags)

    for key, values in vc_tags.items():
        if values:
            tags[key.lower()] = str(values[0]) if isinstance(values, list) else str(values)

    return tags


def _normalise_asf(file: FileType) -> dict[str, str]:
    """Normalise ASF/WMA tags to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    # See _normalise_id3 for why cast() is used here instead of isinstance.
    asf_tags = cast("mutagen.asf.ASFTags", file.tags)

    # WMA tag values come back as a list of ASFBaseAttribute objects, where
    # the actual string lives on .value. Older mutagen versions occasionally
    # hand back a plain string, so handle both shapes.
    for key, values in asf_tags.items():
        norm_key = _ASF_KEY_MAP.get(key.lower()) or key.lower()
        if values:
            raw = values[0]
            tags[norm_key] = str(raw.value) if isinstance(raw, mutagen.asf.ASFBaseAttribute) else str(raw)

    return tags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_tags(filepath: str) -> dict[str, str]:
    """Open *filepath* with mutagen and return a flat dict of lowercase tag keys to string values.

    Returns an empty dict if the file cannot be read or has no tags.
    """
    try:
        file = mutagen.File(filepath, easy=False)
    except Exception:
        logger.debug("mutagen could not open: %s", filepath)
        return {}

    if file is None:
        return {}

    # Dispatch based on the concrete tag type.
    tag_type: Any = type(file.tags)

    if tag_type is None or file.tags is None:
        return {}

    if isinstance(file.tags, mutagen.id3.ID3):
        return _normalise_id3(file)

    if isinstance(file, mutagen.mp4.MP4):
        return _normalise_mp4(file)

    if isinstance(file.tags, mutagen.asf.ASFTags):
        return _normalise_asf(file)

    # Vorbis comments (FLAC, OGG, Opus) -- treated as the generic fallback
    # since VComment is a dict-like with list values.
    if hasattr(file.tags, "items"):
        return _normalise_vorbis(file)

    return {}


def get_tag(tags: dict[str, str], *keys: str) -> str:
    """Return the first non-empty, stripped value found for the given *keys* (case-insensitive).

    Returns ``""`` if no match is found.
    """
    # Build a lowercase view once for the lookup.
    lower_tags: dict[str, str] | None = None

    for key in keys:
        lk = key.lower()
        # Fast path: direct hit.
        val = tags.get(lk)
        if val is not None:
            stripped = val.strip()
            if stripped:
                return stripped

        # Slow path: caller may have mixed-case keys in the dict.
        if lower_tags is None:
            lower_tags = {k.lower(): v for k, v in tags.items()}
        val = lower_tags.get(lk)
        if val is not None:
            stripped = val.strip()
            if stripped:
                return stripped

    return ""


@dataclass
class MetadataResult:
    """Structured metadata extracted from an audio file."""

    author: str = ""
    book: str = ""
    title: str = ""
    track: str = ""          # digits only, or empty
    disc: str = ""           # digits only, or empty
    series: str = ""
    series_index: str = ""   # digits only, or empty
    narrator: str = ""
    year: str = ""           # first 4 chars, or empty
    subtitle: str = ""
    genre: str = ""


def resolve_metadata(filepath: str) -> MetadataResult:
    """Read tags from *filepath* and resolve them into a :class:`MetadataResult`.

    Each field is resolved by trying the priority chain defined in
    ``METADATA_TAG_CHAINS``.  Post-processing is applied to numeric
    fields and the year.  Returns a default (all-empty) result on
    any failure.
    """
    try:
        tags = load_tags(filepath)
    except Exception:
        logger.debug("Failed to load tags for: %s", filepath)
        return MetadataResult()

    result = MetadataResult()

    for field in fields(result):
        chain = METADATA_TAG_CHAINS.get(field.name)
        if chain is None:
            continue
        value = get_tag(tags, *chain)
        setattr(result, field.name, value)

    # --- Post-processing ---

    # Numeric fields: extract leading digits only.
    result.track = _parse_int(result.track)
    result.disc = _parse_int(result.disc)
    result.series_index = _parse_int(result.series_index)

    # Year: keep only the first 4 characters (handles "2023-04-01" etc.).
    if result.year:
        result.year = result.year[:4]

    # Clear series if it is identical to the book title. Some taggers
    # populate ALBUM and SERIES with the same string, which would
    # otherwise cause pathbuilder to emit a duplicate ``Series/Book``
    # path segment like ``Foo/Foo/`` for every file in the book.
    if result.series and result.series == result.book:
        result.series = ""

    return result
