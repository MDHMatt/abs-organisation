"""Path sanitisation and destination building for audiobook organiser."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from absorg.constants import (
    PATH_COMPONENT_MAX_LENGTH,
    SANITISE_MAP,
    UNKNOWN_AUTHOR,
    UNKNOWN_BOOK,
)
from absorg.metadata import MetadataResult

# Matches one or more leading "NN - " / "DNN-TNN - " prefixes that are
# the signature of previous absorg runs on the same file. Used to strip
# them from the filename stem when falling back to it as the title, so
# re-running over an already-organised tree is idempotent instead of
# stacking another prefix on top. The ``+`` at the outer level is
# load-bearing: it heals multi-layered damage where a file has already
# been through two or more bad runs (e.g. ``01 - 01 - Introduction``).
_TRACK_PREFIX_RE = re.compile(r"^(?:(?:D\d{2}-T\d{2}|\d{2})\s*-\s*)+")


def sanitise(name: str) -> str:
    """Make a string safe for filesystem paths using Unicode lookalike replacements.

    Each path component must be sanitised independently — never sanitise a full path.
    """
    s = name.translate(SANITISE_MAP)
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    # Strip only the first leading dot (not all of them).
    if s.startswith("."):
        s = s[1:]
    return s[:PATH_COMPONENT_MAX_LENGTH]


def parse_int(s: str) -> str:
    """Extract the leading integer from strings like '3', '03', '3/12'.

    Returns the matched digit string, or empty string if none found.
    """
    if not s:
        return ""
    m = re.match(r"^(\d+)", s)
    return m.group(1) if m else ""


@dataclass
class DestResult:
    """Result of building a canonical destination path."""

    dest_dir: str      # Directory portion (no trailing separator)
    dest_file: str     # Full destination path including filename
    no_meta: bool      # True if author OR book came from inference/fallback


def build_dest(
    filepath: str,
    metadata: MetadataResult,
    infer_path: tuple[str, str],
    infer_file: tuple[str, str],
    dest_dir: str,
) -> DestResult:
    """Build the canonical destination path for an audio file.

    Parameters
    ----------
    filepath:
        Original path to the audio file.
    metadata:
        Tag-based metadata extracted from the file.
    infer_path:
        ``(author, book)`` inferred from the directory structure.
    infer_file:
        ``(author, book)`` inferred from the filename pattern.
    dest_dir:
        Library root directory to organise into.
    """
    # Step 1: Priority fill — tags > path inference > filename inference > fallback
    author = metadata.author or infer_path[0] or infer_file[0] or ""
    book = metadata.book or infer_path[1] or infer_file[1] or ""
    no_meta = not metadata.author or not metadata.book

    # Step 2: Sanitise each component independently
    sa = sanitise(author or UNKNOWN_AUTHOR)
    sb = sanitise(book or UNKNOWN_BOOK)

    # Step 3: Build destination directory
    series = metadata.series or ""
    series_index = parse_int(metadata.series_index or "")

    if series and series_index:
        full_dir = os.path.join(
            dest_dir,
            sa,
            sanitise(series),
            f"{int(series_index):02d} - {sb}",
        )
    elif series:
        full_dir = os.path.join(dest_dir, sa, sanitise(series), sb)
    else:
        full_dir = os.path.join(dest_dir, sa, sb)

    # Step 4: Build destination filename
    filename = os.path.basename(filepath)
    ext_lower = os.path.splitext(filename)[1].lstrip(".").lower()

    if ext_lower == "m4b":
        dest_filename = f"{sb}.m4b"
    else:
        disc = parse_int(metadata.disc or "")
        track = parse_int(metadata.track or "")

        if disc and int(disc) > 1:
            prefix = f"D{int(disc):02d}-T{int(track or '0'):02d}"
        elif track:
            prefix = f"{int(track):02d}"
        else:
            prefix = ""

        if metadata.title:
            st = sanitise(metadata.title)
        else:
            # Fall back to the filename stem. Strip a leading "NN - " or
            # "DNN-TNN - " that is the signature of a previous absorg run,
            # so re-running over an already-organised tree is idempotent
            # instead of stacking another prefix on top (issue #10).
            stem = os.path.splitext(filename)[0]
            stem = _TRACK_PREFIX_RE.sub("", stem)
            st = sanitise(stem)

        dest_filename = f"{prefix} - {st}.{ext_lower}" if prefix else f"{st}.{ext_lower}"

    # Step 5: Return
    return DestResult(
        dest_dir=full_dir,
        dest_file=os.path.join(full_dir, dest_filename),
        no_meta=no_meta,
    )
