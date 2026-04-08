# pyright: reportAttributeAccessIssue=false, reportPrivateImportUsage=false
"""Extract embedded cover art from audio files.

The file-level pyright pragma silences two categories of diagnostics
that stem from mutagen shipping without type stubs — see the matching
comment at the top of absorg/metadata.py for details. Runtime
narrowing of ``audio.tags`` uses :func:`typing.cast` for the same
reason (mutagen declares ``FileType.tags`` with a ``None`` class-level
default, so ``isinstance`` asserts would land at ``Never``).
"""

from __future__ import annotations

import base64
import contextlib
import os
from typing import TYPE_CHECKING, cast

import mutagen
from mutagen._vorbis import VComment
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

if TYPE_CHECKING:
    from absorg.logger import AbsorgLogger


def extract_cover(source_file: str, dest_dir: str, logger: AbsorgLogger) -> bool:
    """Extract the first embedded image from *source_file* as ``cover.jpg``.

    Returns ``True`` if a cover was written, ``False`` otherwise.
    Idempotent: skips if ``cover.jpg`` already exists.
    """
    cover_path = os.path.join(dest_dir, "cover.jpg")
    if os.path.exists(cover_path):
        return False

    try:
        image_data = _read_cover_bytes(source_file)
    except Exception:
        return False

    if not image_data:
        return False

    try:
        with open(cover_path, "wb") as f:
            f.write(image_data)
        return True
    except OSError as exc:
        logger.logr(f"  Failed to write cover art: {exc}")
        # Clean up partial file
        with contextlib.suppress(OSError):
            os.remove(cover_path)
        return False


def _read_cover_bytes(filepath: str) -> bytes | None:
    """Return raw image bytes from *filepath*, or ``None``."""
    audio = mutagen.File(filepath, easy=False)
    if audio is None or audio.tags is None:
        return None

    # ID3 (MP3) — APIC frames. The tag object on an MP3 is an ID3
    # instance; cast() narrows it so getall() is visible.
    if isinstance(audio.tags, ID3):
        id3_tags = cast("ID3", audio.tags)
        apic_frames = id3_tags.getall("APIC")
        if apic_frames:
            return getattr(apic_frames[0], "data", None)

    # MP4 / M4A / M4B — covr atom
    if isinstance(audio, MP4) and audio.tags is not None:
        mp4_tags = cast("mutagen.mp4.MP4Tags", audio.tags)
        covers = mp4_tags.get("covr")
        if covers:
            return bytes(covers[0])

    # FLAC — pictures attribute (Picture.data also populated dynamically)
    if isinstance(audio, FLAC) and audio.pictures:
        return getattr(audio.pictures[0], "data", None)

    # Vorbis (OGG, Opus) — metadata_block_picture. VComment inherits from
    # list but behaves as a dict-like at runtime via __getitem__(str); we
    # cast to dict[str, list[str]] so pyright treats the key access as a
    # dict lookup rather than a list slice.
    if isinstance(audio.tags, VComment):
        vc_tags = cast("dict[str, list[str]]", audio.tags)
        if "metadata_block_picture" in vc_tags:
            raw = vc_tags["metadata_block_picture"]
            if raw:
                try:
                    pic = Picture(base64.b64decode(raw[0]))
                    return getattr(pic, "data", None)
                except Exception:
                    pass

    return None
