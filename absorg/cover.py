# pyright: reportAttributeAccessIssue=false
"""Extract embedded cover art from audio files."""

from __future__ import annotations

import base64
import contextlib
import os
from typing import TYPE_CHECKING

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
    import mutagen
    from mutagen.mp4 import MP4

    audio = mutagen.File(filepath, easy=False)
    if audio is None or audio.tags is None:
        return None

    # ID3 (MP3) — APIC frames
    if hasattr(audio.tags, "getall"):
        apic_frames = audio.tags.getall("APIC")
        if apic_frames:
            return apic_frames[0].data

    # MP4 / M4A / M4B — covr atom
    if isinstance(audio, MP4):
        covers = audio.tags.get("covr")
        if covers:
            return bytes(covers[0])

    # FLAC — pictures attribute
    if hasattr(audio, "pictures") and audio.pictures:
        return audio.pictures[0].data

    # Vorbis (OGG, Opus) — metadata_block_picture
    if audio.tags and "metadata_block_picture" in audio.tags:
        from mutagen.flac import Picture

        raw = audio.tags["metadata_block_picture"]
        if raw:
            try:
                pic = Picture(base64.b64decode(raw[0]))
                return pic.data
            except Exception:
                pass

    return None
