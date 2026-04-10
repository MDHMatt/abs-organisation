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

### 11. Within-directory duplicate `.N.m4b` / `.N.mp3` files are invisible to book-dedup

**Severity:** medium. Does not damage data but wastes disk and produces ever-incrementing suffix rings on repeat runs.

**Affected code:** [absorg/bookdedup.py:145-201](absorg/bookdedup.py#L145) (inventory building), in conjunction with [absorg/dedup.py:16-22](absorg/dedup.py#L16) (fingerprint function).

**Symptom from the dry run log (entries `[8/3482]` and `[9/3482]`):**

```text
FILE     : /source/Adrian Newey/How to Build a Car/How to Build a Car.2.m4b
Quality  : AAC 62kbps 22.05kHz stereo, 12h27m08s
-->        /dest/Adrian Newey/How to Build a Car/How to Build a Car.m4b
CONFLICT: renaming to /dest/Adrian Newey/How to Build a Car/How to Build a Car.3.m4b

FILE     : /source/Adrian Newey/How to Build a Car/How to Build a Car.4.m4b
Quality  : AAC 62kbps 22.05kHz stereo, 12h27m08s
-->        /dest/Adrian Newey/How to Build a Car/How to Build a Car.m4b
CONFLICT: renaming to /dest/Adrian Newey/How to Build a Car/How to Build a Car.5.m4b
```

Five files (`.m4b`, `.2.m4b`, `.3.m4b`, `.4.m4b`, `.5.m4b`), all same author, same book, same duration `12h27m08s`, same bitrate. Every run bumps the suffixes up by two because each file computes the base filename `How to Build a Car.m4b` as its target and then conflict-renames to the next free `.N.m4b`. Similar pattern for Patrick Stewart *Making It So*, Andy Weir *Project Hail Mary*, Andrea Mara *No One Saw a Thing*, and many more.

**Count:** 370 files in the library match `\.[0-9]+\.(mp3|m4b)$` (`grep -cE "FILE     :.*\.[0-9]+\.[a-z0-9]+$" absorg_dryrun.log`).

**Root cause — why file-level dedup doesn't catch them:** `fingerprint()` in [absorg/dedup.py:16-22](absorg/dedup.py#L16) is `"{size}:{md5(first 1 MB)}"`. For M4B/MP4 files, the `moov` atom (which contains all metadata) can land in the first MB and is padded differently after each absorg run (because mutagen rewrites tags during cover extraction). The first-1 MB MD5 therefore differs even when the underlying audio is identical, and the file is marked PROCEED rather than QUARANTINE.

**Root cause — why book-dedup doesn't catch them either:** [absorg/bookdedup.py:145-201](absorg/bookdedup.py#L145) groups files by `(directory, normalised (author, book))`. All five `How to Build a Car.N.m4b` files live in the same directory and share the same (author, book), so they collapse into **one edition with `file_count=5`, `total_duration=62h15m40s` (5x12h27m08s)**. Book-dedup only fires when two or more *editions* exist for the same normalised key; a single edition holding multiple copies of the same book looks like a multi-part work to the inventory.

**Fix direction:** add an intra-edition dedup pass during `build_book_inventory()`. For each edition, if multiple files share the same `(duration, bitrate, format)` up to a small tolerance (say +/-1 second on duration, exact on format), collapse to the file with the shortest basename (i.e. the one without a `.N` suffix), and emit the rest as quarantine targets under a new reason like `INTRA_DIR_DUPE: identical duration + format`. Add the quarantined paths to the same `quarantine_files` set that cross-edition dedup uses.

Alternative (less invasive): widen the `fingerprint()` window. Sampling a small middle-of-file slice (e.g. 512 KB starting at file-size / 2) in addition to the first 1 MB would skip over the moov atom for most M4B files and capture actual audio frame bytes. This would let the existing file-level dedup catch the duplicates without any bookdedup changes. Downside: reads are no longer sequential, which is slower on spinning rust. Holly is on spinning rust, so measure before committing.

**Deferred because:** now that Issues 10, 14, 15, and 16 are fixed, the conflict-rename suffix residue can be cleaned up in a one-off sweep rather than chased every run. Re-assess after the first clean `--move` run lands on Holly.

---

## Deferred refactors (non-blocking tech debt)

### 5. Duplicate `parse_int` helper between `metadata.py` and `pathbuilder.py`

[absorg/metadata.py:32-35](absorg/metadata.py#L32) defines `_parse_int()` and [absorg/pathbuilder.py:32-40](absorg/pathbuilder.py#L32) defines `parse_int()`. Both extract leading digits from a string. Extract to a single helper in a new `absorg/util.py` module (or move into `constants.py` / `normalise.py` if a new file feels heavy). Non-urgent — neither copy is buggy. Deferred because it is a refactor crossing two modules and changing public-ish API, which is out of scope for a docs-only pass.

### 6. Test-file module docstrings

None of the files under `tests/` have top-of-file docstrings other than `tests/test_cli.py`. Adding one-line module docstrings to each `tests/test_*.py` would be mechanical and harmless. Deferred because the user scoped the doc pass to `absorg/`.

### 7. `constants.py` per-constant doc comments

The Part 2a doc pass expanded the `absorg/constants.py` module docstring to group constants by purpose. A fuller pass would add a comment above each individual constant explaining its semantics, e.g.:

```python
PATH_COMPONENT_MAX_LENGTH = 180  # keep under Windows MAX_PATH minus headroom
```

Deferred — the module docstring already covers the grouping, and this would be churn for marginal benefit.

### 8. `_process_file()` and `main()` length in `absorg/cli.py`

Both functions are ~90 lines after the Part 2 inline-comment additions. A future split into helpers like `_resolve_and_log_metadata()`, `_apply_dedup_decision()`, `_discover_and_fingerprint()`, `_run_book_dedup_pass()`, `_iterate_files()` would improve readability. Explicitly out of scope for the doc pass — that pass only permitted comments, not refactors. Revisit after the v2.4.x series settles.

### 9. One-line public docstrings to NumPy/Google format

Most public functions across `absorg/` have informative one-line docstrings. Rewriting them to a full `Parameters / Returns / Raises` format would be churn for marginal benefit and would bloat the files. Deferred indefinitely unless a downstream tool (e.g. Sphinx) requires it.

---

## Resolved issues

Issues below have been fixed. They are kept here for historical context.

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
