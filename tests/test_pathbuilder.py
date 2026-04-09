"""Tests for build_dest path construction."""

import os

from absorg.metadata import MetadataResult
from absorg.pathbuilder import build_dest


def _meta(**kwargs) -> MetadataResult:
    return MetadataResult(**kwargs)


class TestBuildDest:
    def test_basic_author_book(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(author="Author", book="Book", title="Chapter"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert result.dest_dir == os.path.join(dest, "Author", "Book")
        assert result.dest_file == os.path.join(dest, "Author", "Book", "Chapter.mp3")
        assert result.no_meta is False

    def test_m4b_uses_book_title(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.m4b",
            metadata=_meta(author="Author", book="My Book", title="Chapter 1"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert result.dest_file.endswith("My Book.m4b")

    def test_series_with_index(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(author="Author", book="Book", series="Series", series_index="3", title="Ch"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.join("Series", "03 - Book") in result.dest_dir

    def test_series_without_index(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(author="Author", book="Book", series="Series", title="Ch"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.join("Series", "Book") in result.dest_dir
        assert "03" not in result.dest_dir

    def test_track_number_prefix(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(author="A", book="B", title="Title", track="5"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "05 - Title.mp3"

    def test_multi_disc_prefix(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(author="A", book="B", title="Title", track="3", disc="2"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "D02-T03 - Title.mp3"

    def test_disc_1_no_disc_prefix(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(author="A", book="B", title="Title", track="3", disc="1"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "03 - Title.mp3"

    def test_no_meta_falls_back_to_unknown(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert "_Unknown Author" in result.dest_dir
        assert "_Unknown Book" in result.dest_dir
        assert result.no_meta is True

    def test_inference_fallback(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.mp3",
            metadata=_meta(),
            infer_path=("Inferred Author", "Inferred Book"),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert "Inferred Author" in result.dest_dir
        assert "Inferred Book" in result.dest_dir
        assert result.no_meta is True  # still no_meta since tags were empty

    def test_extension_lowercased(self, tmp_path):
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/file.MP3",
            metadata=_meta(author="A", book="B", title="Title"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert result.dest_file.endswith(".mp3")

    def test_filename_stem_fallback_strips_existing_track_prefix(self, tmp_path):
        """Re-running over an already-prefixed filename must not stack another prefix (#10)."""
        dest = str(tmp_path)
        # No title tag, filename already has "01 - " from a previous run.
        result = build_dest(
            filepath="/src/01 - Introduction.mp3",
            metadata=_meta(author="A", book="B", track="1"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "01 - Introduction.mp3"

    def test_filename_stem_fallback_strips_double_stacked_prefix(self, tmp_path):
        """A filename like '01 - 01 - Introduction' should heal to one prefix (#10)."""
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/01 - 01 - Introduction.mp3",
            metadata=_meta(author="A", book="B", track="1"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        # All stacked leading "NN - " layers are stripped, then the
        # canonical "01 - " is prepended exactly once.
        assert os.path.basename(result.dest_file) == "01 - Introduction.mp3"

    def test_filename_stem_fallback_strips_triple_stacked_prefix(self, tmp_path):
        """Three stacked prefixes (from three bad runs) must also heal (#10)."""
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/01 - 01 - 01 - Introduction.mp3",
            metadata=_meta(author="A", book="B", track="1"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "01 - Introduction.mp3"

    def test_filename_stem_fallback_strips_multidisc_prefix(self, tmp_path):
        """DNN-TNN - prefixes must also be stripped from the stem fallback (#10)."""
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/D02-T03 - Chapter Three.mp3",
            metadata=_meta(author="A", book="B", track="3", disc="2"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "D02-T03 - Chapter Three.mp3"

    def test_title_tag_overrides_stem_stripping(self, tmp_path):
        """When a title tag exists, the stem-stripping logic is not used at all."""
        dest = str(tmp_path)
        result = build_dest(
            filepath="/src/01 - bogus.mp3",
            metadata=_meta(author="A", book="B", title="Real Title", track="1"),
            infer_path=("", ""),
            infer_file=("", ""),
            dest_dir=dest,
        )
        assert os.path.basename(result.dest_file) == "01 - Real Title.mp3"
