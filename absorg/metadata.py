"""Mutagen-based metadata extraction for audiobook files.

Reads audio file tags using mutagen and resolves them into a structured
MetadataResult via the priority chains defined in constants.METADATA_TAG_CHAINS.
Handles format-specific quirks across ID3 (MP3), MP4/M4A/M4B, Vorbis
(FLAC/OGG/Opus), and ASF (WMA).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, fields
from typing import Any

import mutagen
import mutagen.id3
import mutagen.mp4
import mutagen.asf

from absorg.constants import METADATA_TAG_CHAINS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEADING_DIGITS_RE = re.compile(r"^\s*(\d+)")


def _parse_int(value: str) -> str:
    """Extract leading digits from a string like '3/12' or '  7 '. Returns '' on failure."""
    m = _LEADING_DIGITS_RE.match(value)
    return m.group(1) if m else ""


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


def _normalise_id3(file: mutagen.FileType) -> dict[str, str]:
    """Normalise ID3 tags (MP3) to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    for frame in file.tags.values():
        frame_id = frame.FrameID if hasattr(frame, "FrameID") else ""

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
        if hasattr(frame, "text") and frame.text:
            tags[frame_id.lower()] = str(frame.text[0])

    return tags


def _normalise_mp4(file: mutagen.FileType) -> dict[str, str]:
    """Normalise MP4/M4A/M4B tags to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    for key, value in file.tags.items():
        # Freeform atoms: ----:com.apple.iTunes:SERIES -> txxx:series
        if key.startswith("----:"):
            parts = key.split(":")
            if len(parts) >= 3:
                norm_key = f"txxx:{parts[2]}".lower()
                raw = value[0] if value else b""
                tags[norm_key] = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            continue

        # Track/disc atoms return lists of (number, total) tuples
        if key in ("trkn", "disk"):
            if value and isinstance(value[0], tuple):
                tags[key] = str(value[0][0])
            continue

        # Cover art -- skip
        if key == "covr":
            continue

        # Standard atoms
        norm_key = _MP4_KEY_MAP.get(key, _MP4_KEY_MAP.get(key.lower(), key.lower()))
        if value:
            raw = value[0]
            tags[norm_key] = str(raw)

    return tags


def _normalise_vorbis(file: mutagen.FileType) -> dict[str, str]:
    """Normalise Vorbis comments (FLAC, OGG, Opus) to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    for key, values in file.tags.items():
        if values:
            tags[key.lower()] = str(values[0]) if isinstance(values, list) else str(values)

    return tags


def _normalise_asf(file: mutagen.FileType) -> dict[str, str]:
    """Normalise ASF/WMA tags to a flat lowercase-keyed dict."""
    tags: dict[str, str] = {}
    if file.tags is None:
        return tags

    for key, values in file.tags.items():
        norm_key = _ASF_KEY_MAP.get(key.lower(), key.lower())
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

    if isinstance(file.tags, mutagen.asf.ASFTag):
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

    # Clear series if it is identical to the book title (not useful info).
    if result.series and result.series == result.book:
        result.series = ""

    return result
