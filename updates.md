# Absorg Updates — April 8, 2026

## Completed: Part B — Project-Wide Lint Setup

### Overview
Established project-wide linting standards for both Python and Markdown. Configured ruff for Python linting and markdownlint for markdown style consistency. Applied auto-fixes to resolve import sorting, unused imports, and whitespace issues.

**Commit:** `e48a2ad`  
**Branch:** main

### Changes Implemented

#### 1. Markdown Lint Configuration (`.markdownlint.json`)
Created new configuration file with project's de facto style:
- **MD060**: Compact table separators (`|---|---|` instead of `| --- |`)
- **MD050**: Asterisk bold (`**bold**` instead of `__bold__`)
- **Disabled**:
  - MD013 (line-length) — many code blocks and URLs exceed reasonable limits
  - MD033 (inline HTML) — CLAUDE.md uses HTML comments
  - MD041 (first-line heading) — flow diagrams placed at top without heading

#### 2. Python Lint Configuration (pyproject.toml)

Added comprehensive ruff configuration:
```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "ruff>=0.5"]

[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["B018"]
```

**Rule sets enabled:**
- E — pycodestyle errors
- F — Pyflakes (undefined names, unused imports)
- W — pycodestyle warnings
- I — isort (import sorting)
- UP — pyupgrade (Python version upgrades)
- B — flake8-bugbear (common bugs)
- SIM — flake8-simplify (code simplification suggestions)

#### 3. Auto-fixes Applied
**36 issues auto-fixed:**
- Import sorting and formatting (I001) — 6 files
- Unused imports (F401) — 5 files
  - `absorg.audioinfo.format_quality` (bookdedup.py)
  - `absorg.bookdedup.BookEdition` (cli.py)
  - `struct` (conftest.py)
  - `mutagen.id3.ID3` (conftest.py)
  - `os`, `pytest` (test_audioinfo.py)
  - `pytest` (test_bookdedup.py)
  - `absorg.cli.Counters` (test_cli.py)
- F-string without placeholders (F541) — 2 files
- Blank line whitespace (W293) — 4 instances in normalise.py
- Inner imports inside function scope — reorganized in conftest.py and test_cli.py

#### 4. Documentation Updates (CLAUDE.md)

**Commands section** — Added lint operations:
```bash
# Install dev deps (ruff + pytest)
pip install -e ".[dev]"

# Lint Python
ruff check absorg/ tests/

# Auto-fix Python lint
ruff check --fix absorg/ tests/
```

**Key Design Decisions** — Added new "Linting" section:
> The project uses ruff for Python linting (configured in pyproject.toml) and markdownlint for markdown style (configured in .markdownlint.json). The ruff configuration pins line-length to 120, targets Python 3.11+, and selects rules for error checking, formatting, and code simplification. Markdownlint enforces compact table separators and asterisk bold, matching the existing de facto project style.

### Remaining Lint Issues

**16 non-autofixable issues** (code style suggestions for future enhancement):
- **SIM113** (1) — Use `enumerate()` for index tracking (bookdedup.py:114)
- **SIM102** (1) — Combine nested if statements (cli.py:287)
- **SIM105** (2) — Use `contextlib.suppress()` (cover.py:38, dedup.py:127)
- **SIM108** (1) — Use ternary operator (pathbuilder.py:118)
- **B007** (10) — Rename unused loop variables `dp`/`dn` to `_dp`/`_dn` (test_cli.py — 4 locations)

**Note:** These are code quality suggestions, not errors. They can be addressed in follow-up commits without impact to functionality.

### Quality Assurance

✅ **All tests pass:** 175/175  
✅ **No test breakage:** All fixes are style-only  
✅ **No functionality changes:** Linting only addresses import organization, unused imports, and whitespace  
✅ **Markdown**: Plan file and CLAUDE.md comply with new config  

### Files Modified

| File | Type | Changes |
|---|---|---|
| `.markdownlint.json` | new | Markdown lint configuration |
| `pyproject.toml` | modified | Ruff config + dev dependencies |
| `CLAUDE.md` | modified | Lint commands + Linting section |
| `absorg/audioinfo.py` | modified | Import sorting |
| `absorg/bookdedup.py` | modified | Import sorting, unused import removal |
| `absorg/cli.py` | modified | Import sorting, unused import removal |
| `absorg/logger.py` | modified | Import sorting |
| `absorg/metadata.py` | modified | Import sorting |
| `absorg/normalise.py` | modified | Whitespace cleanup |
| `tests/conftest.py` | modified | Import sorting, unused import removal |
| `tests/test_audioinfo.py` | modified | Import sorting, unused import removal |
| `tests/test_bookdedup.py` | modified | Import sorting, unused import removal |
| `tests/test_cli.py` | modified | Import sorting, unused import removal |
| `tests/test_cover.py` | modified | Import sorting |
| `tests/test_dedup.py` | modified | Import sorting |
| `tests/test_metadata.py` | modified | Import sorting |
| `tests/test_normalise.py` | modified | Import sorting |
| `tests/test_pathbuilder.py` | modified | Import sorting |

**Total:** 18 files modified/created

### Git History

```
e48a2ad (HEAD -> main, origin/main) Part B: Project-wide lint setup (ruff + markdownlint)
28c1fe0 Update CLAUDE.md: document book normalisation volume marker preservation
82332fa Fix book-dedup normalizer to preserve series/volume markers
0ae869f (tag: v2.3.0) Version bump: 2.2.0 → 2.3.0
```

All changes pushed to `origin/main` ✓

## Next Steps: Part A — Fix Book-Dedup Series-Container False Matches

The plan file (`delegated-wiggling-ladybug.md` lines 1–193) outlines the book-dedup bug fix:

**Problem:** Directory-level edition grouping causes series containers (e.g., trilogy directories with Book 1, Book 2, Book 3) to be treated as a single edition and mismatched against standalone copies, leading to incorrect quarantines.

**Solution:** Within each directory, sub-group files by per-file normalised `(author, book)` key so that multi-book containers produce one edition per distinct book.

**Scope:**
- Modify `bookdedup.py` (L140–186): Rewrite edition-building with sub-grouping
- Modify `bookdedup.py` (L202–253): Change `resolve_book_duplicates()` to return `quarantine_files` instead of `quarantine_dirs`
- Modify `cli.py` (L354–358): Update per-file quarantine check to use file paths
- Update `tests/test_bookdedup.py`: Adjust test assertions and add new test for multi-book containers
- Bump version: `2.3.0` → `2.3.1` (pyproject.toml, __init__.py)
- Update `CLAUDE.md`: Fix flow diagram and add note about sub-grouping

---

## Summary

**Part B Status:** ✅ Complete  
**Part A Status:** ⏳ Ready to implement  
**Overall Progress:** 2 of 3 planned tasks complete (Part A pending)

The linting infrastructure is now in place to catch style drift on future contributions. All existing code has been auto-formatted and the project is ready for Part A implementation.
