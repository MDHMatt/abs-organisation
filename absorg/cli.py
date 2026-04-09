"""Command-line interface and main orchestration for absorg."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass

from absorg.audioinfo import AudioInfo, extract_audio_info, format_quality
from absorg.bookdedup import (
    BookDedupDecision,
    _edition_summary,
    build_book_inventory,
    resolve_book_duplicates,
)
from absorg.constants import AUDIO_EXTENSIONS
from absorg.cover import extract_cover
from absorg.dedup import DedupAction, DedupTracker, precompute_fingerprints, quarantine
from absorg.inference import infer_from_filename, infer_from_path
from absorg.logger import AbsorgLogger
from absorg.metadata import MetadataResult, resolve_metadata
from absorg.pathbuilder import build_dest, sanitise


@dataclass
class Counters:
    """Runtime statistics for the organise run."""

    moved: int = 0
    skipped: int = 0
    failed: int = 0
    no_meta: int = 0  # only incremented on live moves
    cover: int = 0
    dupe: int = 0
    conflict: int = 0
    book_dedup: int = 0          # files quarantined by book-level dedup
    book_dedup_groups: int = 0   # number of book groups resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="absorg",
        description="Organise audiobook files for Audiobookshelf.",
    )
    parser.add_argument(
        "--move",
        dest="dry_run",
        action="store_false",
        help="Actually move files (default is dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help=argparse.SUPPRESS,  # undocumented but accepted
    )
    parser.set_defaults(dry_run=True)

    parser.add_argument("--source", default="/audiobooks_unsorted",
                        help="Source directory to scan recursively (default: /audiobooks_unsorted).")
    parser.add_argument("--dest", default="/audiobooks",
                        help="Destination library root (default: /audiobooks).")
    parser.add_argument("--dupes", default="./audiobook_dupes",
                        help="Quarantine directory for duplicates (default: ./audiobook_dupes).")
    parser.add_argument("--log", default="./abs_organise.log",
                        help="Log file path (default: ./abs_organise.log).")
    parser.add_argument("--no-cover", dest="no_cover", action="store_true",
                        help="Skip cover art extraction.")
    parser.add_argument("--book-dedup", dest="book_dedup", action="store_true",
                        help="Enable book-level deduplication (prefer M4B, prefer newer).")
    parser.add_argument("--show-quality", dest="show_quality", action="store_true",
                        help="Log audio quality info (bitrate, duration, codec) per file.")
    parser.add_argument("--workers", type=int, default=0,
                        help="Parallel workers for I/O (0=auto-detect, default: 0).")

    return parser.parse_args(argv)


def _discover_audio_files(source_dir: str) -> list[str]:
    """Recursively find all audio files under *source_dir*, sorted."""
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(source_dir):
        for name in filenames:
            ext = os.path.splitext(name)[1].lstrip(".").lower()
            if ext in AUDIO_EXTENSIONS:
                found.append(os.path.join(dirpath, name))
    found.sort()
    return found


def _print_header(args: argparse.Namespace, log: AbsorgLogger, workers: int) -> None:
    """Print the configuration banner at the start of a run."""
    log.log(f"  Source      : {args.source}")
    log.log(f"  Destination : {args.dest}")
    log.log(f"  Duplicates  : {args.dupes}")
    log.log(f"  Log         : {args.log}")
    log.log(f"  Cover art   : {'yes' if not args.no_cover else 'no'}")
    if getattr(args, "book_dedup", False):
        log.log("  Book dedup  : yes (prefer M4B, prefer newer)")
    if getattr(args, "show_quality", False):
        log.log("  Show quality: yes")
    worker_label = "auto-detected" if not args.workers else "user-specified"
    log.log(f"  Workers     : {workers} ({worker_label})")
    if args.dry_run:
        log.logy("  Mode        : DRY RUN — nothing will be moved (add --move to apply)")
    else:
        log.logg("  Mode        : LIVE — files will be moved")
    log.log()


def _log_file_metadata(
    filepath: str,
    meta: MetadataResult,
    dest_file: str,
    no_meta: bool,
    log: AbsorgLogger,
    *,
    audio_info: AudioInfo | None = None,
) -> None:
    """Log per-file metadata details."""
    log.logc(f"  FILE     : {filepath}")
    log.log(f"  Author   : {sanitise(meta.author) if meta.author else '?'}")
    log.log(f"  Book     : {sanitise(meta.book) if meta.book else '?'}")

    if meta.series:
        series_info = meta.series
        if meta.series_index:
            series_info += f" #{meta.series_index}"
        log.log(f"  Series   : {series_info}")
    if meta.title:
        log.log(f"  Chapter  : {meta.title}")
    if meta.track:
        track_info = meta.track
        if meta.disc:
            track_info += f"  Disc: {meta.disc}"
        log.log(f"  Track    : {track_info}")
    if meta.year:
        log.log(f"  Year     : {meta.year}")
    if meta.narrator:
        log.log(f"  Narrator : {meta.narrator}")
    if meta.subtitle:
        log.log(f"  Subtitle : {meta.subtitle}")
    if meta.genre:
        log.log(f"  Genre    : {meta.genre}")
    if audio_info:
        log.log(f"  Quality  : {format_quality(audio_info)}")
    if no_meta:
        log.logy("  WARNING  : No embedded tags — inferred from path/filename")
    log.log(f"  --> {dest_file}")


def _print_summary(
    counters: Counters,
    dry_run: bool,
    dupes_dir: str,
    log: AbsorgLogger,
) -> None:
    """Print the run summary."""
    log.log()
    if dry_run:
        log.log(log.bold("DRY RUN complete"))
        log.log(f"  Would move    : {counters.moved} files")
        log.log(f"  Skipped       : {counters.skipped} (already in place)")
        log.log(f"  Duplicates    : {counters.dupe} (would quarantine to {dupes_dir})")
        log.log(f"  Conflicts     : {counters.conflict} (would rename with suffix)")
        if counters.book_dedup_groups > 0:
            log.log(f"  Book dedup    : {counters.book_dedup_groups} groups resolved, {counters.book_dedup} files (would quarantine)")
        log.logy("  Run with --move to apply.")
    else:
        log.log(log.bold("Complete"))
        log.log(f"  Moved         : {counters.moved} files")
        log.log(f"  Skipped       : {counters.skipped}")
        log.log(f"  Covers        : {counters.cover} extracted")
        log.log(f"  Duplicates    : {counters.dupe} quarantined")
        log.log(f"  Conflicts     : {counters.conflict} renamed")
        log.log(f"  Failed        : {counters.failed}")
        if counters.book_dedup_groups > 0:
            log.log(f"  Book dedup    : {counters.book_dedup_groups} groups resolved, {counters.book_dedup} files quarantined")
        if counters.no_meta > 0:
            log.logy(f"  WARNING: {counters.no_meta} files had no metadata — inferred from path/filename")
        if counters.dupe > 0 or counters.book_dedup > 0:
            log.logy(f"  Review duplicates in {dupes_dir}")


def _log_book_dedup_decisions(
    decisions: list[BookDedupDecision],
    log: AbsorgLogger,
) -> None:
    """Log book-level dedup decisions before processing starts."""
    log.log()
    log.log(log.bold(f"BOOK-LEVEL DEDUP: {len(decisions)} book(s) with multiple editions"))
    log.log()
    for d in decisions:
        log.log(f"  {d.book_display}")
        log.logg(f"    KEEP:       {d.kept.source_dir} ({_edition_summary(d.kept)})")
        for q in d.quarantined:
            log.logm(f"    QUARANTINE: {q.source_dir} ({_edition_summary(q)})")
        log.log(f"    Reason: {d.reason}")
        log.log()


def _process_file(
    filepath: str,
    args: argparse.Namespace,
    tracker: DedupTracker,
    counters: Counters,
    log: AbsorgLogger,
    *,
    metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]] | None = None,
    show_quality: bool = False,
) -> None:
    """Process a single audio file: resolve metadata, dedup, move/skip."""
    # ─── Stage 1: metadata ────────────────────────────────────────────────
    # Reuse cached metadata from the book-dedup pre-pass when available;
    # otherwise read tags now. Audio info is only computed when --show-quality
    # is enabled.
    abs_path = os.path.abspath(filepath)
    audio_info: AudioInfo | None = None

    if metadata_cache and abs_path in metadata_cache:
        meta, audio_info = metadata_cache[abs_path]
    else:
        meta = resolve_metadata(filepath)
        if show_quality:
            audio_info = extract_audio_info(filepath)

    ip = infer_from_path(filepath, args.source)
    ifn = infer_from_filename(os.path.basename(filepath))

    # ─── Stage 2: destination ─────────────────────────────────────────────
    # Combine tags + path inference + filename inference into a final dest.
    dest = build_dest(filepath, meta, ip, ifn, args.dest)

    # Already-in-place check — short-circuit before logging anything noisy.
    if os.path.normpath(os.path.abspath(filepath)) == os.path.normpath(os.path.abspath(dest.dest_file)):
        log.logd(f"  SKIP (already in place): {os.path.basename(filepath)}")
        counters.skipped += 1
        return

    # Log metadata
    _log_file_metadata(
        filepath, meta, dest.dest_file, dest.no_meta, log,
        audio_info=audio_info if show_quality else None,
    )

    # ─── Stage 3: dedup decision ──────────────────────────────────────────
    # tracker.check() compares fingerprints against both in-run claimed
    # destinations and pre-existing files at the target path.
    dedup_result = tracker.check(filepath, dest.dest_file)

    if dedup_result.action == DedupAction.QUARANTINE:
        quarantine(filepath, args.dupes, args.source, args.dry_run, "DUPLICATE", log)
        counters.dupe += 1
        log.log()
        return

    if dedup_result.action == DedupAction.SKIP:
        log.logd("  EXISTING DUPLICATE: already at destination (fingerprints match)")
        counters.dupe += 1
        counters.skipped += 1
        log.log()
        return

    # PROCEED — possibly with a renamed destination
    dest_file = dedup_result.dest_file
    dest_dir = os.path.dirname(dest_file)

    if dedup_result.dest_file != dest.dest_file:
        counters.conflict += 1
        log.logy(f"  CONFLICT: renaming to {dest_file}")

    # ─── Stage 4: claim the destination ───────────────────────────────────
    # tracker.register() MUST run before the dry-run guard so that later
    # files in the same run see this dest as claimed and route around it.
    # Without this, two source files mapping to the same dest would both
    # report "would move" in dry-run mode and silently collide on apply.
    tracker.register(dest_file, filepath)

    if args.dry_run:
        log.log("  [DRY RUN — would move]")
        counters.moved += 1
        log.log()
        return

    # ─── Stage 5: live move ───────────────────────────────────────────────
    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(filepath, dest_file)
        log.logg("  MOVED")
        counters.moved += 1
        if dest.no_meta:
            counters.no_meta += 1
        # Cover extraction — only on live moves
        if not args.no_cover and extract_cover(dest_file, dest_dir, log):
            counters.cover += 1
    except OSError as exc:
        log.logr(f"  FAILED: {exc}")
        counters.failed += 1

    log.log()


def main(argv: list[str] | None = None) -> None:
    """Entry point for the absorg CLI."""
    args = parse_args(argv)

    log = AbsorgLogger(args.log)

    try:
        workers = args.workers or min(os.cpu_count() or 4, 16)

        _print_header(args, log, workers)

        # Validate source
        if not os.path.isdir(args.source):
            log.logr(f"ERROR: source not found: {args.source}")
            sys.exit(1)

        # ─── Phase 1: discover ────────────────────────────────────────────
        files = _discover_audio_files(args.source)
        total = len(files)
        log.log(f"Found {log.bold(total)} audio file(s)")

        if total == 0:
            log.log()
            return

        # ─── Phase 2: fingerprint pre-compute (parallel I/O) ──────────────
        log.log(f"Pre-computing fingerprints ({workers} workers)...")
        fp_cache = precompute_fingerprints(files, max_workers=workers)
        log.log(f"  {len(fp_cache)} fingerprints cached")

        tracker = DedupTracker(fingerprint_cache=fp_cache)
        counters = Counters()

        # ─── Phase 3: book-dedup (optional, two-pass mode) ────────────────
        metadata_cache: dict[str, tuple[MetadataResult, AudioInfo]] | None = None
        quarantine_files: set[str] = set()

        if getattr(args, "book_dedup", False):
            log.log()
            log.log(log.bold(f"Scanning for book-level duplicates ({workers} workers)..."))
            groups, metadata_cache = build_book_inventory(files, args.source, max_workers=workers)
            if groups:
                quarantine_files, decisions = resolve_book_duplicates(groups, args.source)
                counters.book_dedup_groups = len(decisions)
                _log_book_dedup_decisions(decisions, log)
            else:
                log.log("  No book-level duplicates found.")

        show_quality = getattr(args, "show_quality", False)

        # ─── Phase 4: per-file processing (sequential) ────────────────────
        # Sequential because DedupTracker has ordering dependencies on
        # claimed destinations within the run.
        for n, filepath in enumerate(files, 1):
            log.log()
            log.log(f"{log.bold(f'[{n}/{total}]')}")
            try:
                # Book-dedup quarantine check
                if quarantine_files:
                    file_key = os.path.normpath(os.path.abspath(filepath))
                    if file_key in quarantine_files:
                        log.logc(f"  FILE     : {filepath}")
                        quarantine(filepath, args.dupes, args.source,
                                   args.dry_run, "BOOK_DEDUP: inferior edition", log)
                        counters.book_dedup += 1
                        log.log()
                        continue

                _process_file(
                    filepath, args, tracker, counters, log,
                    metadata_cache=metadata_cache,
                    show_quality=show_quality,
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                try:
                    log.logr(f"  ERROR processing {filepath}: {exc}")
                except Exception:
                    log.logr(f"  ERROR processing file: {type(exc).__name__}: {exc}")
                counters.failed += 1
                log.log()

        # ─── Phase 5: summary ─────────────────────────────────────────────
        _print_summary(counters, args.dry_run, args.dupes, log)

    except KeyboardInterrupt:
        log.log()
        log.logy("Interrupted.")
    finally:
        log.close()
