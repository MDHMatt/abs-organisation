# fixes.md — Deferred work and known issues

This file tracks work that has been intentionally left out of the main task scope, plus concrete diagnostics surfacing in dry runs. Each entry is meant to be actionable on its own — a future session (or a human) should be able to pick any item and apply it without re-investigating the codebase.

**Maintenance rule:** when an item here is fixed, delete it (or move to the resolved notes section at the bottom). When a new deferred item is identified, add it with the same level of detail as the existing entries.

## Dry run history

| Date | Version | Image digest | Files | Would move | Skipped | Duplicates | Conflicts | Book-dedup groups | Quarantined |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-08 | v2.3.1 | `sha256:cc6f62ea…d525f3` | 3,482 | 1,762 | 1,451 | 1,454 | 341 | 118 | 266 |
| 2026-04-09 | v2.3.2 | — | 3,482 | 1,764 | 1,449 | 18 | 341 | 118 | 266 |

Key change v2.3.1 → v2.3.2: file-level duplicates dropped from 1,454 to 18 thanks to the `build_dest()` prefix-doubling fix (Issue 10, commit `f64b1ad`). The 18 remaining file-level duplicates are genuine (e.g. Good Omens `.N.m4b` copies with matching first-1 MB fingerprints).

Log files on Holly: `/mnt/user/Media/Music/absorg_dryrun.log` (v2.3.2 run), `/mnt/user/Media/Music/absorg_dryrun_console.log` (v2.3.1 run).

---

## Runtime correctness issues

*No open items.*

---

## Deferred refactors (non-blocking tech debt)

*No open items.* All tech debt from Issues 5-9 has been resolved or closed.

---

## Resolved issues

Issues below have been fixed. They are kept here for historical context.

**Issue 11** (v2.3.5): Within-directory `.N.m4b` / `.N.mp3` duplicate copies invisible to both file-level and book-level dedup. 335 conflicts and 370 suffixed files. Root cause: file-level fingerprint hashes first 1MB (moov atom differs per run), and book-level dedup collapses all copies into one inflated edition. Fixed by adding `resolve_intra_edition_duplicates()` in `bookdedup.py` — groups files within each edition by `(extension, duration±1s)`, requires `.N` suffix evidence to avoid false positives on multi-chapter books, quarantines duplicates and corrects edition stats before cross-edition scoring.

**Issue 5** (v2.3.3): Duplicate `parse_int` helper — `metadata.py` and `pathbuilder.py` each defined their own copy. Consolidated into `constants.py` (already imported by both modules). `pathbuilder.py` re-exports for backward compatibility.

**Issue 6** (v2.3.3): Test-file module docstrings — all `tests/test_*.py` files already had module docstrings. Moot.

**Issue 7** (v2.3.3): `constants.py` per-constant doc comments — added inline comments above every constant explaining its purpose and which module(s) consume it.

**Issue 8** (v2.3.3): `_process_file()` and `main()` length in `cli.py` — extracted five helpers: `_resolve_metadata_and_dest()`, `_apply_dedup_and_move()`, `_discover_and_fingerprint()`, `_run_book_dedup_pass()`, `_iterate_files()`. `_process_file()` is now 6 lines; `main()` is ~20 lines.

**Issue 9**: One-line docstrings to NumPy/Google format — closed, not worth the churn. Existing one-line docstrings are informative and sufficient. Revisit only if Sphinx or similar tooling is adopted.

**Issue 10** (v2.3.2, `f64b1ad`): `build_dest()` prefix-doubling — filenames like `22 - 22 - Chapter.mp3` caused by double-stacked track prefixes. Fixed by stripping existing numeric prefixes from the filename stem before re-prefixing.

**Issue 12** (v2.3.2, `f64b1ad`): Book-dedup tiebreaker instability — editions with equal scores could swap order between runs depending on filesystem walk order. Fixed by adding a two-phase stable sort: first by structural tiebreak key, then by score.

**Issue 13** (v2.3.2, `f64b1ad`): Misleading "higher bitrate" reason in book-dedup log when the display rounds to the same kbps on both sides (e.g. "62kbps vs 62kbps"). Fixed by suppressing the bitrate reason when display values are equal.

**Issue 14** (v2.3.3): Year-prefix book conflation — books named "YYYY - Title" (e.g. "1982 - The Gunslinger", "1982 - Different Seasons") normalised to just "YYYY" because ` - ` was treated as subtitle separator. The `len(before_sep) >= 3` guard was satisfied by the year string. **Critical data-loss bug:** Different Seasons (4 files) would be quarantined as a duplicate of The Gunslinger (14 files). Fixed by adding `and not before_sep.isdigit()` guard in `normalise_book()`.

**Issue 15** (v2.3.3): Role qualifier regex `.*` too greedy — `ROLE_QUALIFIERS_RE` ending with `.*` ate everything after the match including subsequent author names when the qualifier appeared mid-string. "Stephen Fry - introductions; Arthur Conan Doyle" normalised to "stephen fry" instead of "arthur conan doyle, stephen fry", splitting Sherlock Holmes into two separate book-dedup groups. Fixed by changing `.*` to `[^,;]*` in the regex.

**Issue 16** (v2.3.3): "(Unabridged)" not stripped from book titles — `normalise_book()` lacked parenthetical annotation stripping, causing "Unruly" and "Unruly (Unabridged)" to normalise differently. Created duplicate directories and prevented book-dedup grouping. Affected: Unruly, Fairy Tale, Die Trying, Killing Floor, The Stand, Under the Dome, Tomorrow and Tomorrow and Tomorrow, Dune. Fixed by adding `re.sub(r"\s*\([^)]*\)", "", s)` to `normalise_book()`.

---

## Notes on moot issues

- The "Mutagen ID3 frame imports — future compatibility" section that previously appeared in this file was based on an incorrect premise. Verified on mutagen 1.47.0: `from mutagen.id3 import TALB` is the stable public API. The `mutagen/id3/__init__.py` module explicitly imports all frame classes from `_frames` and re-exports them (lines 40-53). The `# deprecated` comment on line 55 refers to error utility classes (`ID3EncryptionUnsupportedError`, etc.), not frame imports. No action needed.
- The "16 remaining ruff lint issues" list that used to live in `updates.md` is obsolete — those were all cleared in the `Clear ruff SIM/B007 lint debt` commit.
- `updates.md` itself had MD009 trailing-whitespace on L8. The file was deleted in the `Remove unused PyInstaller artifacts and stale changelog` commit, so its lint state is no longer relevant.
- `absorg-linux` (8.4 MB PyInstaller binary) and `Dockerfile.pyinstaller` were both deleted in the same cleanup commit. Any references to PyInstaller as the build path in older session memory should be ignored.
