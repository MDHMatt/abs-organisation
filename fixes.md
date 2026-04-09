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

These four issues were found by running `mdhmatt/abs-organiser:latest` (v2.3.1, digest `sha256:cc6f62ea3df3…d525f3`) in dry-run mode against the consolidated Holly library (`/mnt/user/Media/Music/Audiobooks`, 3,482 files: 2,762 MP3 + 720 M4B) using `--book-dedup --show-quality`. The dry run was an idempotency check (source == dest) against a library already organised by a previous live run of v2.1.0. It reported `1,762 would move / 1,451 skipped / 1,454 duplicates / 341 conflicts / 118 book-dedup groups / 266 files quarantined`. None of the issues below are regressions from the v2.3.1 type-guard commit (`43789ee`) — the mutagen `cast()` work is behaviour-preserving and the library contains zero FLAC/OGG/Opus/WMA files, so the ASFTag→ASFTags runtime-bug fix in that commit had no observable effect. Every finding here is a **pre-existing** defect that the dry run exposed.

Log file on Holly for future investigation: `/mnt/user/Media/Music/absorg_dryrun.log` (42,059 lines, 1.5 MB). A mirror of the stdout stream is at `/mnt/user/Media/Music/absorg_dryrun_console.log`.

**DO NOT run the v2.3.1 image with `--move` on Holly until Issue 10 is fixed.** Running live in the current state would actively damage the library by stacking another layer of `NN -` prefixes on ~1,424 already-sanitised files and adding `.N.m4b` suffix rings to another ~370 conflict-rename residue files.

### 10. Pathbuilder prepends a track prefix on top of an already-prefixed filename (non-idempotent — DAMAGING)

**Severity:** high. This is the blocker for any future `--move` run.

**Affected code:** [absorg/pathbuilder.py:100-118](absorg/pathbuilder.py#L100). Specifically line 116:

```python
st = sanitise(metadata.title or os.path.splitext(filename)[0])
```

**Symptom from the dry run log (entry `[880/3482]`):**

```text
FILE     : /source/Richard Bachman/Blaze/01 - 01 - 0│ Introduction.mp3
Author   : Richard Bachman
Book     : Blaze
Track    : 1
Year     : 2007
Quality  : MP3 96kbps 44.1kHz mono, 11m25s
-->        /dest/Richard Bachman/Blaze/01 - 01 - 01 - 0│ Introduction.mp3
[DRY RUN — would move]
```

The source filename already contains `01 - 01 -` (two prior runs worth of track prefix) and the run would produce `01 - 01 - 01 -` (three). Nothing in the skip/rename path catches this because the computed dest path differs from the source path by exactly the newly-added prefix, so the [absorg/cli.py:238](absorg/cli.py#L238) already-in-place short-circuit does not fire. The tracker then treats it as a move.

**Root cause:** when an MP3 has a track-number tag but **no title tag**, the fallback for the title component is `os.path.splitext(filename)[0]` — i.e. the current filename minus extension. For a file that was produced by a previous run of absorg, that stem already looks like `01 - Whatever`. The pathbuilder then prepends another `f"{int(track):02d} - "` (line 118) without checking whether the stem already starts with an `NN -` prefix. Each run layers on one more prefix. The `│` (U+2502) in the Blaze sample is the sanitise map's replacement for `|`, which confirms these files have been round-tripped through absorg at least once before.

Confirmed scope via the log: **1,424 non-churn `FILE :` lines appear inside `would move` blocks** (`grep -B12 "would move" | grep -vE '\.[0-9]+\.[a-z0-9]+$'`). The Stephen King / Richard Bachman subtree is the largest contributor. Every one of these runs the same code path and would get another prefix stacked.

**Fix direction (preferred):** strip a leading `NN -` or `DNN-TNN -` prefix from the filename stem before using it as the title fallback. Pseudocode to drop into [absorg/pathbuilder.py:116](absorg/pathbuilder.py#L116):

```python
import re

_TRACK_PREFIX_RE = re.compile(r"^(?:D\d{2}-T\d{2}|\d{2})\s*-\s*")

...

if metadata.title:
    st = sanitise(metadata.title)
else:
    stem = os.path.splitext(filename)[0]
    # Strip a leading NN -  or DNN-TNN -  that is the signature of a
    # previous absorg run, so re-running over an already-organised tree
    # is idempotent and does not stack prefixes.
    stem = _TRACK_PREFIX_RE.sub("", stem)
    st = sanitise(stem)
```

Belt-and-braces alternative: also compare the *normalised* source and computed-dest basenames (with any number of leading `NN -` prefixes stripped from both) in the already-in-place short-circuit. This would catch residue from any future format change too, not just this one. Pure defence-in-depth — do not use as the only fix, because it hides rather than corrects the underlying path drift.

**Test coverage needed:** a pytest case under `tests/test_pathbuilder.py` that:

1. Creates an MP3 with `Track=1`, `Title=""`, filename `"01 - 01 - Introduction.mp3"`.
2. Asserts `build_dest()` returns a dest filename of `"01 - Introduction.mp3"`, not `"01 - 01 - 01 - Introduction.mp3"`.
3. Also covers the `DNN-TNN -` multi-disc variant.

**Verification after fix:** re-pull the image on Holly, re-run the exact same dry-run command, confirm the `[880/3482]` entry (Richard Bachman/Blaze Introduction) reports `SKIP (already in place)` and that the aggregate "would move" count drops by at least ~1,400.

---

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

**Deferred because:** the prefix-doubling issue (#10) is the urgent one and must land first. Once that fix is in and the library is re-organised cleanly, the conflict-rename suffix residue can be cleaned up in a one-off sweep rather than on every run.

---

### 12. Book-dedup tiebreaker picks the alphabetically-last source_dir, which systematically prefers mis-organised folders

**Severity:** medium. Would actively move correctly-structured content into quarantine if run live.

**Affected code:** [absorg/bookdedup.py:233-241](absorg/bookdedup.py#L233):

```python
for _key, group in sorted(groups.items()):
    ranked = sorted(
        group.editions,
        key=lambda e: (score_edition(e), e.source_dir),
        reverse=True,
    )
    kept = ranked[0]
    losers = ranked[1:]
```

**Symptom from the dry run log — book-dedup section:**

```text
"Children of Memory: Children of Time, Book 3" by Adrian Tchaikovsky
  KEEP:       /source/Adrian Tchikovski  (M4B, 2022, 125kbps, 13h26m06s, 1 file)
  QUARANTINE: /source/Adrian Tchaikovsky/Children of Memory… (M4B, 2022, 125kbps, 13h26m06s, 1 file)
  Reason: higher overall score

"Sherlock Holmes: The Definitive Collection" by Arthur Conan Doyle, Stephen Fry - introductions
  KEEP:       /source/_Unknown Author/Sherlock Holmes [B06X1BRZYC]  (M4B, 2017, 62kbps, 71h57m52s, 1 file)
  QUARANTINE: /source/Arthur Conan Doyle, Stephen Fry - introductions/Sherlock Holmes/…
  Reason: higher overall score

"The Martian" by Andy Weir
  KEEP:       /source/The Martian.m4b  (root-level loose file)
  QUARANTINE: /source/Andy Weir/The Martian (properly-tagged folder)
  Reason: higher overall score
```

118 total groups, of which **109 emit the uninformative "Reason: higher overall score"** — i.e. all strong signals (format, year, bitrate, duration) tied and the decision fell entirely on the `e.source_dir` tiebreaker. Only 9 groups had a real reason (M4B preferred, newer recording, higher bitrate).

**Root cause:** `sorted(..., reverse=True)` on the key `(score_edition(e), e.source_dir)` means when `score_edition` is equal, the **alphabetically last** `source_dir` wins. This produces three classes of bad pick, all visible in the log:

1. **Typos beat correct spellings.** `/source/Adrian Tchikovski` (T-c-h-**i**-k, ASCII 105) sorts after `/source/Adrian Tchaikovsky` (T-c-h-**a**-i, ASCII 97). Reversed, the typo wins. Same book × 3 (*Children of Time*, *Children of Ruin*, *Children of Memory*).
2. **Underscore-prefixed placeholder dirs beat tagged ones.** `_` is ASCII 95, `A` is 65, so `/source/_Unknown Author/Sherlock Holmes [B06X1BRZYC]` sorts after `/source/Arthur Conan Doyle…`. Reversed, the `_Unknown Author` placeholder wins. The user's prior session memory explicitly records the `_Unknown Author` folder as a scratch dumping ground — keeping it would undo real organisation work.
3. **Root-level loose files beat organised `Author/Book/` folders.** `/source/The Martian.m4b` (the full file path used as source_dir for root files — see [absorg/bookdedup.py:134](absorg/bookdedup.py#L134)) has `T` after `/source/Andy Weir/The Martian`'s `A`. Reversed, the loose file wins. Same pattern for *Battle Cruiser*, *Dreadnought*, *Star Carrier*, *Steel World*, *The Nox*, *Black Ops*, *Columbus Day*, and the full Three-Body / Rama / Aurora Cycle series.

**Fix direction:** replace the `e.source_dir` tiebreaker with a structural tiebreaker that prefers "better-organised" paths. Concretely, sort ties by (in order):

1. **Is the source a root-level loose file?** `-1` if it is (penalised), `0` otherwise. Loose files at the library root always lose ties to organised folders.
2. **Does the path contain a placeholder segment** like `_Unknown Author`, `_unknown`, `Unknown`, `Audiobooks`, `Classics & General Fiction`? `-1` per offending segment, `0` otherwise.
3. **Does any path segment match the tagged author name** (case-insensitively, after `normalise_author`)? `+1` if yes, `0` otherwise. Rewards dirs whose filesystem path already agrees with the file's own metadata.
4. **Path depth** (number of segments under `source_dir`). More depth = more specific = preferred.
5. **Alphabetical source_dir as final deterministic fallback** (not reversed — prefer alphabetically *earlier*, so typos lose to correct spellings).

Drop-in code sketch for [absorg/bookdedup.py:233](absorg/bookdedup.py#L233):

```python
_PLACEHOLDER_SEGMENTS = {"_unknown author", "_unknown", "unknown", "audiobooks", "classics & general fiction"}

def _tiebreak_key(edition: BookEdition, source_root: str) -> tuple[int, int, int, int, str]:
    path = edition.source_dir
    rel = os.path.relpath(path, source_root) if path.startswith(source_root) else path
    segments = [s for s in rel.split(os.sep) if s]
    is_root_loose = 1 if len(segments) <= 1 else 0
    placeholder_hits = sum(1 for s in segments if s.lower() in _PLACEHOLDER_SEGMENTS)
    norm_author = normalise_author(edition.author or "")
    author_match = 1 if norm_author and any(normalise_author(s) == norm_author for s in segments) else 0
    depth = len(segments)
    return (-is_root_loose, -placeholder_hits, author_match, depth, path)  # later in ranking is better

ranked = sorted(
    group.editions,
    key=lambda e: (score_edition(e), _tiebreak_key(e, source_dir)),
    reverse=True,
)
```

(`resolve_book_duplicates` will need to accept `source_dir` as a parameter; the caller in `cli.py` already has it.)

**Test coverage needed:** an addition to `tests/test_bookdedup.py` that constructs two `BookEdition` objects with identical `score_edition()` results and different `source_dir` values, then asserts the "better-organised" one wins. Cover all three bad-pick classes above.

**Verification after fix:** re-run the same Holly dry-run, confirm the Adrian Tchaikovsky / Sherlock Holmes / Andy Weir cases all flip their KEEP/QUARANTINE decisions, and that the count of groups reporting `Reason: higher overall score` drops significantly (a properly-working tiebreaker should only surface that reason when *all* structural signals are also tied).

---

### 13. Bitrate reason line emits nonsense "`62kbps vs 62kbps`" when values differ below kbps precision

**Severity:** low. Cosmetic log noise, not a correctness bug.

**Affected code:** [absorg/bookdedup.py:258-259](absorg/bookdedup.py#L258):

```python
if kept_score[2] > loser_score[2]:
    reasons.append(f"higher bitrate ({kept.avg_bitrate // 1000}kbps vs {loser.avg_bitrate // 1000}kbps)")
```

**Symptom from the dry run log:**

```text
1    Reason: higher bitrate (62kbps vs 62kbps)
```

The integer comparison `kept_score[2] > loser_score[2]` is on `avg_bitrate` which is already an int in bps (see [absorg/bookdedup.py:44](absorg/bookdedup.py#L44) and the computation at [absorg/bookdedup.py:197](absorg/bookdedup.py#L197): `avg_bitrate = total_bitrate // len(sub_files)`). The comparison is over true bps, but the format string uses `// 1000`, i.e. integer kbps, which **truncates sub-kbps differences**. So e.g. 62,800 bps vs 62,100 bps is a valid tiebreaker win (the first is higher) but both display as "62kbps".

The other suspicious entry `higher bitrate (114kbps vs 113kbps)` is actually legitimate and matches the integer display. Only `62 vs 62` is broken.

**Fix direction (two options, take either):**

1. **Display more precision.** Change the format to use one decimal: `f"{kept.avg_bitrate / 1000:.1f}kbps vs {loser.avg_bitrate / 1000:.1f}kbps"`. Produces `"62.8kbps vs 62.1kbps"`.

2. **Suppress the reason when the display rounds identically.** Guard the append:

```python
kept_kbps = kept.avg_bitrate // 1000
loser_kbps = loser.avg_bitrate // 1000
if kept_kbps != loser_kbps:
    reasons.append(f"higher bitrate ({kept_kbps}kbps vs {loser_kbps}kbps)")
```

Option 2 is cleaner because it avoids decimals in the log for the common case. With Issue 12 fixed, sub-kbps tiebreakers will be invisible to the user anyway (the structural tiebreak will dominate), so Option 2 is the preferred fix.

**Test coverage needed:** a unit test with two editions whose `avg_bitrate` values differ by <1000 bps, asserting that the reason string does **not** contain "higher bitrate" under Option 2, or that it contains a decimal under Option 1.

**Verification after fix:** grep the next dry-run log for `higher bitrate \(\d+kbps vs \1kbps\)` — zero matches expected.

---

## Notes on moot issues

These were observed during the audit but do not need fixing because they have been resolved by other commits in this task or because the affected file no longer exists.

- The "16 remaining ruff lint issues" list that used to live in `updates.md` is obsolete — those were all cleared in the `Clear ruff SIM/B007 lint debt` commit on this branch.
- `updates.md` itself had MD009 trailing-whitespace on L8 (and possibly other markdownlint findings). The file was deleted in the `Remove unused PyInstaller artifacts and stale changelog` commit, so its lint state is no longer relevant.
- `absorg-linux` (8.4 MB PyInstaller binary) and `Dockerfile.pyinstaller` were both deleted in the same cleanup commit. Any references to PyInstaller as the build path in older session memory should be ignored.
