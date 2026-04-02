"""Tests for path and filename inference."""

import os

from absorg.inference import infer_from_filename, infer_from_path


class TestInferFromPath:
    def test_two_levels(self, tmp_path):
        source = str(tmp_path / "source")
        filepath = os.path.join(source, "Author Name", "Book Title", "ch01.mp3")
        assert infer_from_path(filepath, source) == ("Author Name", "Book Title")

    def test_single_level_with_separator(self, tmp_path):
        source = str(tmp_path / "source")
        filepath = os.path.join(source, "Author - Book", "file.mp3")
        assert infer_from_path(filepath, source) == ("Author", "Book")

    def test_single_level_no_separator(self, tmp_path):
        source = str(tmp_path / "source")
        filepath = os.path.join(source, "BookTitle", "file.mp3")
        assert infer_from_path(filepath, source) == ("", "BookTitle")

    def test_file_directly_in_source(self, tmp_path):
        source = str(tmp_path / "source")
        filepath = os.path.join(source, "file.mp3")
        assert infer_from_path(filepath, source) == ("", "")

    def test_three_levels_uses_first_two(self, tmp_path):
        source = str(tmp_path / "source")
        filepath = os.path.join(source, "Author", "Series", "Book", "ch01.mp3")
        assert infer_from_path(filepath, source) == ("Author", "Series")


class TestInferFromFilename:
    def test_author_and_book(self):
        assert infer_from_filename("Author Name - Book Title.mp3") == ("Author Name", "Book Title")

    def test_numeric_prefix(self):
        assert infer_from_filename("01 - Chapter Title.mp3") == ("", "Chapter Title")

    def test_no_separator(self):
        assert infer_from_filename("somefile.mp3") == ("", "")

    def test_strips_whitespace(self):
        assert infer_from_filename("  Author  -  Book  .mp3") == ("Author", "Book")

    def test_first_separator_only(self):
        assert infer_from_filename("Author - Book - Subtitle.mp3") == ("Author", "Book - Subtitle")
