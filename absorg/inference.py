from __future__ import annotations

import os


def infer_from_path(filepath: str, source_dir: str) -> tuple[str, str]:
    """Derive (author, book) from the directory structure relative to source_dir.

    Returns a tuple of (author, book) where either may be empty string
    if the information cannot be determined.
    """
    filepath = os.path.normpath(filepath)
    source_dir = os.path.normpath(source_dir)

    rel = os.path.relpath(filepath, source_dir)
    dir_portion = os.path.dirname(rel)

    if not dir_portion or dir_portion == ".":
        return ("", "")

    components = dir_portion.split(os.sep)

    if len(components) >= 2:
        return (components[0], components[1])

    # Single directory level
    dirname = components[0]
    if " - " in dirname:
        author, _, book = dirname.partition(" - ")
        return (author, book)

    return ("", dirname)


def infer_from_filename(filename: str) -> tuple[str, str]:
    """Last-resort inference of (author, book) from the filename itself.

    Expects a basename (not a full path). Returns a tuple of (author, book)
    where either may be empty string.
    """
    basename = os.path.splitext(filename)[0]

    if " - " not in basename:
        return ("", "")

    left, _, right = basename.partition(" - ")
    left = left.strip()
    right = right.strip()

    if left.isdigit():
        return ("", right)

    return (left, right)
