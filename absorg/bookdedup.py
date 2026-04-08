"""Book-level deduplication for the audiobook organiser.

When enabled via ``--book-dedup``, this module adds a two-pass architecture:

Pass 1 (Inventory):
    Scan all files, extract metadata + audio info, group files into editions
    by their source directory and per-file normalised ``(author, book)``
    sub-key (so a "series container" directory produces one edition per
    book), then group editions across directories by normalised
    ``(author, book)`` key.

Pass 2 (Resolution):
    For each book group with 2+ editions, score them and keep the best.
    Lower-scoring editions are marked for quarantine.
"""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from absorg.audioinfo import AudioInfo, extract_audio_info, format_duration
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


def _extract_file_info(filepath: str) -> tuple[str, MetadataResult, AudioInfo]:
    """Extract metadata and audio info for a single file (thread-safe)."""
    meta = resolve_metadata(filepath)
    ai = extract_audio_info(filepath)
    return (os.path.abspath(filepath), meta, ai)


def build_book_inventory(
    files: list[str],
    source_dir: str,
    max_workers: int = 4,
) -> tuple[dict[tuple[str, str], BookGroup], dict[str, tuple[MetadataResult, AudioInfo]]]:
    """Scan all files, build editions grouped by normalised (author, book) key.

    Returns
    -------
    groups : dict mapping norm_key → BookGroup (only groups with 2+ editions)
    metadata_cache : dict mapping abs_filepath → (MetadataResult, AudioInfo)
    """
    source_dir = os.path.normpath(os.path.abspath(source_dir))
    metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]] = {}

    # Phase 1a: Extract metadata + audio info for all files in parallel.
    total = len(files)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_extract_file_info, f): f for f in files}
        for completed, future in enumerate(as_completed(futures), start=1):
            if total >= 100 and (completed % 500 == 0 or completed == total):
                print(f"\r  Scanned {completed}/{total} files...", end="", flush=True, file=sys.stderr)
            try:
                abs_path, meta, ai = future.result()
            except Exception:
                filepath = futures[future]
                abs_path = os.path.abspath(filepath)
                meta, ai = MetadataResult(), AudioInfo()
            metadata_cache[abs_path] = (meta, ai)
    if total >= 100:
        print(file=sys.stderr)

    # Phase 1b: Group files by their parent directory.
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

    # Step 2: Build editions from directory groups using cached metadata.
    # Within each directory, sub-group files by their per-file normalised
    # (author, book) key so that "series container" directories (holding
    # multiple distinct books) produce one edition per book rather than being
    # mis-matched as a single book against standalone copies elsewhere.
    editions: list[BookEdition] = []
    for dir_path, dir_file_list in dir_files.items():
        sub_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
        sub_first_meta: dict[tuple[str, str], tuple[str, str, str]] = {}

        for fpath in dir_file_list:
            meta, _ai = metadata_cache[fpath]
            sub_key = (
                normalise_author(meta.author or ""),
                normalise_book(meta.book or ""),
            )
            sub_groups[sub_key].append(fpath)
            if sub_key not in sub_first_meta:
                sub_first_meta[sub_key] = (meta.author or "", meta.book or "", meta.year or "")

        for sub_key, sub_files in sub_groups.items():
            first_author, first_book, first_year = sub_first_meta[sub_key]
            edition = BookEdition(
                source_dir=dir_path,
                files=sub_files,
                author=first_author,
                book=first_book,
                year=first_year,
            )

            total_bitrate = 0
            total_duration = 0.0
            total_size = 0
            ext_counter: Counter[str] = Counter()
            has_m4b = False

            for fpath in sub_files:
                _meta, ai = metadata_cache[fpath]
                ext = os.path.splitext(fpath)[1].lstrip(".").lower()
                ext_counter[ext] += 1
                if ext == "m4b":
                    has_m4b = True
                total_bitrate += ai.bitrate
                total_duration += ai.duration
                total_size += os.path.getsize(fpath) if os.path.exists(fpath) else 0

            # Infer author/book from path if tags were empty
            if not edition.author or not edition.book:
                sample = sub_files[0]
                ip = infer_from_path(sample, source_dir)
                ifn = infer_from_filename(os.path.basename(sample))
                if not edition.author:
                    edition.author = ip[0] or ifn[0] or ""
                if not edition.book:
                    edition.book = ip[1] or ifn[1] or ""

            edition.format = "m4b" if has_m4b else (ext_counter.most_common(1)[0][0] if ext_counter else "")
            edition.total_duration = total_duration
            edition.avg_bitrate = total_bitrate // len(sub_files) if sub_files else 0
            edition.file_count = len(sub_files)
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
    quarantine_files : set of normalised absolute file paths to quarantine.
        Populated from ``loser.files`` and normalised via
        ``os.path.normpath(os.path.abspath(...))`` so callers can look up files
        by computing the same key from the iterated source file path.
    decisions : list of BookDedupDecision records for logging
    """
    quarantine_files: set[str] = set()
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
            for fpath in loser.files:
                quarantine_files.add(os.path.normpath(os.path.abspath(fpath)))

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

    return quarantine_files, decisions
