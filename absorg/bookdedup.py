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
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from absorg.audioinfo import AudioInfo, extract_audio_info, format_duration
from absorg.constants import FORMAT_PREFERENCE
from absorg.inference import infer_from_filename, infer_from_path
from absorg.metadata import MetadataResult, resolve_metadata
from absorg.normalise import normalise_author, normalise_book

# Path segments that indicate a "placeholder" / dumping-ground directory
# rather than a properly-organised Author/Book folder. When a book-dedup
# tiebreak falls back to path structure, editions under these segments
# are penalised so correctly-organised folders win over scratch dirs.
# Compared lowercase against individual path segments.
_PLACEHOLDER_SEGMENTS: frozenset[str] = frozenset({
    "_unknown author",
    "_unknown",
    "unknown",
    "unknown author",
    "audiobooks",
    "classics & general fiction",
})


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


@dataclass
class IntraEditionDedupDecision:
    """Record of an intra-edition dedup decision for logging."""

    book_display: str
    source_dir: str
    kept: str                  # file path kept
    quarantined: list[str]     # file paths quarantined
    reason: str


def score_edition(edition: BookEdition) -> tuple[int, int, int, float]:
    """Return a comparable score tuple (higher = preferred).

    Priority order: format (M4B > MP3) → year → bitrate → duration.
    """
    format_score = FORMAT_PREFERENCE.get(edition.format, 0)
    year_score = int(edition.year) if edition.year.isdigit() else 0
    return (format_score, year_score, edition.avg_bitrate, edition.total_duration)


def _tiebreak_key(edition: BookEdition, source_dir: str) -> tuple[int, int, int, int, str]:
    """Ascending-sort key to break ties between equally-scored editions.

    This key is designed for an **ascending** sort (``sorted(..., reverse=False)``)
    where **lower = better**, so it slots cleanly into a two-phase stable
    sort: phase 1 orders by this tiebreak (ascending), phase 2 stable-sorts
    by ``score_edition`` (descending). Ties in score preserve the phase-1
    ordering.

    Components, in priority order (all "lower is better"):

    1. **Root-loose penalty.** ``0`` if the edition lives in a proper
       sub-directory under *source_dir*, ``1`` if it is a loose file
       directly at the source root. Loose files at the root always lose
       ties to organised folders.
    2. **Placeholder segment count.** Number of path segments matching a
       known dumping-ground name (``_Unknown Author``, ``Unknown``,
       ``Audiobooks``, etc.). Zero is best.
    3. **Author-match penalty.** ``0`` if any path segment normalises to
       the edition's tagged author name, ``1`` otherwise. Rewards folders
       whose filesystem path already agrees with the audio tags.
    4. **Depth penalty** (negated). ``-depth`` where depth is the number
       of relative path segments under *source_dir*. Deeper = more
       specifically organised = preferred, and negation flips it to
       "lower is better".
    5. **Alphabetical source_dir** as a final deterministic fallback.
       Alphabetically earlier wins, which means correctly-spelled folders
       beat typos (``Tchaikovsky`` < ``Tchikovski`` → Tchaikovsky wins).

    See fixes.md Issue 12 for the full motivation and the three classes
    of bad pick this replaces.
    """
    path = edition.source_dir
    abs_path = os.path.normpath(os.path.abspath(path))
    abs_source = os.path.normpath(os.path.abspath(source_dir))

    # For loose files at the source root, inventory stores the full file
    # path as source_dir (see build_book_inventory ~line 134), so the
    # "directory" is actually a file whose parent is source_dir itself.
    if os.path.isfile(abs_path):
        parent = os.path.dirname(abs_path)
        is_root_loose = 1 if os.path.normpath(parent) == abs_source else 0
        rel = os.path.relpath(abs_path, abs_source) if abs_path.startswith(abs_source) else abs_path
    else:
        is_root_loose = 0
        rel = os.path.relpath(abs_path, abs_source) if abs_path.startswith(abs_source) else abs_path

    segments = [s for s in rel.split(os.sep) if s and s != "."]

    placeholder_hits = sum(1 for s in segments if s.lower() in _PLACEHOLDER_SEGMENTS)

    norm_author = normalise_author(edition.author or "")
    author_mismatch = 1
    if norm_author:
        for s in segments:
            if normalise_author(s) == norm_author:
                author_mismatch = 0
                break

    depth = len(segments)

    return (is_root_loose, placeholder_hits, author_mismatch, -depth, path)


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
    groups : dict mapping norm_key → BookGroup (all groups, including single-edition)
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

    return dict(all_groups), metadata_cache


def resolve_book_duplicates(
    groups: dict[tuple[str, str], BookGroup],
    source_dir: str = "",
) -> tuple[set[str], list[BookDedupDecision]]:
    """For each group with 2+ editions, keep the best and quarantine the rest.

    Parameters
    ----------
    groups:
        Book groups produced by :func:`build_book_inventory`.
    source_dir:
        The library source root. Used by the structural tiebreaker to
        compute path depth and detect root-level loose files. May be left
        empty in tests that construct ``BookEdition`` objects directly; in
        that case the tiebreak falls back to alphabetical ``source_dir``.

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
        # Two-phase stable sort so we can mix sort directions:
        #   Phase 1 — ascending by _tiebreak_key (lower = better)
        #   Phase 2 — descending by score_edition (higher = better), stable
        # Stability guarantees that editions with equal score_edition
        # values retain the phase-1 tiebreak order. See fixes.md Issue 12
        # for why this replaces the old single-sort reverse=True key.
        tb_sorted = sorted(group.editions, key=lambda e: _tiebreak_key(e, source_dir))
        ranked = sorted(tb_sorted, key=score_edition, reverse=True)
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
                # Suppress the reason when the display would round to the
                # same kbps value on both sides (fixes.md Issue 13). The
                # score comparison is on true bps, so sub-kbps wins are
                # valid but would render as "62kbps vs 62kbps" which is
                # user-hostile log noise. With the structural tiebreak in
                # place, sub-kbps ties are already broken by path quality
                # anyway, so skipping the reason here loses no information.
                kept_kbps = kept.avg_bitrate // 1000
                loser_kbps = loser.avg_bitrate // 1000
                if kept_kbps != loser_kbps:
                    reasons.append(f"higher bitrate ({kept_kbps}kbps vs {loser_kbps}kbps)")

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


# ---------------------------------------------------------------------------
# Intra-edition dedup (Issue 11)
# ---------------------------------------------------------------------------

# Matches a numeric suffix like ".2" in "Book.2.m4b" — the lookahead ensures
# there is still a real file extension after the suffix.
_NUMERIC_SUFFIX_RE = re.compile(r"\.\d+(?=\.[^.]+$)")


def _recalculate_edition_stats(
    edition: BookEdition,
    removed: set[str],
    metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]],
) -> None:
    """Recalculate edition stats after removing intra-edition duplicates."""
    kept_files = [
        f for f in edition.files
        if os.path.normpath(os.path.abspath(f)) not in removed
    ]
    if not kept_files:
        return  # safety: never empty an edition

    edition.files = kept_files
    total_bitrate = 0
    total_duration = 0.0
    total_size = 0
    for fpath in kept_files:
        entry = metadata_cache.get(fpath)
        ai = entry[1] if entry else AudioInfo()
        total_bitrate += ai.bitrate
        total_duration += ai.duration
        total_size += os.path.getsize(fpath) if os.path.exists(fpath) else 0

    edition.file_count = len(kept_files)
    edition.total_duration = total_duration
    edition.avg_bitrate = total_bitrate // len(kept_files) if kept_files else 0
    edition.total_size = total_size


def resolve_intra_edition_duplicates(
    all_groups: dict[tuple[str, str], BookGroup],
    metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]],
    *,
    duration_tolerance: float = 1.0,
) -> tuple[set[str], list[IntraEditionDedupDecision]]:
    """Detect and quarantine duplicate files within a single edition.

    Files within the same edition that share the same extension and have
    durations within *duration_tolerance* seconds are treated as identical
    audio copies (differing only in container metadata like moov atom
    padding).  A cluster is only processed when at least one file carries
    a ``.N`` numeric suffix — this prevents false positives on legitimate
    multi-chapter editions where several files happen to share a duration.

    Returns
    -------
    quarantine_files : set of normalised absolute file paths to quarantine.
    decisions : list of IntraEditionDedupDecision records for logging.
    """
    quarantine_files: set[str] = set()
    decisions: list[IntraEditionDedupDecision] = []

    for group in all_groups.values():
        for edition in group.editions:
            if edition.file_count <= 1:
                continue

            # Group files by extension
            by_ext: dict[str, list[str]] = defaultdict(list)
            for fpath in edition.files:
                ext = os.path.splitext(fpath)[1].lstrip(".").lower()
                by_ext[ext].append(fpath)

            for _ext, ext_files in by_ext.items():
                if len(ext_files) <= 1:
                    continue

                # Collect (path, duration) pairs, excluding zero-duration files
                file_durations: list[tuple[str, float]] = []
                for fpath in ext_files:
                    entry = metadata_cache.get(fpath)
                    dur = entry[1].duration if entry else 0.0
                    if dur > 0:
                        file_durations.append((fpath, dur))

                if len(file_durations) <= 1:
                    continue

                # Sort by duration for clustering
                file_durations.sort(key=lambda x: x[1])

                # Cluster: files within tolerance of the cluster's first element
                clusters: list[list[str]] = []
                cluster_start_dur = file_durations[0][1]
                current: list[str] = [file_durations[0][0]]

                for fpath, dur in file_durations[1:]:
                    if dur - cluster_start_dur <= duration_tolerance:
                        current.append(fpath)
                    else:
                        if len(current) > 1:
                            clusters.append(current)
                        current = [fpath]
                        cluster_start_dur = dur

                if len(current) > 1:
                    clusters.append(current)

                # Process each cluster
                for cluster in clusters:
                    # Safety: require at least one .N suffix file as evidence
                    has_suffix = any(
                        _NUMERIC_SUFFIX_RE.search(os.path.basename(f))
                        for f in cluster
                    )
                    if not has_suffix:
                        continue

                    # Pick keeper: prefer no .N suffix, then shortest name, then alphabetical
                    def _sort_key(fpath: str) -> tuple[int, int, str]:
                        bn = os.path.basename(fpath)
                        sfx = 1 if _NUMERIC_SUFFIX_RE.search(bn) else 0
                        return (sfx, len(bn), bn)

                    cluster.sort(key=_sort_key)
                    kept = cluster[0]
                    dupes = cluster[1:]

                    for dupe in dupes:
                        quarantine_files.add(os.path.normpath(os.path.abspath(dupe)))

                    book_display = f'"{edition.book}"' if edition.book else "(unknown book)"
                    if edition.author:
                        book_display += f" by {edition.author}"

                    decisions.append(IntraEditionDedupDecision(
                        book_display=book_display,
                        source_dir=edition.source_dir,
                        kept=kept,
                        quarantined=dupes,
                        reason=f"same duration, same format, {len(dupes)} duplicate cop{'y' if len(dupes) == 1 else 'ies'}",
                    ))

            # Fix edition stats after removing duplicates
            if quarantine_files:
                _recalculate_edition_stats(edition, quarantine_files, metadata_cache)

    return quarantine_files, decisions
