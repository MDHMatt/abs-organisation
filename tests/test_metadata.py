"""Tests for metadata extraction via mutagen."""

import os

import pytest

from absorg.metadata import MetadataResult, get_tag, load_tags, resolve_metadata


class TestGetTag:
    def test_direct_hit(self):
        tags = {"artist": "Author Name"}
        assert get_tag(tags, "artist") == "Author Name"

    def test_case_insensitive(self):
        tags = {"ARTIST": "Author Name"}
        assert get_tag(tags, "artist") == "Author Name"

    def test_priority_order(self):
        tags = {"artist": "Artist", "album_artist": "Album Artist"}
        assert get_tag(tags, "album_artist", "artist") == "Album Artist"

    def test_skips_empty(self):
        tags = {"album_artist": "", "artist": "Fallback"}
        assert get_tag(tags, "album_artist", "artist") == "Fallback"

    def test_skips_whitespace_only(self):
        tags = {"album_artist": "   ", "artist": "Fallback"}
        assert get_tag(tags, "album_artist", "artist") == "Fallback"

    def test_no_match(self):
        tags = {"genre": "Fiction"}
        assert get_tag(tags, "artist", "album_artist") == ""

    def test_empty_tags(self):
        assert get_tag({}, "artist") == ""

    def test_strips_whitespace(self):
        tags = {"artist": "  Name  "}
        assert get_tag(tags, "artist") == "Name"


class TestLoadTags:
    def test_mp3_basic_tags(self, make_mp3):
        path = make_mp3("test.mp3", artist="Artist", album="Album", title="Title")
        tags = load_tags(path)
        assert tags.get("tpe1") == "Artist"
        assert tags.get("talb") == "Album"
        assert tags.get("tit2") == "Title"

    def test_mp3_txxx_tags(self, make_mp3):
        path = make_mp3("test.mp3", **{"txxx:SERIES": "My Series"})
        tags = load_tags(path)
        assert tags.get("txxx:series") == "My Series"

    def test_nonexistent_file(self, tmp_path):
        tags = load_tags(str(tmp_path / "nonexistent.mp3"))
        assert tags == {}

    def test_non_audio_file(self, tmp_path):
        txt = tmp_path / "test.txt"
        txt.write_text("not audio")
        tags = load_tags(str(txt))
        assert tags == {}

    def test_mp3_track_number(self, make_mp3):
        path = make_mp3("test.mp3", track="3/12")
        tags = load_tags(path)
        assert tags.get("trck") == "3/12"


class TestResolveMetadata:
    def test_mp3_full_metadata(self, make_mp3):
        path = make_mp3(
            "test.mp3",
            album_artist="Author",
            album="Book Title",
            title="Chapter 1",
            track="5/20",
            disc="1/2",
        )
        result = resolve_metadata(path)
        assert result.author == "Author"
        assert result.book == "Book Title"
        assert result.title == "Chapter 1"
        assert result.track == "5"
        assert result.disc == "1"

    def test_no_tags_returns_empty(self, make_mp3):
        path = make_mp3("empty.mp3")
        result = resolve_metadata(path)
        assert result.author == ""
        assert result.book == ""
        assert result.title == ""

    def test_artist_fallback_when_no_album_artist(self, make_mp3):
        path = make_mp3("test.mp3", artist="The Artist")
        result = resolve_metadata(path)
        assert result.author == "The Artist"

    def test_series_cleared_when_equals_book(self, make_mp3):
        """Series should be empty when it's identical to the book title."""
        path = make_mp3(
            "test.mp3",
            album="Same Title",
            **{"txxx:SERIES": "Same Title"},
        )
        result = resolve_metadata(path)
        assert result.book == "Same Title"
        assert result.series == ""

    def test_series_kept_when_different(self, make_mp3):
        path = make_mp3(
            "test.mp3",
            album="Book One",
            **{"txxx:SERIES": "Epic Series"},
        )
        result = resolve_metadata(path)
        assert result.series == "Epic Series"

    def test_year_truncated_to_four(self, make_mp3):
        """Year like '2023-04-01' should become '2023'."""
        from mutagen.mp3 import MP3
        from mutagen.id3 import TDRC

        path = make_mp3("test.mp3", artist="Placeholder")
        audio = MP3(path)
        audio.tags.add(TDRC(encoding=3, text=["2023-04-01"]))
        audio.save()

        result = resolve_metadata(path)
        assert result.year == "2023"

    def test_nonexistent_returns_empty(self, tmp_path):
        result = resolve_metadata(str(tmp_path / "nope.mp3"))
        assert result == MetadataResult()

    def test_metadata_result_defaults(self):
        result = MetadataResult()
        assert result.author == ""
        assert result.track == ""
        assert result.series_index == ""
