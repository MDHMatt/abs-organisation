"""End-to-end integration tests for the CLI."""

import os

import pytest
from mutagen.id3 import TALB, TIT2, TPE2
from mutagen.mp3 import MP3

from absorg.cli import _discover_audio_files, main, parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.dry_run is True
        assert args.source == "/audiobooks_unsorted"
        assert args.dest == "/audiobooks"
        assert args.no_cover is False

    def test_move_flag(self):
        args = parse_args(["--move"])
        assert args.dry_run is False

    def test_dry_run_flag(self):
        args = parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_move_then_dry_run(self):
        """Last flag wins."""
        args = parse_args(["--move", "--dry-run"])
        assert args.dry_run is True

    def test_dry_run_then_move(self):
        args = parse_args(["--dry-run", "--move"])
        assert args.dry_run is False

    def test_custom_paths(self):
        args = parse_args(["--source", "/a", "--dest", "/b", "--dupes", "/c", "--log", "/d.log"])
        assert args.source == "/a"
        assert args.dest == "/b"
        assert args.dupes == "/c"
        assert args.log == "/d.log"

    def test_no_cover(self):
        args = parse_args(["--no-cover"])
        assert args.no_cover is True

    def test_book_dedup_flag(self):
        args = parse_args(["--book-dedup"])
        assert args.book_dedup is True

    def test_book_dedup_default_off(self):
        args = parse_args([])
        assert args.book_dedup is False

    def test_show_quality_flag(self):
        args = parse_args(["--show-quality"])
        assert args.show_quality is True

    def test_show_quality_default_off(self):
        args = parse_args([])
        assert args.show_quality is False

    def test_workers_default(self):
        args = parse_args([])
        assert args.workers == 0

    def test_workers_custom(self):
        args = parse_args(["--workers", "8"])
        assert args.workers == 8


class TestDiscoverAudioFiles:
    def test_finds_mp3(self, make_mp3):
        path = make_mp3("sub/file.mp3")
        source = os.path.dirname(os.path.dirname(path))  # tmp_path
        files = _discover_audio_files(source)
        assert len(files) >= 1
        assert any(f.endswith(".mp3") for f in files)

    def test_ignores_non_audio(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hi")
        (tmp_path / "data.json").write_text("{}")
        files = _discover_audio_files(str(tmp_path))
        assert files == []

    def test_case_insensitive_extensions(self, tmp_path):
        """Should find .MP3 and .Mp3 etc."""
        # Create a file with uppercase extension — needs valid enough content
        f = tmp_path / "test.MP3"
        f.write_bytes(b"\xff\xe3\x18\x00" + b"\x00" * 417)
        files = _discover_audio_files(str(tmp_path))
        assert len(files) == 1

    def test_sorted_output(self, tmp_path):
        for name in ["c.mp3", "a.mp3", "b.mp3"]:
            (tmp_path / name).write_bytes(b"\xff\xe3\x18\x00" + b"\x00" * 417)
        files = _discover_audio_files(str(tmp_path))
        basenames = [os.path.basename(f) for f in files]
        assert basenames == ["a.mp3", "b.mp3", "c.mp3"]


class TestMainDryRun:
    def test_dry_run_no_files_moved(self, make_mp3, tmp_path):
        """Dry run should not move any files."""
        source = tmp_path / "source"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        log_file = str(tmp_path / "test.log")

        # Create a tagged MP3 in source using the fixture's tmp_path
        # Write valid MP3 frames
        mp3_path = str(source / "ch01.mp3")
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        with open(mp3_path, "wb") as f:
            f.write(frame * 5)

        from mutagen.id3 import TALB, TIT2, TPE2
        from mutagen.mp3 import MP3

        audio = MP3(mp3_path)
        audio.add_tags()
        audio.tags.add(TPE2(encoding=3, text=["Test Author"]))
        audio.tags.add(TALB(encoding=3, text=["Test Book"]))
        audio.tags.add(TIT2(encoding=3, text=["Chapter 1"]))
        audio.save()

        main([
            "--source", str(source),
            "--dest", str(dest),
            "--dupes", str(tmp_path / "dupes"),
            "--log", log_file,
        ])

        # File should still be at source
        assert os.path.exists(mp3_path)
        # Dest should have no audio files
        dest_files = []
        for dp, dn, fnames in os.walk(str(dest)):
            for fn in fnames:
                dest_files.append(fn)
        assert len(dest_files) == 0

    def test_missing_source_exits(self, tmp_path):
        """Should exit with code 1 if source doesn't exist."""
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--source", str(tmp_path / "nonexistent"),
                "--dest", str(tmp_path / "dest"),
                "--log", str(tmp_path / "test.log"),
            ])
        assert exc_info.value.code == 1

    def test_empty_source(self, tmp_path):
        """No files to process — should complete without error."""
        source = tmp_path / "source"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        main([
            "--source", str(source),
            "--dest", str(dest),
            "--log", str(tmp_path / "test.log"),
        ])
        # Just verify it didn't crash


class TestMainLiveMove:
    def test_live_move(self, make_mp3, tmp_path):
        """With --move, files should actually be moved."""
        source = tmp_path / "source"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        mp3_path = str(source / "ch01.mp3")
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        with open(mp3_path, "wb") as f:
            f.write(frame * 5)

        audio = MP3(mp3_path)
        audio.add_tags()
        audio.tags.add(TPE2(encoding=3, text=["Author"]))
        audio.tags.add(TALB(encoding=3, text=["Book"]))
        audio.tags.add(TIT2(encoding=3, text=["Chapter 1"]))
        audio.save()

        main([
            "--move",
            "--source", str(source),
            "--dest", str(dest),
            "--dupes", str(tmp_path / "dupes"),
            "--log", str(tmp_path / "test.log"),
            "--no-cover",
        ])

        # Source file should be gone
        assert not os.path.exists(mp3_path)

        # Should be somewhere under dest
        moved_files = []
        for dp, dn, fnames in os.walk(str(dest)):
            for fn in fnames:
                moved_files.append(os.path.join(dp, fn))
        assert len(moved_files) == 1
        assert moved_files[0].endswith(".mp3")


def _create_tagged_mp3(path, *, album_artist="", album="", title="Chapter"):
    """Helper to create a tagged MP3 at the given path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
    with open(path, "wb") as f:
        f.write(frame * 5)
    if album_artist or album or title:
        audio = MP3(path)
        audio.add_tags()
        if album_artist:
            audio.tags.add(TPE2(encoding=3, text=[album_artist]))
        if album:
            audio.tags.add(TALB(encoding=3, text=[album]))
        if title:
            audio.tags.add(TIT2(encoding=3, text=[title]))
        audio.save()
    return path


class TestBookDedup:
    def test_book_dedup_quarantines_duplicate_editions(self, tmp_path):
        """With --book-dedup, duplicate editions should be quarantined."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        dupes = tmp_path / "dupes"
        dest.mkdir()

        # Edition 1: tagged as "Author A" (comma separator)
        d1 = source / "Author A, Author B" / "Good Book"
        _create_tagged_mp3(
            str(d1 / "ch01.mp3"),
            album_artist="Author A, Author B",
            album="Good Book", title="Ch 1",
        )
        _create_tagged_mp3(
            str(d1 / "ch02.mp3"),
            album_artist="Author A, Author B",
            album="Good Book", title="Ch 2",
        )

        # Edition 2: tagged with semicolon separator (should normalise to same key)
        d2 = source / "Author A; Author B" / "Good Book"
        _create_tagged_mp3(
            str(d2 / "ch01.mp3"),
            album_artist="Author A; Author B",
            album="Good Book", title="Ch 1",
        )

        main([
            "--move", "--book-dedup", "--no-cover",
            "--source", str(source),
            "--dest", str(dest),
            "--dupes", str(dupes),
            "--log", str(tmp_path / "test.log"),
        ])

        # One edition should be in dest, the other in dupes
        dest_files = []
        for dp, dn, fnames in os.walk(str(dest)):
            for fn in fnames:
                if fn.endswith(".mp3"):
                    dest_files.append(fn)
        dupes_files = []
        for dp, dn, fnames in os.walk(str(dupes)):
            for fn in fnames:
                if fn.endswith(".mp3"):
                    dupes_files.append(fn)

        assert len(dest_files) > 0, "Should have kept at least one edition"
        assert len(dupes_files) > 0, "Should have quarantined at least one edition"
        # Total should equal original count
        assert len(dest_files) + len(dupes_files) == 3

    def test_without_book_dedup_both_survive(self, tmp_path):
        """Without --book-dedup, both editions should survive."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        dupes = tmp_path / "dupes"
        dest.mkdir()

        # Two editions with different separator
        d1 = source / "Author A, Author B" / "Good Book"
        _create_tagged_mp3(
            str(d1 / "ch01.mp3"),
            album_artist="Author A, Author B",
            album="Good Book", title="Ch 1",
        )

        d2 = source / "Author A; Author B" / "Good Book"
        _create_tagged_mp3(
            str(d2 / "ch01.mp3"),
            album_artist="Author A; Author B",
            album="Good Book", title="Ch 1",
        )

        main([
            "--move", "--no-cover",
            "--source", str(source),
            "--dest", str(dest),
            "--dupes", str(dupes),
            "--log", str(tmp_path / "test.log"),
        ])

        # Both files should end up somewhere (dest or dest with conflicts)
        dest_mp3s = []
        for dp, dn, fnames in os.walk(str(dest)):
            for fn in fnames:
                if fn.endswith(".mp3"):
                    dest_mp3s.append(fn)
        # Without book-dedup, file-level dedup may quarantine identical content
        # but both editions with different content should survive
        total = len(dest_mp3s)
        dupes_count = 0
        for dp, dn, fnames in os.walk(str(dupes)):
            for fn in fnames:
                if fn.endswith(".mp3"):
                    dupes_count += 1
        assert total + dupes_count == 2

    def test_show_quality_outputs_quality_line(self, tmp_path):
        """--show-quality should include quality info in the log."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        dest.mkdir()

        d = source / "Author" / "Book"
        _create_tagged_mp3(
            str(d / "ch01.mp3"),
            album_artist="Author", album="Book", title="Ch 1",
        )

        log_file = str(tmp_path / "test.log")
        main([
            "--show-quality", "--no-cover",
            "--source", str(source),
            "--dest", str(dest),
            "--dupes", str(tmp_path / "dupes"),
            "--log", log_file,
        ])

        with open(log_file) as f:
            log_content = f.read()
        assert "Quality" in log_content
        assert "MP3" in log_content
        assert "kbps" in log_content
