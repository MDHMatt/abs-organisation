"""Tests for book-level deduplication."""

import os

from absorg.audioinfo import AudioInfo
from absorg.bookdedup import (
    BookEdition,
    BookGroup,
    build_book_inventory,
    resolve_book_duplicates,
    resolve_intra_edition_duplicates,
    score_edition,
)
from absorg.metadata import MetadataResult


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


def _norm(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


class TestResolveBookDuplicates:
    def test_keeps_best_quarantines_rest(self):
        kept_file = _norm("/kept/file.m4b")
        loser_file = _norm("/loser/file.mp3")
        kept = BookEdition(source_dir="/kept", files=[kept_file], format="m4b", year="2019",
                           avg_bitrate=128000, total_duration=3600,
                           author="Author", book="Book", file_count=1)
        loser = BookEdition(source_dir="/loser", files=[loser_file], format="mp3", year="2014",
                            avg_bitrate=64000, total_duration=3600,
                            author="Author", book="Book", file_count=10)
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[kept, loser]),
        }
        quarantine_files, decisions = resolve_book_duplicates(groups)
        assert loser_file in quarantine_files
        assert kept_file not in quarantine_files
        assert len(decisions) == 1
        assert decisions[0].kept.source_dir == "/kept"

    def test_empty_groups(self):
        quarantine_files, decisions = resolve_book_duplicates({})
        assert quarantine_files == set()
        assert decisions == []

    def test_three_editions(self):
        best_file = _norm("/best/file.m4b")
        mid_file = _norm("/mid/file.mp3")
        worst_file = _norm("/worst/file.mp3")
        best = BookEdition(source_dir="/best", files=[best_file], format="m4b", year="2020",
                           avg_bitrate=128000, total_duration=3600,
                           author="A", book="B", file_count=1)
        mid = BookEdition(source_dir="/mid", files=[mid_file], format="mp3", year="2020",
                          avg_bitrate=128000, total_duration=3600,
                          author="A", book="B", file_count=10)
        worst = BookEdition(source_dir="/worst", files=[worst_file], format="mp3", year="2010",
                            avg_bitrate=64000, total_duration=3600,
                            author="A", book="B", file_count=10)
        groups = {
            ("a", "b"): BookGroup(norm_key=("a", "b"), editions=[worst, best, mid]),
        }
        quarantine_files, decisions = resolve_book_duplicates(groups)
        assert best_file not in quarantine_files
        assert mid_file in quarantine_files
        assert worst_file in quarantine_files

    def test_decision_has_reason(self):
        kept_file = _norm("/a/file.m4b")
        loser_file = _norm("/b/file.mp3")
        kept = BookEdition(source_dir="/a", files=[kept_file], format="m4b", year="2019",
                           avg_bitrate=128000, total_duration=3600,
                           author="Author", book="Book", file_count=1)
        loser = BookEdition(source_dir="/b", files=[loser_file], format="mp3", year="2014",
                            avg_bitrate=64000, total_duration=3600,
                            author="Author", book="Book", file_count=10)
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[kept, loser]),
        }
        _, decisions = resolve_book_duplicates(groups)
        assert "M4B" in decisions[0].reason
        assert "MP3" in decisions[0].reason

    def test_quarantines_all_files_in_loser_edition(self):
        """A loser edition with multiple files should quarantine every one."""
        kept_file = _norm("/kept/file.m4b")
        loser_files = [_norm(f"/loser/ch{i:02d}.mp3") for i in range(1, 4)]
        kept = BookEdition(source_dir="/kept", files=[kept_file], format="m4b", year="2019",
                           avg_bitrate=128000, total_duration=3600,
                           author="Author", book="Book", file_count=1)
        loser = BookEdition(source_dir="/loser", files=loser_files, format="mp3", year="2014",
                            avg_bitrate=64000, total_duration=3600,
                            author="Author", book="Book", file_count=3)
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[kept, loser]),
        }
        quarantine_files, _ = resolve_book_duplicates(groups)
        for f in loser_files:
            assert f in quarantine_files
        assert kept_file not in quarantine_files


class TestStructuralTiebreaker:
    """Issue 12: when score_edition ties, the structural tiebreaker must
    prefer better-organised paths over typos, placeholders, and loose
    root-level files."""

    def _edition(self, source_dir, files, author="Adrian Tchaikovsky", book="Children of Memory"):
        return BookEdition(
            source_dir=source_dir,
            files=[_norm(f) for f in files],
            format="m4b",
            year="2022",
            avg_bitrate=125000,
            total_duration=48366,
            author=author,
            book=book,
            file_count=len(files),
        )

    def test_correct_spelling_beats_typo(self, tmp_path):
        """Adrian Tchaikovsky (correct) must beat Adrian Tchikovski (typo)."""
        source = str(tmp_path)
        correct_dir = os.path.join(source, "Adrian Tchaikovsky", "Children of Memory")
        typo_dir = os.path.join(source, "Adrian Tchikovski", "Children of Memory")
        os.makedirs(correct_dir)
        os.makedirs(typo_dir)

        correct = self._edition(correct_dir, [os.path.join(correct_dir, "file.m4b")])
        typo = self._edition(typo_dir, [os.path.join(typo_dir, "file.m4b")])

        # Put the typo first in the list to make sure the old alphabetical-
        # last-wins-under-reverse bug would pick it; the fix must flip it.
        groups = {
            ("adrian tchaikovsky", "children of memory"): BookGroup(
                norm_key=("adrian tchaikovsky", "children of memory"),
                editions=[typo, correct],
            ),
        }
        _, decisions = resolve_book_duplicates(groups, source_dir=source)
        assert decisions[0].kept.source_dir == correct_dir, (
            f"Expected correct-spelling folder to be kept, got {decisions[0].kept.source_dir}"
        )

    def test_tagged_author_beats_placeholder_unknown(self, tmp_path):
        """Arthur Conan Doyle folder must beat _Unknown Author/Sherlock Holmes."""
        source = str(tmp_path)
        tagged_dir = os.path.join(source, "Arthur Conan Doyle", "Sherlock Holmes")
        placeholder_dir = os.path.join(source, "_Unknown Author", "Sherlock Holmes [B06X1BRZYC]")
        os.makedirs(tagged_dir)
        os.makedirs(placeholder_dir)

        tagged = self._edition(
            tagged_dir, [os.path.join(tagged_dir, "file.m4b")],
            author="Arthur Conan Doyle", book="Sherlock Holmes",
        )
        placeholder = self._edition(
            placeholder_dir, [os.path.join(placeholder_dir, "file.m4b")],
            author="Arthur Conan Doyle", book="Sherlock Holmes",
        )

        groups = {
            ("arthur conan doyle", "sherlock holmes"): BookGroup(
                norm_key=("arthur conan doyle", "sherlock holmes"),
                editions=[placeholder, tagged],
            ),
        }
        _, decisions = resolve_book_duplicates(groups, source_dir=source)
        assert decisions[0].kept.source_dir == tagged_dir

    def test_organised_folder_beats_root_loose_file(self, tmp_path):
        """Andy Weir/The Martian (folder) must beat /The Martian.m4b (root-loose)."""
        source = str(tmp_path)
        folder_dir = os.path.join(source, "Andy Weir", "The Martian")
        os.makedirs(folder_dir)
        loose_file = os.path.join(source, "The Martian.m4b")
        # inventory stores the full file path as source_dir for root-loose files
        folder_edition = self._edition(
            folder_dir, [os.path.join(folder_dir, "file.m4b")],
            author="Andy Weir", book="The Martian",
        )
        loose_edition = BookEdition(
            source_dir=loose_file,
            files=[_norm(loose_file)],
            format="m4b",
            year="2022",
            avg_bitrate=125000,
            total_duration=48366,
            author="Andy Weir",
            book="The Martian",
            file_count=1,
        )
        # The loose file must actually exist on disk for the tiebreak key
        # to recognise it as a file vs directory. Create a stub.
        with open(loose_file, "wb") as f:
            f.write(b"")

        groups = {
            ("andy weir", "martian"): BookGroup(
                norm_key=("andy weir", "martian"),
                editions=[loose_edition, folder_edition],
            ),
        }
        _, decisions = resolve_book_duplicates(groups, source_dir=source)
        assert decisions[0].kept.source_dir == folder_dir

    def test_higher_score_still_wins_over_tiebreak(self, tmp_path):
        """Score_edition must still dominate the tiebreak when scores differ."""
        source = str(tmp_path)
        # Score differs: good_dir is an MP3 (lower format_score),
        # bad_dir is an M4B (higher format_score). Tiebreak would prefer
        # good_dir, but score must win.
        good_dir = os.path.join(source, "Adrian Tchaikovsky", "Children of Memory")
        bad_dir = os.path.join(source, "_Unknown Author", "Children of Memory")
        os.makedirs(good_dir)
        os.makedirs(bad_dir)

        mp3_good = BookEdition(
            source_dir=good_dir, files=[_norm(os.path.join(good_dir, "f.mp3"))],
            format="mp3", year="2022", avg_bitrate=128000, total_duration=3600,
            author="Adrian Tchaikovsky", book="Children of Memory", file_count=1,
        )
        m4b_bad = BookEdition(
            source_dir=bad_dir, files=[_norm(os.path.join(bad_dir, "f.m4b"))],
            format="m4b", year="2022", avg_bitrate=128000, total_duration=3600,
            author="Adrian Tchaikovsky", book="Children of Memory", file_count=1,
        )
        groups = {
            ("adrian tchaikovsky", "children of memory"): BookGroup(
                norm_key=("adrian tchaikovsky", "children of memory"),
                editions=[mp3_good, m4b_bad],
            ),
        }
        _, decisions = resolve_book_duplicates(groups, source_dir=source)
        assert decisions[0].kept.source_dir == bad_dir  # M4B wins on score


class TestBitrateReasonSuppression:
    """Issue 13: higher-bitrate reason must be suppressed when both sides
    round to the same kbps display value."""

    def test_sub_kbps_tie_suppresses_reason(self, tmp_path):
        """62,800 bps vs 62,100 bps must not emit 'higher bitrate (62kbps vs 62kbps)'."""
        source = str(tmp_path)
        a_dir = os.path.join(source, "A", "B")
        c_dir = os.path.join(source, "C", "B")
        os.makedirs(a_dir)
        os.makedirs(c_dir)

        hi = BookEdition(
            source_dir=a_dir, files=[_norm(os.path.join(a_dir, "f.m4b"))],
            format="m4b", year="2019", avg_bitrate=62800, total_duration=3600,
            author="Author", book="Book", file_count=1,
        )
        lo = BookEdition(
            source_dir=c_dir, files=[_norm(os.path.join(c_dir, "f.m4b"))],
            format="m4b", year="2019", avg_bitrate=62100, total_duration=3600,
            author="Author", book="Book", file_count=1,
        )
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[hi, lo]),
        }
        _, decisions = resolve_book_duplicates(groups, source_dir=source)
        assert "higher bitrate" not in decisions[0].reason
        assert "62kbps vs 62kbps" not in decisions[0].reason

    def test_multi_kbps_delta_still_emits_reason(self, tmp_path):
        """A 114 vs 113 kbps delta must still emit the reason."""
        source = str(tmp_path)
        a_dir = os.path.join(source, "A", "B")
        c_dir = os.path.join(source, "C", "B")
        os.makedirs(a_dir)
        os.makedirs(c_dir)

        hi = BookEdition(
            source_dir=a_dir, files=[_norm(os.path.join(a_dir, "f.m4b"))],
            format="m4b", year="2019", avg_bitrate=114000, total_duration=3600,
            author="Author", book="Book", file_count=1,
        )
        lo = BookEdition(
            source_dir=c_dir, files=[_norm(os.path.join(c_dir, "f.m4b"))],
            format="m4b", year="2019", avg_bitrate=113000, total_duration=3600,
            author="Author", book="Book", file_count=1,
        )
        groups = {
            ("author", "book"): BookGroup(norm_key=("author", "book"), editions=[hi, lo]),
        }
        _, decisions = resolve_book_duplicates(groups, source_dir=source)
        assert "higher bitrate (114kbps vs 113kbps)" in decisions[0].reason


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

        # Each file is its own edition (different inferred book name), no multi-edition groups
        assert all(len(g.editions) == 1 for g in groups.values())

    def test_single_edition_has_one_edition(self, tmp_path):
        """A book with only one edition should appear as a single-edition group."""
        source = tmp_path / "source"
        d = source / "Author" / "Book"
        d.mkdir(parents=True)

        path = d / "ch01.mp3"
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        path.write_bytes(frame * 5)

        from absorg.cli import _discover_audio_files
        files = _discover_audio_files(str(source))
        groups, cache = build_book_inventory(files, str(source))

        assert len(groups) == 1
        assert len(list(groups.values())[0].editions) == 1

    def test_multi_book_container_splits_into_sub_editions(self, tmp_path):
        """A directory holding files with different album tags becomes multiple editions."""
        source = tmp_path / "source"
        container = source / "Author" / "Trilogy"
        container.mkdir(parents=True)
        helper = _make_mp3_helper(container)
        helper("book1.mp3", album_artist="Author", album="Book One")
        helper("book2.mp3", album_artist="Author", album="Book Two")
        helper("book3.mp3", album_artist="Author", album="Book Three")

        from absorg.cli import _discover_audio_files
        files = _discover_audio_files(str(source))
        groups, _cache = build_book_inventory(files, str(source))
        # Each distinct book appears only once -> three single-edition groups.
        assert all(len(g.editions) == 1 for g in groups.values())

        # Add a standalone copy of Book Two; it should group with the container sub-edition.
        standalone = source / "Author" / "Book Two"
        standalone.mkdir(parents=True)
        _make_mp3_helper(standalone)("only.mp3", album_artist="Author", album="Book Two")
        files = _discover_audio_files(str(source))
        groups, _cache = build_book_inventory(files, str(source))
        # 3 groups total; only Book Two has 2 editions
        multi = {k: v for k, v in groups.items() if len(v.editions) >= 2}
        assert len(multi) == 1
        g = list(multi.values())[0]
        assert len(g.editions) == 2
        for ed in g.editions:
            assert ed.file_count == 1

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


class TestIntraEditionDedup:
    """Tests for resolve_intra_edition_duplicates (Issue 11)."""

    def _make_group(self, files_and_durations, author="Author", book="Book"):
        """Build a BookGroup + metadata_cache from a list of (path, duration) pairs."""
        metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]] = {}
        file_paths = []
        for fpath, dur in files_and_durations:
            abs_path = os.path.abspath(fpath)
            file_paths.append(abs_path)
            metadata_cache[abs_path] = (
                MetadataResult(author=author, book=book),
                AudioInfo(duration=dur, bitrate=62000, codec="aac"),
            )

        edition = BookEdition(
            source_dir=os.path.dirname(file_paths[0]) if file_paths else "/tmp",
            files=file_paths,
            author=author,
            book=book,
            format="m4b",
            total_duration=sum(d for _, d in files_and_durations),
            avg_bitrate=62000,
            file_count=len(file_paths),
        )
        group = BookGroup(
            norm_key=("author", "book"),
            editions=[edition],
        )
        return {("author", "book"): group}, metadata_cache, edition

    def test_detects_same_duration_same_ext(self, tmp_path):
        """Files with matching duration and ext should be detected as duplicates."""
        groups, cache, _ = self._make_group([
            (str(tmp_path / "Book.m4b"), 44827.5),
            (str(tmp_path / "Book.2.m4b"), 44827.5),
            (str(tmp_path / "Book.3.m4b"), 44827.5),
        ])
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert len(qf) == 2
        assert len(decisions) == 1

    def test_keeps_clean_name_over_suffixed(self, tmp_path):
        """The file without .N suffix should be kept."""
        clean = str(tmp_path / "Book.m4b")
        suf2 = str(tmp_path / "Book.2.m4b")
        suf3 = str(tmp_path / "Book.3.m4b")
        groups, cache, _ = self._make_group([
            (clean, 44827.5), (suf2, 44827.5), (suf3, 44827.5),
        ])
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert _norm(clean) not in qf
        assert _norm(suf2) in qf
        assert _norm(suf3) in qf

    def test_different_durations_not_grouped(self, tmp_path):
        """Files with different durations should NOT be grouped."""
        groups, cache, _ = self._make_group([
            (str(tmp_path / "ch01.m4b"), 3600.0),
            (str(tmp_path / "ch02.2.m4b"), 7200.0),
            (str(tmp_path / "ch03.3.m4b"), 1800.0),
        ])
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert len(qf) == 0

    def test_different_extensions_not_grouped(self, tmp_path):
        """Same duration but different extensions should NOT be grouped."""
        cache: dict[str, tuple[MetadataResult, AudioInfo]] = {}
        mp3 = os.path.abspath(str(tmp_path / "ch01.mp3"))
        m4b = os.path.abspath(str(tmp_path / "book.2.m4b"))
        cache[mp3] = (MetadataResult(author="A", book="B"), AudioInfo(duration=3600, bitrate=128000, codec="mp3"))
        cache[m4b] = (MetadataResult(author="A", book="B"), AudioInfo(duration=3600, bitrate=62000, codec="aac"))
        edition = BookEdition(
            source_dir=str(tmp_path), files=[mp3, m4b], author="A", book="B",
            format="m4b", total_duration=7200, avg_bitrate=95000, file_count=2,
        )
        groups = {("a", "b"): BookGroup(norm_key=("a", "b"), editions=[edition])}
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert len(qf) == 0

    def test_single_file_edition(self, tmp_path):
        """An edition with 1 file should produce no quarantine."""
        groups, cache, _ = self._make_group([
            (str(tmp_path / "Book.m4b"), 44827.5),
        ])
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert len(qf) == 0
        assert len(decisions) == 0

    def test_edition_stats_corrected(self, tmp_path):
        """After intra-dedup, edition stats should reflect only kept files."""
        groups, cache, edition = self._make_group([
            (str(tmp_path / "Book.m4b"), 44827.5),
            (str(tmp_path / "Book.2.m4b"), 44827.5),
            (str(tmp_path / "Book.3.m4b"), 44827.5),
        ])
        resolve_intra_edition_duplicates(groups, cache)
        assert edition.file_count == 1
        assert edition.total_duration == 44827.5

    def test_no_suffix_evidence_skips_cluster(self, tmp_path):
        """Files with matching duration but no .N suffix should NOT be quarantined."""
        groups, cache, _ = self._make_group([
            (str(tmp_path / "disc1.m4b"), 3600.0),
            (str(tmp_path / "disc2.m4b"), 3600.0),
        ])
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert len(qf) == 0

    def test_zero_duration_skipped(self, tmp_path):
        """Files with duration=0 should be excluded from clustering."""
        groups, cache, _ = self._make_group([
            (str(tmp_path / "Book.m4b"), 0.0),
            (str(tmp_path / "Book.2.m4b"), 0.0),
        ])
        qf, decisions = resolve_intra_edition_duplicates(groups, cache)
        assert len(qf) == 0
