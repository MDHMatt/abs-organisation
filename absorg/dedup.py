"""Deduplication and fingerprinting for the audiobook organiser."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum

from absorg.logger import AbsorgLogger


def fingerprint(filepath: str) -> str:
    """Compute a fast file fingerprint: ``"{size}:{md5_hex}"``."""
    size = os.path.getsize(filepath)
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        md5.update(f.read(1_048_576))  # first 1 MB
    return f"{size}:{md5.hexdigest()}"


class DedupAction(Enum):
    """What the organiser should do with a file after dedup analysis."""

    PROCEED = "proceed"  # Move to destination (possibly renamed)
    QUARANTINE = "quarantine"  # Duplicate — send to dupes dir
    SKIP = "skip"  # Already at destination, skip


@dataclass
class DedupResult:
    """Outcome of a dedup check for a single file."""

    action: DedupAction
    dest_file: str  # Final destination (may be renamed from original)


class DedupTracker:
    """Track claimed destinations within a single organise run.

    Detects both in-run collisions (two source files mapping to the same
    destination) and on-disk collisions (a source file mapping to a path
    that already exists from a previous run).
    """

    def __init__(self, fingerprint_cache: dict[str, str] | None = None) -> None:
        self.seen_dests: dict[str, str] = {}  # normalised dest → fingerprint
        self._fp_cache: dict[str, str] = fingerprint_cache or {}

    def _get_fingerprint(self, filepath: str) -> str:
        """Return fingerprint from cache or compute on demand."""
        norm = os.path.normpath(os.path.abspath(filepath))
        if norm in self._fp_cache:
            return self._fp_cache[norm]
        fp = fingerprint(filepath)
        self._fp_cache[norm] = fp
        return fp

    def register(self, dest_file: str, source_file: str) -> None:
        """Record that *source_file* has claimed *dest_file*.

        This **must** be called before the dry-run guard so that later files
        see the claimed destination even when no files are actually moved.
        """
        key = os.path.normpath(dest_file)
        self.seen_dests[key] = self._get_fingerprint(source_file)

    def check(self, source_file: str, dest_file: str) -> DedupResult:
        """Determine whether *source_file* can be placed at *dest_file*.

        Returns a :class:`DedupResult` indicating the action to take.
        """
        norm = os.path.normpath(dest_file)
        src_fp = self._get_fingerprint(source_file)

        # Phase 1: in-run collision
        if norm in self.seen_dests:
            existing_fp = self.seen_dests[norm]
            if src_fp == existing_fp:
                return DedupResult(action=DedupAction.QUARANTINE, dest_file=dest_file)
            # Different content → conflict-rename
            free = self.find_free_dest(dest_file)
            return DedupResult(action=DedupAction.PROCEED, dest_file=free)

        # Phase 2: on-disk collision
        if os.path.exists(dest_file):
            existing_fp = self._get_fingerprint(dest_file)
            if src_fp == existing_fp:
                return DedupResult(action=DedupAction.SKIP, dest_file=dest_file)
            free = self.find_free_dest(dest_file)
            return DedupResult(action=DedupAction.PROCEED, dest_file=free)

        # No collision
        return DedupResult(action=DedupAction.PROCEED, dest_file=dest_file)

    def find_free_dest(self, dest_path: str) -> str:
        """Return the first available path by appending ``.2``, ``.3``, etc."""
        base, ext = os.path.splitext(dest_path)
        n = 2
        while True:
            candidate = f"{base}.{n}{ext}"
            norm = os.path.normpath(candidate)
            if not os.path.exists(candidate) and norm not in self.seen_dests:
                return candidate
            n += 1


def precompute_fingerprints(
    files: list[str],
    max_workers: int = 4,
) -> dict[str, str]:
    """Pre-compute fingerprints for all *files* in parallel.

    Returns a dict mapping normalised absolute path to fingerprint string.
    Files that cannot be read are silently skipped (computed on demand later).
    """
    cache: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fingerprint, f): os.path.normpath(os.path.abspath(f))
            for f in files
        }
        for future in as_completed(futures):
            norm_path = futures[future]
            # Files that fail will be computed on-demand in check()
            with contextlib.suppress(OSError):
                cache[norm_path] = future.result()
    return cache


def quarantine(
    source_file: str,
    dupes_dir: str,
    source_dir: str,
    dry_run: bool,
    reason: str,
    logger: AbsorgLogger,
) -> None:
    """Move a duplicate file to *dupes_dir*, preserving its relative path."""
    rel = os.path.relpath(source_file, source_dir)
    dupe_dest = os.path.join(dupes_dir, rel)

    logger.logm(f"QUARANTINE ({reason}): {source_file} -> {dupe_dest}")

    if not dry_run:
        try:
            os.makedirs(os.path.dirname(dupe_dest), exist_ok=True)
            shutil.move(source_file, dupe_dest)
        except OSError as exc:
            logger.logr(f"Failed to quarantine {source_file}: {exc}")
