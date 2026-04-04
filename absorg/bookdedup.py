"""Book-level deduplication for the audiobook organiser.

When enabled via ``--book-dedup``, this module adds a two-pass architecture:

Pass 1 (Inventory):
    Scan all files, extract metadata + audio info, group files into editions
    by their source directory, then group editions by normalised
    ``(author, book)`` key.

Pass 2 (Resolution):
    For each book group with 2+ editions, score them and keep the best.
    Lower-scoring editions are marked for quarantine.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from absorg.audioinfo import AudioInfo, extract_audio_info, format_duration, format_quality
from absorg.constants import FORMAT_PREFERENCE
from absorg.inference import infer_from_filename, infer_from_path
from absorg.metadata import MetadataResult, resolve_metadata
from absorg.normalise import normalise_author, normalise_book


@dataclass
class BookEdition:
    """One edition/version of a book (all audio files in one source directory)."""

    source_dir: str
    files: list[str] = field(default_factory=list)
    author: str = ""
    book: str = ""
    format: str = ""           # primary format: "m4b", "mp3", etc.
    year: str = ""
    total_duration: float = 0.0
    avg_bitrate: int = 0
    file_count: int = 0
    total_size: int = 0        # bytes


@dataclass
class BookGroup:
    """A group of editions that represent the same logical book."""

    norm_key: tuple[str, str]  # (normalised_author, normalised_book)
    editions: list[BookEdition] = field(default_factory=list)


@dataclass
class BookDedupDecision:
    """Record of a book-level dedup decision for logging."""

    book_display: str          # e.g. '"Good Omens" by Neil Gaiman'
    kept: BookEdition
    quarantined: list[BookEdition]
    reason: str


def score_edition(edition: BookEdition) -> tuple[int, int, int, float]:
    """Return a comparable score tuple (higher = preferred).

    Priority order: format (M4B > MP3) → year → bitrate → duration.
    """
    format_score = FORMAT_PREFERENCE.get(edition.format, 0)
    year_score = int(edition.year) if edition.year.isdigit() else 0
    return (format_score, year_score, edition.avg_bitrate, edition.total_duration)


def _edition_summary(edition: BookEdition) -> str:
    """One-line summary of an edition for log output."""
    parts = [edition.format.upper() if edition.format else "?"]
    if edition.year:
        parts.append(edition.year)
    if edition.avg_bitrate:
        parts.append(f"{edition.avg_bitrate // 1000}kbps")
    parts.append(format_duration(edition.total_duration))
    parts.append(f"{edition.file_count} file{'s' if edition.file_count != 1 else ''}")
    return ", ".join(parts)


def build_book_inventory(
    files: list[str],
    source_dir: str,
) -> tuple[dict[tuple[str, str], BookGroup], dict[str, tuple[MetadataResult, AudioInfo]]]:
    """Scan all files, build editions grouped by normalised (author, book) key.

    Returns
    -------
    groups : dict mapping norm_key → BookGroup (only groups with 2+ editions)
    metadata_cache : dict mapping abs_filepath → (MetadataResult, AudioInfo)
    """
    source_dir = os.path.normpath(os.path.abspath(source_dir))
    metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]] = {}

    # Step 1: Group files by their parent directory.
    # Root-level files each get their own unique key.
    dir_files: dict[str, list[str]] = defaultdict(list)
    for filepath in files:
        abs_path = os.path.abspath(filepath)
        parent = os.path.dirname(abs_path)
        if os.path.normpath(parent) == source_dir:
            # Loose file at source root — give it its own unique dir key
            dir_files[abs_path] = [abs_path]
        else:
            dir_files[parent].append(abs_path)

    # Step 2: Build editions from directory groups.
    editions: list[BookEdition] = []
    for dir_path, dir_file_list in dir_files.items():
        edition = BookEdition(source_dir=dir_path, files=dir_file_list)

        total_bitrate = 0
        total_duration = 0.0
        total_size = 0
        ext_counter: Counter[str] = Counter()
        has_m4b = False

        for fpath in dir_file_list:
            meta = resolve_metadata(fpath)
            ai = extract_audio_info(fpath)
            metadata_cache[fpath] = (meta, ai)

            # Collect edition metadata from the first file with non-empty values
            if not edition.author and meta.author:
                edition.author = meta.author
            if not edition.book and meta.book:
                edition.book = meta.book
            if not edition.year and meta.year:
                edition.year = meta.year

            ext = os.path.splitext(fpath)[1].lstrip(".").lower()
            ext_counter[ext] += 1
            if ext == "m4b":
                has_m4b = True

            total_bitrate += ai.bitrate
            total_duration += ai.duration
            total_size += os.path.getsize(fpath) if os.path.exists(fpath) else 0

        # Infer author/book from path if tags were empty
        if dir_file_list:
            sample = dir_file_list[0]
            ip = infer_from_path(sample, source_dir)
            ifn = infer_from_filename(os.path.basename(sample))
            if not edition.author:
                edition.author = ip[0] or ifn[0] or ""
            if not edition.book:
                edition.book = ip[1] or ifn[1] or ""

        edition.format = "m4b" if has_m4b else (ext_counter.most_common(1)[0][0] if ext_counter else "")
        edition.total_duration = total_duration
        edition.avg_bitrate = total_bitrate // len(dir_file_list) if dir_file_list else 0
        edition.file_count = len(dir_file_list)
        edition.total_size = total_size

        editions.append(edition)

    # Step 3: Group editions by normalised (author, book) key.
    all_groups: dict[tuple[str, str], BookGroup] = defaultdict(lambda: BookGroup(norm_key=("", "")))
    for edition in editions:
        key = (normalise_author(edition.author), normalise_book(edition.book))
        if not all_groups[key].norm_key[0] and not all_groups[key].norm_key[1]:
            all_groups[key] = BookGroup(norm_key=key)
        all_groups[key].editions.append(edition)

    # Only return groups with 2+ editions (these are the duplicates).
    multi_groups = {k: v for k, v in all_groups.items() if len(v.editions) >= 2}

    return multi_groups, metadata_cache


def resolve_book_duplicates(
    groups: dict[tuple[str, str], BookGroup],
) -> tuple[set[str], list[BookDedupDecision]]:
    """For each group with 2+ editions, keep the best and quarantine the rest.

    Returns
    -------
    quarantine_dirs : set of absolute directory paths whose files should be quarantined
    decisions : list of BookDedupDecision records for logging
    """
    quarantine_dirs: set[str] = set()
    decisions: list[BookDedupDecision] = []

    for _key, group in sorted(groups.items()):
        # Sort editions by score descending; ties broken by source_dir for determinism.
        ranked = sorted(
            group.editions,
            key=lambda e: (score_edition(e), e.source_dir),
            reverse=True,
        )
        kept = ranked[0]
        losers = ranked[1:]

        for loser in losers:
            quarantine_dirs.add(loser.source_dir)

        # Build reason string
        reasons: list[str] = []
        kept_score = score_edition(kept)
        for loser in losers:
            loser_score = score_edition(loser)
            if kept_score[0] > loser_score[0]:
                reasons.append(f"{kept.format.upper()} preferred over {loser.format.upper()}")
            if kept_score[1] > loser_score[1] and kept.year and loser.year:
                reasons.append(f"newer recording ({kept.year} vs {loser.year})")
            elif kept_score[1] > loser_score[1] and kept.year:
                reasons.append(f"has year metadata ({kept.year})")
            if kept_score[2] > loser_score[2]:
                reasons.append(f"higher bitrate ({kept.avg_bitrate // 1000}kbps vs {loser.avg_bitrate // 1000}kbps)")

        book_display = f'"{kept.book}"' if kept.book else "(unknown book)"
        if kept.author:
            book_display += f" by {kept.author}"

        decisions.append(BookDedupDecision(
            book_display=book_display,
            kept=kept,
            quarantined=losers,
            reason="; ".join(reasons) if reasons else "higher overall score",
        ))

    return quarantine_dirs, decisions
