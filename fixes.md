# fixes.md — Deferred work and known issues

This file tracks work that has been intentionally left out of the main task scope (clean-up, documentation pass, README), plus concrete diagnostics that are currently surfacing in files open in the IDE. Each entry is meant to be actionable on its own — a future session (or a human) should be able to pick any item and apply it without re-investigating the codebase.

**Maintenance rule:** when an item here is fixed, delete it. When a new deferred item is identified, add it with the same level of detail as the existing entries.

## Markdown lint errors in tracked files

`CLAUDE.md` was authored against an older interpretation of the `.markdownlint.json` config and now fails several rules under `markdownlint-cli@0.48.0`. Notably, the config sets `"MD060": { "style": "compact" }` but `compact` is not a valid value for MD060 — markdownlint silently falls back to `consistent`, which then complains that the table separator rows do not match the header rows for pipe spacing. The cleanest path is to either (a) change the separator rows to use spaces, matching the header rows, or (b) change `MD060` to `"leading_and_trailing"` in `.markdownlint.json` and accept that as the project policy.

### 1. `CLAUDE.md` MD060 — separator rows do not match header spacing

**Affected lines:** [CLAUDE.md:12](CLAUDE.md#L12), [CLAUDE.md:57](CLAUDE.md#L57), [CLAUDE.md:171](CLAUDE.md#L171).

Each of these is a table separator row using `|---|---|---|` while its header row uses spaced cells like `| Layer | Tool |`. Fix one of two ways.

**Option A — pad the separator rows.** Change every `|---|---|---|` to `| --- | --- | --- |` (with the appropriate column count). This is a per-file fix and matches the README.md style introduced in this task.

**Option B — change the project policy.** Edit `.markdownlint.json` to set `"MD060": { "style": "leading_and_trailing" }` (the actual valid style name). Then keep the existing CLAUDE.md tables as-is *only if* you also strip the spaces from the header rows so both styles match. This is a global decision and affects future PRs, so should not be applied silently.

Recommended: **Option A**, since it is local to the docs that already exist and matches what README.md now does.

### 2. `CLAUDE.md:70`, `CLAUDE.md:101`, `CLAUDE.md:183` MD040 — fenced code blocks missing language

Three plain triple-backtick fences are used for directory tree and flow-diagram listings without a language hint. Add `text` (the conventional choice for tree-like ASCII output) immediately after the opening fence on each of those three lines, e.g. change ` ``` ` to ` ```text `. The closing fence stays as plain triple-backticks.

### 3. `CLAUDE.md:145` MD009 — trailing whitespace

**Affected line:** [CLAUDE.md:145](CLAUDE.md#L145). The line reading `` `normalise.py` produces canonical grouping keys for dedup. `` has a single trailing space after the period. Fix: strip the trailing whitespace.

### 4. `CLAUDE.md:150` MD032 — list not preceded by blank line

**Affected lines:** [CLAUDE.md:149-150](CLAUDE.md#L149). Between L149 (which ends with `For example:`) and L150 (`- "Alan Partridge Series 1" ...`) there is no blank line before the bulleted list. Insert a blank line so the list is preceded by a blank line.

```markdown
...preserves volume/series markers** (Series, Part, Act, Volume, Book, etc.) that distinguish different works. For example:

- "Alan Partridge Series 1" and "Alan Partridge Series 2" normalize to different keys
```

**Verify (all CLAUDE.md fixes):** `npx --yes markdownlint-cli@0.48.0 CLAUDE.md` should exit 0.

## Mutagen ID3 frame imports — future compatibility

**Issue:** ID3 frame classes (`TALB`, `TIT2`, `TPE2`, `TRCK`, `TCON`, etc.) are located in the private `mutagen.id3._frames` submodule in mutagen ≥1.47. Importing directly from `mutagen.id3` (the public API) is deprecated and may fail in future versions.

**Common frames used in `absorg`:**
- `TALB` — album/book title
- `TIT2` — song/track title  
- `TPE1` — artist/author
- `TPE2` — album artist
- `TRCK` — track number
- `TCON` — content type (genre)
- `TDRC` — date recorded
- `APIC` — attached picture (cover art)

**Fix — two approaches:**

1. **Direct import from `_frames`** (required for newer mutagen):
   ```python
   from mutagen.id3._frames import TALB, TIT2, TPE1, TPE2, TRCK, TCON, TDRC, APIC
   ```

2. **High-level tag API** (recommended for robustness; works across versions):
   ```python
   from mutagen.id3 import ID3
   tag = ID3(file_path)
   tag['TALB'] = mutagen.id3.TALB(text=['Album Title'])
   tag['TIT2'] = mutagen.id3.TIT2(text=['Track Title'])
   # Frame creation via string key is stable across versions
   ```

**Recommendation:** Refactor test fixtures in [tests/conftest.py](tests/conftest.py) and any tag-writing code to use the high-level API (approach 2) wherever possible. This shields the codebase from mutagen's private API churn. If direct frame instantiation is necessary, fall back to the `_frames` import (approach 1) but wrap it in a version check or try/except for forward compatibility:

```python
try:
    from mutagen.id3._frames import TALB
except ImportError:
    # future mutagen version with different private structure
    from mutagen.id3 import TALB
```

**Status:** Not urgent if tests are currently passing, but should be addressed before upgrading mutagen beyond 1.47. Mark for v2.4.x or later.

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

### 9. One-line public docstrings → NumPy/Google format

Most public functions across `absorg/` have informative one-line docstrings. Rewriting them to a full `Parameters / Returns / Raises` format would be churn for marginal benefit and would bloat the files. Deferred indefinitely unless a downstream tool (e.g. Sphinx) requires it.

## Runtime correctness issues surfaced by dry run on 2026-04-08

These issues were found by running `mdhmatt/abs-organiser:latest` (v2.3.1, digest `sha256:cc6f62ea3df3…d525f3`) in dry-run mode against the consolidated Holly library (`/mnt/user/Media/Music/Audiobooks`, 3,482 files: 2,762 MP3 + 720 M4B) using `--book-dedup --show-quality`. The dry run was an idempotency check (source == dest) against a library already organised by a previous live run of v2.1.0. It reported `1,762 would move / 1,451 skipped / 1,454 duplicates / 341 conflicts / 118 book-dedup groups / 266 files quarantined`. None of the issues below are regressions from the v2.3.1 type-guard commit (`43789ee`) — the mutagen `cast()` work is behaviour-preserving and the library contains zero FLAC/OGG/Opus/WMA files, so the ASFTag→ASFTags runtime-bug fix in that commit had no observable effect. Every finding here is a **pre-existing** defect that the dry run exposed.

Log file on Holly for future investigation: `/mnt/user/Media/Music/absorg_dryrun.log` (42,059 lines, 1.5 MB). A mirror of the stdout stream is at `/mnt/user/Media/Music/absorg_dryrun_console.log`.

Issues 10, 12, and 13 were fixed in a follow-up commit. Issue 11 remains deferred — see its entry below for why.

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

**Root cause — why book-dedup doesn't catch them either:** [absorg/bookdedup.py:145-201](absorg/bookdedup.py#L145) groups files by `(directory, normalised (author, book))`. All five `How to Build a Car.N.m4b` files live in the same directory and share the same (author, book), so they collapse into **one edition with `file_count=5`, `total_duration=62h15m40s` (5×12h27m08s)**. Book-dedup only fires when two or more *editions* exist for the same normalised key; a single edition holding multiple copies of the same book looks like a multi-part work to the inventory.

**Fix direction:** add an intra-edition dedup pass during `build_book_inventory()`. For each edition, if multiple files share the same `(duration, bitrate, format)` up to a small tolerance (say ±1 second on duration, exact on format), collapse to the file with the shortest basename (i.e. the one without a `.N` suffix), and emit the rest as quarantine targets under a new reason like `INTRA_DIR_DUPE: identical duration + format`. Add the quarantined paths to the same `quarantine_files` set that cross-edition dedup uses.

Alternative (less invasive): widen the `fingerprint()` window. Sampling a small middle-of-file slice (e.g. 512 KB starting at file-size / 2) in addition to the first 1 MB would skip over the moov atom for most M4B files and capture actual audio frame bytes. This would let the existing file-level dedup catch the duplicates without any bookdedup changes. Downside: reads are no longer sequential, which is slower on spinning rust. Holly is on spinning rust, so measure before committing.

**Deferred because:** now that Issue 10 is fixed, the conflict-rename suffix residue can be cleaned up in a one-off sweep rather than chased every run. Re-assess after the first clean `--move` run lands on Holly.

---

## Notes on moot issues

These were observed during the audit but do not need fixing because they have been resolved by other commits in this task or because the affected file no longer exists.

- The "16 remaining ruff lint issues" list that used to live in `updates.md` is obsolete — those were all cleared in the `Clear ruff SIM/B007 lint debt` commit on this branch.
- `updates.md` itself had MD009 trailing-whitespace on L8 (and possibly other markdownlint findings). The file was deleted in the `Remove unused PyInstaller artifacts and stale changelog` commit, so its lint state is no longer relevant.
- `absorg-linux` (8.4 MB PyInstaller binary) and `Dockerfile.pyinstaller` were both deleted in the same cleanup commit. Any references to PyInstaller as the build path in older session memory should be ignored.
