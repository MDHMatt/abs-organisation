"""Tests for author and book name normalisation."""


from absorg.normalise import normalise_author, normalise_book


class TestNormaliseAuthor:
    def test_semicolon_vs_comma(self):
        assert normalise_author("Neil Gaiman, Terry Pratchett") == \
               normalise_author("Neil Gaiman; Terry Pratchett")

    def test_name_order(self):
        assert normalise_author("Neil Gaiman, Terry Pratchett") == \
               normalise_author("Terry Pratchett, Neil Gaiman")

    def test_accent(self):
        assert normalise_author("Jo Nesbø") == normalise_author("Jo Nesbo")

    def test_case(self):
        assert normalise_author("Stephen King") == normalise_author("stephen king")

    def test_qualifier_and_order(self):
        assert normalise_author("Arthur Conan Doyle, Stephen Fry - introductions") == \
               normalise_author("Stephen Fry, Arthur Conan Doyle")

    def test_semicolon_multi_author(self):
        assert normalise_author("Martina Cole, Jacqui Rose") == \
               normalise_author("Martina Cole; Jacqui Rose")

    def test_parenthetical_qualifier(self):
        assert normalise_author("J.K. Rowling (author)") == \
               normalise_author("J.K. Rowling")

    def test_translator_qualifier(self):
        assert normalise_author("Andrzej Sapkowski, David French - translator") == \
               normalise_author("David French, Andrzej Sapkowski")

    def test_empty(self):
        assert normalise_author("") == ""

    def test_single_name(self):
        result = normalise_author("Stephen King")
        assert result == "stephen king"

    def test_whitespace_handling(self):
        assert normalise_author("  Stephen   King  ") == normalise_author("Stephen King")

    def test_foreword_qualifier(self):
        assert normalise_author("Lucy Beaumont, Jon Richardson - introduction") == \
               normalise_author("Jon Richardson, Lucy Beaumont")

    def test_emdash_qualifier(self):
        assert normalise_author("Author — narrator") == normalise_author("Author")

    def test_endash_qualifier(self):
        assert normalise_author("Author \u2013 introductions") == normalise_author("Author")

    def test_qualifier_mid_string_semicolon(self):
        """Role qualifier before semicolon must not eat subsequent authors."""
        assert normalise_author("Stephen Fry - introductions; Arthur Conan Doyle") == \
               normalise_author("Arthur Conan Doyle, Stephen Fry")

    def test_preserves_distinct_authors(self):
        """Different authors should not normalise to the same key."""
        assert normalise_author("Stephen King") != normalise_author("Dean Koontz")

    def test_german_eszett(self):
        assert normalise_author("Straße Author") == normalise_author("Strasse Author")


class TestNormaliseBook:
    def test_audible_id(self):
        assert normalise_book("Wool [B0071KBMAO]") == normalise_book("Wool")

    def test_numeric_id(self):
        assert normalise_book("Catching Fire [1338589016]") == normalise_book("Catching Fire")

    def test_subtitle_colon(self):
        assert normalise_book("Good Omens: The Nice and Accurate Prophecies") == \
               normalise_book("Good Omens")

    def test_subtitle_dash(self):
        assert normalise_book("Dune - The First Novel") == normalise_book("Dune")

    def test_short_title_preserved(self):
        """Short titles like 'It' should not be stripped by article removal."""
        result = normalise_book("It")
        assert result == "it"

    def test_leading_article_the(self):
        assert normalise_book("The Martian") == normalise_book("Martian")

    def test_leading_article_a(self):
        assert normalise_book("A Perfect Spy") == normalise_book("Perfect Spy")

    def test_case(self):
        assert normalise_book("good omens") == normalise_book("Good Omens")

    def test_accent(self):
        assert normalise_book("Café Society") == normalise_book("Cafe Society")

    def test_empty(self):
        assert normalise_book("") == ""

    def test_subtitle_not_stripped_if_too_short(self):
        """Don't strip subtitle if it would leave a result shorter than 3 chars."""
        result = normalise_book("It: A Novel")
        # "It" is only 2 chars, so subtitle should NOT be stripped
        assert "novel" in result

    def test_whitespace(self):
        assert normalise_book("  Good   Omens  ") == normalise_book("Good Omens")

    def test_preserves_distinct_books(self):
        assert normalise_book("Dune") != normalise_book("Foundation")

    def test_preserves_series_numbers(self):
        """Different series numbers should normalize to different keys."""
        assert normalise_book("Alan Partridge - Series 1") != \
               normalise_book("Alan Partridge - Series 2")

    def test_preserves_book_ranges(self):
        """Different book ranges should normalize to different keys."""
        assert normalise_book("Skulduggery Pleasant: Books 1-3") != \
               normalise_book("Skulduggery Pleasant: Books 4-6")
        assert normalise_book("Skulduggery Pleasant: Books 4-6") != \
               normalise_book("Skulduggery Pleasant: Books 7-9")

    def test_preserves_act_numbers(self):
        """Different acts should normalize to different keys."""
        assert normalise_book("The Sandman - Act I") != \
               normalise_book("The Sandman - Act II")

    def test_preserves_part_numbers(self):
        """Different parts should normalize to different keys."""
        assert normalise_book("Hitchhiker's Guide - Part 1") != \
               normalise_book("Hitchhiker's Guide - Part 2")

    def test_preserves_volume_numbers(self):
        """Different volumes should normalize to different keys."""
        assert normalise_book("Aurora Saga - Volume 1") != \
               normalise_book("Aurora Saga - Volume 2")

    def test_base_title_equivalent_with_series_marker(self):
        """The base title with and without series marker should still normalize the same
        when the series marker is conceptually the same edition."""
        # "Alan Partridge Series 1" and "Alan Partridge - Series 1" should be the same
        assert normalise_book("Alan Partridge Series 1") == \
               normalise_book("Alan Partridge - Series 1")

    def test_strips_actual_subtitle_before_series(self):
        """Actual subtitles should still be stripped; series markers preserved."""
        # A real subtitle before the series info
        assert normalise_book("Good Omens: The Nice and Accurate Prophecies Series 1") == \
               normalise_book("Good Omens Series 1")

    def test_year_prefix_not_conflated(self):
        """Year-prefixed books with different titles must NOT conflate."""
        assert normalise_book("1982 - The Gunslinger") != \
               normalise_book("1982 - Different Seasons")

    def test_year_prefix_same_book_matches(self):
        """Same year-prefixed book with parenthetical should still match."""
        # Real data: "(DT1 - revised edition - read by George Guidall)"
        # Parenthetical is stripped first, leaving "1982 - The Gunslinger"
        assert normalise_book("1982 - The Gunslinger (DT1 - revised edition)") == \
               normalise_book("1982 - The Gunslinger")

    def test_unabridged_stripped(self):
        """'(Unabridged)' annotation should be stripped for grouping."""
        assert normalise_book("Unruly (Unabridged)") == normalise_book("Unruly")

    def test_parenthetical_narrator_stripped(self):
        """Parenthetical narrator/edition info should be stripped."""
        assert normalise_book("Dune (read by someone)") == normalise_book("Dune")

    def test_parenthetical_with_subtitle(self):
        """Parenthetical stripped before subtitle handling."""
        assert normalise_book("Fairy Tale (Unabridged)") == \
               normalise_book("Fairy Tale")
