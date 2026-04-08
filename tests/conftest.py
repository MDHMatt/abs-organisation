"""Shared test fixtures for absorg."""

import os

import pytest

from absorg.logger import AbsorgLogger


@pytest.fixture
def logger(tmp_path):
    """Provide a logger that writes to a temp file."""
    log = AbsorgLogger(str(tmp_path / "test.log"))
    yield log
    log.close()


@pytest.fixture
def make_mp3(tmp_path):
    """Return a helper that creates minimal valid MP3 files with optional ID3 tags.

    Usage::

        path = make_mp3("author/book/ch01.mp3", artist="Foo", album="Bar")
    """

    def _make(rel_path: str, **tags: str) -> str:
        full = os.path.join(str(tmp_path), rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)

        # Build a minimal valid MP3: MPEG1 Layer3 128kbps 44100Hz
        # Header: 0xFF 0xFB (sync + MPEG1/Layer3/no CRC), 0x90 (128kbps/44100Hz/no pad), 0x00
        # Frame size = 144 * 128000 / 44100 = 417 bytes (including 4-byte header)
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        # Mutagen needs at least 4 valid frames to sync
        data = frame * 5

        with open(full, "wb") as f:
            f.write(data)

        if tags:
            import mutagen.mp3
            from mutagen.id3 import TALB, TIT2, TPE1, TPE2, TPOS, TRCK, TXXX

            audio = mutagen.mp3.MP3(full)
            if audio.tags is None:
                audio.add_tags()

            tag_map = {
                "title": lambda v: TIT2(encoding=3, text=[v]),
                "artist": lambda v: TPE1(encoding=3, text=[v]),
                "album_artist": lambda v: TPE2(encoding=3, text=[v]),
                "album": lambda v: TALB(encoding=3, text=[v]),
                "track": lambda v: TRCK(encoding=3, text=[v]),
                "disc": lambda v: TPOS(encoding=3, text=[v]),
            }

            for key, value in tags.items():
                if key in tag_map:
                    audio.tags.add(tag_map[key](value))
                elif key.startswith("txxx:"):
                    desc = key[5:]
                    audio.tags.add(TXXX(encoding=3, desc=desc, text=[value]))
                else:
                    # Try as generic TXXX
                    audio.tags.add(TXXX(encoding=3, desc=key.upper(), text=[value]))

            audio.save()

        return full

    return _make


@pytest.fixture
def source_dir(tmp_path):
    """Return a temporary source directory path."""
    src = tmp_path / "source"
    src.mkdir()
    return str(src)


@pytest.fixture
def dest_dir(tmp_path):
    """Return a temporary destination directory path."""
    dst = tmp_path / "dest"
    dst.mkdir()
    return str(dst)
