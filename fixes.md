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

## Notes on moot issues

These were observed during the audit but do not need fixing because they have been resolved by other commits in this task or because the affected file no longer exists.

- The "16 remaining ruff lint issues" list that used to live in `updates.md` is obsolete — those were all cleared in the `Clear ruff SIM/B007 lint debt` commit on this branch.
- `updates.md` itself had MD009 trailing-whitespace on L8 (and possibly other markdownlint findings). The file was deleted in the `Remove unused PyInstaller artifacts and stale changelog` commit, so its lint state is no longer relevant.
- `absorg-linux` (8.4 MB PyInstaller binary) and `Dockerfile.pyinstaller` were both deleted in the same cleanup commit. Any references to PyInstaller as the build path in older session memory should be ignored.
