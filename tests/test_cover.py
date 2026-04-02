"""Tests for cover art extraction."""

import os

import pytest

from absorg.cover import extract_cover


class TestExtractCover:
    def test_skip_if_cover_exists(self, tmp_path, logger):
        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"existing")
        result = extract_cover("whatever.mp3", str(tmp_path), logger)
        assert result is False

    def test_no_art_returns_false(self, make_mp3, tmp_path, logger):
        """MP3 with no embedded art → returns False."""
        path = make_mp3("bare.mp3", artist="Test")
        dest = str(tmp_path / "output")
        os.makedirs(dest)
        result = extract_cover(path, dest, logger)
        assert result is False
        assert not os.path.exists(os.path.join(dest, "cover.jpg"))

    def test_nonexistent_file_returns_false(self, tmp_path, logger):
        dest = str(tmp_path / "output")
        os.makedirs(dest)
        result = extract_cover(str(tmp_path / "nope.mp3"), dest, logger)
        assert result is False

    def test_extract_from_mp3_with_art(self, make_mp3, tmp_path, logger):
        """MP3 with embedded APIC frame → cover.jpg written."""
        from mutagen.mp3 import MP3
        from mutagen.id3 import APIC

        path = make_mp3("art.mp3", artist="Test")
        audio = MP3(path)
        # Add a minimal JPEG-like cover
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        audio.tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,  # Cover (front)
            desc="Cover",
            data=fake_jpeg,
        ))
        audio.save()

        dest = str(tmp_path / "output")
        os.makedirs(dest)
        result = extract_cover(path, dest, logger)
        assert result is True

        cover_path = os.path.join(dest, "cover.jpg")
        assert os.path.exists(cover_path)
        with open(cover_path, "rb") as f:
            assert f.read() == fake_jpeg

    def test_idempotent_after_extract(self, make_mp3, tmp_path, logger):
        """Second call should return False since cover.jpg exists."""
        from mutagen.mp3 import MP3
        from mutagen.id3 import APIC

        path = make_mp3("art.mp3", artist="Test")
        audio = MP3(path)
        audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover",
                            data=b"\xff\xd8\xff\xe0" + b"\x00" * 50))
        audio.save()

        dest = str(tmp_path / "output")
        os.makedirs(dest)

        assert extract_cover(path, dest, logger) is True
        assert extract_cover(path, dest, logger) is False  # already exists
