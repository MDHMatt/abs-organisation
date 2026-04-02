"""End-to-end integration tests for the CLI."""

import os

import pytest

from absorg.cli import Counters, _discover_audio_files, main, parse_args


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

        from mutagen.mp3 import MP3
        from mutagen.id3 import TPE2, TALB, TIT2

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

        from mutagen.mp3 import MP3
        from mutagen.id3 import TPE2, TALB, TIT2

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
