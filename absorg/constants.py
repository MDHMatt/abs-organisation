"""Shared constants for absorg."""

AUDIO_EXTENSIONS = frozenset({
    "mp3", "m4a", "m4b", "m4p", "flac", "ogg", "opus",
    "aac", "wav", "wma", "mp4", "aiff", "ape",
})

UNKNOWN_AUTHOR = "_Unknown Author"
UNKNOWN_BOOK = "_Unknown Book"

PATH_COMPONENT_MAX_LENGTH = 180

# Character replacements for filesystem-safe paths.
# Uses visually similar Unicode lookalikes so folder names stay human-readable.
# Source of truth: the original absorg.sh sanitise() function.
SANITISE_MAP: dict[int, str | None] = {
    ord("/"): "\u2215",   # ∕  DIVISION SLASH
    ord("\\"): "\u2215",  # ∕  DIVISION SLASH (same as /)
    ord(":"): "\u2236",   # ∶  RATIO
    ord("*"): "\u2217",   # ∗  ASTERISK OPERATOR
    ord("?"): None,       #    removed
    ord('"'): None,       #    removed
    ord("<"): "\u2039",   # ‹  SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    ord(">"): "\u203a",   # ›  SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    ord("|"): "\u2502",   # │  BOX DRAWINGS LIGHT VERTICAL
    ord("\t"): " ",       #    tab → space
}

# Tag priority chains for metadata resolution.
# For each field the first non-empty tag wins.
# Keys are the normalised names used in the flat tags dict produced by load_tags().
METADATA_TAG_CHAINS: dict[str, list[str]] = {
    "author": [
        "album_artist", "albumartist", "album artist", "tpe2",
        "artist", "tpe1",
        "composer", "tcom",
        "narrator", "txxx:narrator", "txxx:narrated_by",
        "sort_artist", "artistsort", "tso2",
    ],
    "book": [
        "album", "talb",
        "work", "\u00a9wrk", "txxx:work",
        "tvshow",
    ],
    "title": ["title", "tit2", "\u00a9nam"],
    "track": ["track", "trck", "trkn"],
    "disc": ["disc", "tpos", "disk", "disknumber"],
    "series": [
        "txxx:series", "series",
        "txxx:series_name", "series_name", "txxx:seriesname",
        "grouping", "tit1",
        "work", "\u00a9wrk",
    ],
    "series_index": [
        "txxx:series-part", "txxx:series_part", "txxx:seriespart",
        "series-part", "series_part", "seriespart",
        "movementnumber", "\u00a9mvi", "movement",
    ],
    "narrator": [
        "narrator", "txxx:narrator", "txxx:narrated_by", "txxx:narrated_by",
        "composer", "tcom",
    ],
    "year": ["date", "tdrc", "year", "\u00a9day", "tyer"],
    "subtitle": ["subtitle", "txxx:subtitle", "tit3"],
    "genre": ["genre", "tcon", "\u00a9gen"],
}
