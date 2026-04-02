"""Tests for the sanitise() and parse_int() functions."""

from absorg.pathbuilder import parse_int, sanitise


class TestSanitise:
    def test_slash_replaced(self):
        assert sanitise("Author/Book") == "Author\u2215Book"

    def test_backslash_replaced(self):
        assert sanitise("Author\\Book") == "Author\u2215Book"

    def test_colon_replaced(self):
        assert sanitise("Title: Subtitle") == "Title\u2236 Subtitle"

    def test_asterisk_replaced(self):
        assert sanitise("Best*Book") == "Best\u2217Book"

    def test_question_mark_removed(self):
        assert sanitise("What?") == "What"

    def test_double_quote_removed(self):
        assert sanitise('Say "Hello"') == "Say Hello"

    def test_less_than_replaced(self):
        assert sanitise("A<B") == "A\u2039B"

    def test_greater_than_replaced(self):
        assert sanitise("A>B") == "A\u203aB"

    def test_pipe_replaced(self):
        assert sanitise("A|B") == "A\u2502B"

    def test_tab_replaced_with_space(self):
        assert sanitise("A\tB") == "A B"

    def test_whitespace_collapsed(self):
        assert sanitise("A    B") == "A B"

    def test_leading_trailing_whitespace_stripped(self):
        assert sanitise("  Hello  ") == "Hello"

    def test_first_leading_dot_stripped(self):
        assert sanitise(".hidden") == "hidden"

    def test_only_first_dot_stripped(self):
        assert sanitise("..hidden") == ".hidden"

    def test_truncated_to_180(self):
        long = "A" * 200
        assert len(sanitise(long)) == 180

    def test_clean_string_passthrough(self):
        assert sanitise("Normal Title") == "Normal Title"

    def test_empty_string(self):
        assert sanitise("") == ""

    def test_multiple_replacements(self):
        assert sanitise('A/B:C*D?E"F') == "A\u2215B\u2236C\u2217DEF"


class TestParseInt:
    def test_simple_digit(self):
        assert parse_int("3") == "3"

    def test_zero_padded(self):
        assert parse_int("03") == "03"

    def test_with_total(self):
        assert parse_int("3/12") == "3"

    def test_empty_string(self):
        assert parse_int("") == ""

    def test_no_digits(self):
        assert parse_int("abc") == ""

    def test_leading_digits_then_text(self):
        assert parse_int("42abc") == "42"
