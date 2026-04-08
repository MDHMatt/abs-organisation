"""Tests for book-level deduplication."""

import os

from absorg.bookdedup import (
    BookEdition,
    BookGroup,
    build_book_inventory,
    resolve_book_duplicates,
    score_edition,
)


class TestScoreEdition:
    def test_m4b_beats_mp3(self):
        m4b = BookEdition(source_dir="/a", format="m4b", year="2019", avg_bitrate=128000, total_duration=3600)
        mp3 = BookEdition(source_dir="/b", format="mp3", year="2019", avg_bitrate=128000, total_duration=3600)
        assert score_edition(m4b) > score_edition(mp3)

    def test_newer_year_beats_older(self):
        new = BookEdition(source_dir="/a", format="mp3", year="2019", avg_bitrate=128000, total_duration=3600)
        old = BookEdition(source_dir="/b", format="mp3", year="2014", avg_bitrate=128000, total_duration=3600)
        assert score_edition(new) > score_edition(old)

    def test_higher_bitrate_breaks_tie(self):
        hi = BookEdition(source_dir="/a", format="mp3", year="2019", avg_bitrate=192000, total_duration=3600)
        lo = BookEdition(source_dir="/b", format="mp3", year="2019", avg_bitrate=64000, total_duration=3600)
        assert score_edition(hi) > score_edition(lo)

    def test_longer_duration_breaks_tie(self):
        long = BookEdition(source_dir="/a", format="mp3", year="2019", avg_bitrate=128000, total_duration=7200)
        short = BookEdition(source_dir="/b", format="mp3", year="2019", avg_bitrate=128000, total_duration=3600)
        assert score_edition(long) > score_edition(short)

    def test_empty_year_scores_zero(self):
        no_year = BookEdition(source_dir="/a", format="mp3", year="", avg_bitrate=128000, total_duration=3600)
        with_year = BookEdition(source_dir="/b", format="mp3", year="2010", avg_bitrate=128000, total_duration=3600)
        assert score_edition(with_year) > score_edition(no_year)

    def test_format_trumps_year(self):
        """M4B from 2010 should beat MP3 from 2020."""
        m4b_old = BookEdition(source_dir="/a", format="m4b", year="2010", avg_bitrate=64000, total_duration=3600)
        mp3_new = BookEdition(source_dir="/b", format="mp3", year="2020", avg_bitrate=320000, total_duration=3600)
        assert score_edition(m4b_old) > score_edition(mp3_new)


class TestResolveBookDuplicates:
    def test_keeps_best_quarantines_rest(self):
        kept = BookEdition(source_dir="/kept", format="m4b", year="2019",
                           avg_bitrate=128000, total_duration=3600,
                           author="Author", book="Book", file_count=1)
        loser = BookEdition(source_dir="/loser", format="mp3", year="2014",
                            avg_bitrate=64000, total_duration=3600,
                            author="Author", book="Book", file_count=10)
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[kept, loser]),
        }
        quarantine_dirs, decisions = resolve_book_duplicates(groups)
        assert "/loser" in quarantine_dirs
        assert "/kept" not in quarantine_dirs
        assert len(decisions) == 1
        assert decisions[0].kept.source_dir == "/kept"

    def test_empty_groups(self):
        quarantine_dirs, decisions = resolve_book_duplicates({})
        assert quarantine_dirs == set()
        assert decisions == []

    def test_three_editions(self):
        best = BookEdition(source_dir="/best", format="m4b", year="2020",
                           avg_bitrate=128000, total_duration=3600,
                           author="A", book="B", file_count=1)
        mid = BookEdition(source_dir="/mid", format="mp3", year="2020",
                          avg_bitrate=128000, total_duration=3600,
                          author="A", book="B", file_count=10)
        worst = BookEdition(source_dir="/worst", format="mp3", year="2010",
                            avg_bitrate=64000, total_duration=3600,
                            author="A", book="B", file_count=10)
        groups = {
            ("a", "b"): BookGroup(norm_key=("a", "b"), editions=[worst, best, mid]),
        }
        quarantine_dirs, decisions = resolve_book_duplicates(groups)
        assert "/best" not in quarantine_dirs
        assert "/mid" in quarantine_dirs
        assert "/worst" in quarantine_dirs

    def test_decision_has_reason(self):
        kept = BookEdition(source_dir="/a", format="m4b", year="2019",
                           avg_bitrate=128000, total_duration=3600,
                           author="Author", book="Book", file_count=1)
        loser = BookEdition(source_dir="/b", format="mp3", year="2014",
                            avg_bitrate=64000, total_duration=3600,
                            author="Author", book="Book", file_count=10)
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[kept, loser]),
        }
        _, decisions = resolve_book_duplicates(groups)
        assert "M4B" in decisions[0].reason
        assert "MP3" in decisions[0].reason


class TestBuildBookInventory:
    def test_groups_by_normalised_key(self, make_mp3, tmp_path):
        """Two dirs with same book under different author names should group."""
        source = tmp_path / "source"
        source.mkdir()

        # Edition 1: "Neil Gaiman, Terry Pratchett"
        d1 = source / "Neil Gaiman, Terry Pratchett" / "Good Omens"
        d1.mkdir(parents=True)
        make_mp3_in = _make_mp3_helper(d1)
        make_mp3_in("ch01.mp3", album_artist="Neil Gaiman, Terry Pratchett", album="Good Omens")

        # Edition 2: "Neil Gaiman; Terry Pratchett"
        d2 = source / "Neil Gaiman; Terry Pratchett" / "Good Omens"
        d2.mkdir(parents=True)
        make_mp3_in2 = _make_mp3_helper(d2)
        make_mp3_in2("ch01.mp3", album_artist="Neil Gaiman; Terry Pratchett", album="Good Omens")

        from absorg.cli import _discover_audio_files
        files = _discover_audio_files(str(source))
        groups, cache = build_book_inventory(files, str(source))

        # Should have exactly 1 group with 2 editions
        assert len(groups) == 1
        group = list(groups.values())[0]
        assert len(group.editions) == 2

    def test_loose_root_files_separate_editions(self, tmp_path):
        """Each loose file at source root should be its own edition."""
        source = tmp_path / "source"
        source.mkdir()

        # Create two loose mp3 files at root
        for name in ["BookA.mp3", "BookB.mp3"]:
            path = source / name
            frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
            path.write_bytes(frame * 5)

        from absorg.cli import _discover_audio_files
        files = _discover_audio_files(str(source))
        groups, cache = build_book_inventory(files, str(source))

        # No groups with 2+ editions (each file is its own edition with different inferred book name)
        assert len(groups) == 0

    def test_single_edition_not_in_groups(self, tmp_path):
        """A book with only one edition should not appear in the groups dict."""
        source = tmp_path / "source"
        d = source / "Author" / "Book"
        d.mkdir(parents=True)

        path = d / "ch01.mp3"
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        path.write_bytes(frame * 5)

        from absorg.cli import _discover_audio_files
        files = _discover_audio_files(str(source))
        groups, cache = build_book_inventory(files, str(source))

        assert len(groups) == 0

    def test_cache_populated(self, tmp_path):
        """Metadata cache should have entries for all files."""
        source = tmp_path / "source"
        d = source / "Author" / "Book"
        d.mkdir(parents=True)

        path = d / "ch01.mp3"
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        path.write_bytes(frame * 5)

        from absorg.cli import _discover_audio_files
        files = _discover_audio_files(str(source))
        groups, cache = build_book_inventory(files, str(source))

        assert len(cache) == 1
        abs_path = os.path.abspath(str(path))
        assert abs_path in cache
        meta, ai = cache[abs_path]
        assert ai.codec == "mp3"


def _make_mp3_helper(directory):
    """Return a helper that creates tagged MP3 files in *directory*."""
    def _make(name, **tags):
        path = directory / name
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        path.write_bytes(frame * 5)

        if tags:
            import mutagen.mp3
            from mutagen.id3 import TALB, TIT2, TPE2, TRCK

            audio = mutagen.mp3.MP3(str(path))
            if audio.tags is None:
                audio.add_tags()
            tag_map = {
                "album_artist": lambda v: TPE2(encoding=3, text=[v]),
                "album": lambda v: TALB(encoding=3, text=[v]),
                "title": lambda v: TIT2(encoding=3, text=[v]),
                "track": lambda v: TRCK(encoding=3, text=[v]),
            }
            for key, value in tags.items():
                if key in tag_map:
                    audio.tags.add(tag_map[key](value))
            audio.save()
        return str(path)
    return _make
