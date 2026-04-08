"""Tests for dedup fingerprinting and collision detection."""

import os

from absorg.dedup import DedupAction, DedupTracker, fingerprint, precompute_fingerprints, quarantine


class TestFingerprint:
    def test_consistent(self, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"hello world" * 100)
        assert fingerprint(str(f)) == fingerprint(str(f))

    def test_different_content(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"aaa" * 100)
        b.write_bytes(b"bbb" * 100)
        assert fingerprint(str(a)) != fingerprint(str(b))

    def test_same_content_different_files(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        data = b"identical" * 100
        a.write_bytes(data)
        b.write_bytes(data)
        assert fingerprint(str(a)) == fingerprint(str(b))

    def test_format(self, tmp_path):
        f = tmp_path / "f.bin"
        f.write_bytes(b"x" * 50)
        fp = fingerprint(str(f))
        assert ":" in fp
        size_part, hash_part = fp.split(":")
        assert size_part == "50"
        assert len(hash_part) == 32  # MD5 hex length


class TestDedupTracker:
    def test_no_collision(self, tmp_path):
        src = tmp_path / "src.bin"
        src.write_bytes(b"data123")
        dest = str(tmp_path / "dest" / "file.bin")

        tracker = DedupTracker()
        result = tracker.check(str(src), dest)
        assert result.action == DedupAction.PROCEED
        assert result.dest_file == dest

    def test_in_run_duplicate(self, tmp_path):
        """Same fingerprint, same dest → QUARANTINE."""
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        data = b"same content here"
        a.write_bytes(data)
        b.write_bytes(data)

        dest = str(tmp_path / "dest" / "file.bin")
        tracker = DedupTracker()

        # First file claims the dest
        tracker.register(dest, str(a))

        # Second file with same content → quarantine
        result = tracker.check(str(b), dest)
        assert result.action == DedupAction.QUARANTINE

    def test_in_run_conflict(self, tmp_path):
        """Different fingerprint, same dest → renamed dest."""
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"content A")
        b.write_bytes(b"content B different")

        dest = str(tmp_path / "dest" / "file.bin")
        tracker = DedupTracker()

        tracker.register(dest, str(a))
        result = tracker.check(str(b), dest)

        assert result.action == DedupAction.PROCEED
        assert result.dest_file != dest
        assert ".2." in result.dest_file or result.dest_file.endswith(".2")

    def test_on_disk_duplicate(self, tmp_path):
        """File already at dest with same content → SKIP."""
        src = tmp_path / "src.bin"
        data = b"file content here"
        src.write_bytes(data)

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest_file = dest_dir / "file.bin"
        dest_file.write_bytes(data)

        tracker = DedupTracker()
        result = tracker.check(str(src), str(dest_file))
        assert result.action == DedupAction.SKIP

    def test_on_disk_conflict(self, tmp_path):
        """File at dest with different content → renamed dest."""
        src = tmp_path / "src.bin"
        src.write_bytes(b"new content")

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest_file = dest_dir / "file.bin"
        dest_file.write_bytes(b"old content different")

        tracker = DedupTracker()
        result = tracker.check(str(src), str(dest_file))
        assert result.action == DedupAction.PROCEED
        assert result.dest_file != str(dest_file)

    def test_find_free_dest_increments(self, tmp_path):
        tracker = DedupTracker()
        base = str(tmp_path / "file.mp3")

        # Claim the base and .2
        tracker.seen_dests[os.path.normpath(base)] = "fp1"
        expected_2 = str(tmp_path / "file.2.mp3")
        tracker.seen_dests[os.path.normpath(expected_2)] = "fp2"

        free = tracker.find_free_dest(base)
        assert free == str(tmp_path / "file.3.mp3")


class TestPrecomputeFingerprints:
    def test_basic(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        cache = precompute_fingerprints([str(a), str(b)], max_workers=2)
        assert len(cache) == 2
        norm_a = os.path.normpath(os.path.abspath(str(a)))
        norm_b = os.path.normpath(os.path.abspath(str(b)))
        assert norm_a in cache
        assert norm_b in cache
        assert cache[norm_a] == fingerprint(str(a))

    def test_missing_file_skipped(self, tmp_path):
        existing = tmp_path / "exists.bin"
        existing.write_bytes(b"data")
        cache = precompute_fingerprints(
            [str(existing), str(tmp_path / "nonexistent.bin")],
            max_workers=2,
        )
        assert len(cache) == 1


class TestDedupTrackerWithCache:
    def test_cache_hit(self, tmp_path):
        """Tracker uses pre-computed fingerprint from cache."""
        src = tmp_path / "src.bin"
        src.write_bytes(b"data123")
        dest = str(tmp_path / "dest" / "file.bin")

        cache = precompute_fingerprints([str(src)], max_workers=1)
        tracker = DedupTracker(fingerprint_cache=cache)
        result = tracker.check(str(src), dest)
        assert result.action == DedupAction.PROCEED

    def test_cache_miss_fallback(self, tmp_path):
        """Tracker computes fingerprint on demand for uncached files."""
        src = tmp_path / "src.bin"
        src.write_bytes(b"data456")
        dest = str(tmp_path / "dest" / "file.bin")

        # Empty cache — should fall back to live fingerprint
        tracker = DedupTracker(fingerprint_cache={})
        result = tracker.check(str(src), dest)
        assert result.action == DedupAction.PROCEED

    def test_cached_dedup_detects_duplicate(self, tmp_path):
        """Cached fingerprints still detect duplicates correctly."""
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        data = b"same content"
        a.write_bytes(data)
        b.write_bytes(data)

        cache = precompute_fingerprints([str(a), str(b)], max_workers=2)
        tracker = DedupTracker(fingerprint_cache=cache)
        dest = str(tmp_path / "dest" / "file.bin")

        tracker.register(dest, str(a))
        result = tracker.check(str(b), dest)
        assert result.action == DedupAction.QUARANTINE


class TestQuarantine:
    def test_live_quarantine(self, tmp_path, logger):
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        src_file = source_dir / "Author" / "Book" / "ch01.mp3"
        src_file.parent.mkdir(parents=True)
        src_file.write_bytes(b"audio data")

        dupes_dir = str(tmp_path / "dupes")

        quarantine(str(src_file), dupes_dir, str(source_dir), dry_run=False, reason="DUPLICATE", logger=logger)

        expected = os.path.join(dupes_dir, "Author", "Book", "ch01.mp3")
        assert os.path.exists(expected)
        assert not os.path.exists(str(src_file))

    def test_dry_run_no_move(self, tmp_path, logger):
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        src_file = source_dir / "file.mp3"
        src_file.write_bytes(b"data")

        dupes_dir = str(tmp_path / "dupes")

        quarantine(str(src_file), dupes_dir, str(source_dir), dry_run=True, reason="DUPLICATE", logger=logger)

        # File should still be at source
        assert os.path.exists(str(src_file))
        assert not os.path.exists(dupes_dir)
