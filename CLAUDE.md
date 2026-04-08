# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

**absorg** is a Python package that organises audiobook libraries for [Audiobookshelf](https://www.audiobookshelf.org/). It reads embedded metadata tags from audio files using `mutagen`, then moves (or dry-runs the move of) each file into a structured hierarchy under a destination directory. It also extracts cover art and deduplicates files.

## Technology Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Metadata / cover art | [mutagen](https://mutagen.readthedocs.io/) (no ffmpeg needed) |
| Container base | python:3.12-alpine |
| Orchestration | Docker / Docker Compose (optional) |
| Testing | pytest |

## Commands

```bash
# Install (editable, with test deps)
pip install -e ".[test]"

# Dry-run (default — no files moved)
absorg --source /path/to/unsorted --dest /path/to/library

# Apply changes
absorg --source /path/to/unsorted --dest /path/to/library --move

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_sanitise.py -v

# Run a single test
pytest tests/test_pathbuilder.py::TestBuildDest::test_basic_author_book -v

# Docker
docker-compose run --rm absorg              # dry run
docker-compose run --rm absorg --move       # apply
```

## CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--move` | off | Actually move files (default is dry-run) |
| `--source DIR` | `/audiobooks_unsorted` | Directory to scan recursively |
| `--dest DIR` | `/audiobooks` | Library root to organise into |
| `--dupes DIR` | `./audiobook_dupes` | Where to quarantine duplicate files |
| `--log FILE` | `./abs_organise.log` | Log file path (truncated each run) |
| `--no-cover` | off | Skip cover art extraction |
| `--book-dedup` | off | Book-level dedup: prefer M4B, prefer newer recordings |
| `--show-quality` | off | Log audio quality info (bitrate, codec, duration) per file |
| `--workers N` | 0 (auto) | Parallel I/O workers (0 = auto-detect from CPU count, max 16) |

## Project Structure

```
absorg/
  __init__.py          # Package version
  __main__.py          # python -m absorg entry point
  cli.py               # Arg parsing, main() orchestration, summary
  metadata.py          # mutagen tag extraction, resolve_metadata()
  audioinfo.py         # Audio stream info (bitrate, codec, duration) via mutagen
  normalise.py         # Author/book name normalisation for book-level dedup
  bookdedup.py         # Book-level dedup: inventory, scoring, resolution
  inference.py         # infer_from_path(), infer_from_filename()
  pathbuilder.py       # sanitise(), parse_int(), build_dest()
  dedup.py             # fingerprint(), DedupTracker, quarantine()
  cover.py             # extract_cover() via mutagen
  logger.py            # Colored TTY logging with file tee
  constants.py         # Extensions, unknown fallbacks, sanitisation map, tag chains, format prefs
tests/
  conftest.py          # Shared fixtures (make_mp3, logger)
  test_sanitise.py     # sanitise() and parse_int()
  test_pathbuilder.py  # build_dest() path construction
  test_inference.py    # Path and filename inference
  test_metadata.py     # Tag loading and resolution
  test_audioinfo.py    # Audio stream info extraction
  test_normalise.py    # Author/book name normalisation
  test_bookdedup.py    # Book-level dedup scoring and grouping
  test_dedup.py        # Fingerprinting and collision detection
  test_cover.py        # Cover art extraction
  test_cli.py          # CLI args, file discovery, end-to-end, book-dedup integration
```

## Execution Flow

```
main()
  ├─ parse_args()
  ├─ AbsorgLogger(log_path)
  ├─ _discover_audio_files()     → os.walk + extension filter
  ├─ precompute_fingerprints()   → ThreadPoolExecutor (--workers) for dedup cache
  │
  ├─ if --book-dedup:            → TWO-PASS MODE
  │    ├─ build_book_inventory() → ThreadPoolExecutor: parallel metadata + audio info
  │    │                           group editions by normalised (author, book) key
  │    ├─ resolve_book_duplicates() → score editions, keep best, quarantine rest
  │    │                              scoring: M4B > MP3 → newer year → higher bitrate
  │    └─ _log_book_dedup_decisions()
  │
  └─ per file:
       ├─ if in quarantine_dirs → quarantine(BOOK_DEDUP) + skip
       ├─ resolve_metadata()     → mutagen tags → MetadataResult (cached if book-dedup)
       ├─ infer_from_path()      → directory-name fallback
       ├─ infer_from_filename()  → filename-pattern fallback
       ├─ build_dest()           → computes target path + sanitises
       ├─ tracker.check()        → fingerprint → file-level dedup decision
       ├─ tracker.register()     → BEFORE dry-run guard (critical)
       ├─ move / dry-run         → shutil.move or log only
       └─ extract_cover()        → writes cover.jpg (live moves only)
```

## Key Design Decisions

### Metadata Resolution

Each field is resolved by trying a tag priority chain (defined in `constants.METADATA_TAG_CHAINS`). Mutagen uses different APIs per format, so `metadata.py` has format-specific normalisers (`_normalise_id3`, `_normalise_mp4`, `_normalise_vorbis`, `_normalise_asf`) that flatten everything to a `dict[str, str]` with lowercase keys. The `get_tag()` function walks the chain and returns the first non-empty value.

### Dedup Tracking

**File-level dedup** (`dedup.py`): `DedupTracker.register()` must be called **before** the dry-run guard so that later files see claimed destinations even when no files are actually moved. This is critical for correct dedup in dry-run mode. The `no_meta` counter is only incremented on live moves.

**Book-level dedup** (`bookdedup.py`): Enabled with `--book-dedup`. Uses a two-pass architecture:
- Pass 1: Inventories all files, extracts metadata + audio info (`AudioInfo`), groups files into editions by directory, then groups editions by normalised `(author, book)` key using `normalise.py`.
- Pass 2: Scores editions (format preference M4B>MP3, newer year, higher bitrate, longer duration) and quarantines inferior editions before the normal per-file pipeline runs.
- Book-dedup and file-level dedup are complementary: book-dedup removes inferior editions first, then file-level dedup catches identical content within remaining files.

### Author/Book Name Normalisation

`normalise.py` produces canonical grouping keys for dedup. 

**Author normalisation** handles: case folding, accent stripping (NFKD + transliteration), separator variants (`;` → `,`), name ordering (sorted), role qualifier removal (`- introductions`, `- translator`, etc.).

**Book normalisation** handles: case folding, Audible ID stripping, subtitle removal, leading article removal, and **crucially, preserves volume/series markers** (Series, Part, Act, Volume, Book, etc.) that distinguish different works. For example:
- "Alan Partridge Series 1" and "Alan Partridge Series 2" normalize to different keys
- "Skulduggery Pleasant Books 1-3" and "Books 4-6" are kept distinct
- "The Sandman Act I" and "Act II" remain separate
- Extracting markers from mixed subtitle text: "Good Omens: The Nice and Accurate Prophecies Series 1" → "good omens series 1"

This prevents incorrectly grouping different seasons, trilogies, or volumes as duplicates during book-level dedup.

### Parallel Processing

`--workers N` controls I/O parallelism (default: auto-detect via `os.cpu_count()`, capped at 16). Two operations run in parallel via `ThreadPoolExecutor`:

1. **Fingerprint pre-computation** (`dedup.py`): All source files fingerprinted before the per-file loop. `DedupTracker` uses a cache with on-demand fallback for destination files not in the pre-computed set.
2. **Metadata extraction** (`bookdedup.py`): When `--book-dedup` is enabled, `build_book_inventory()` extracts metadata + audio info for all files in parallel before grouping into editions.

Both are I/O-bound (NAS reads), so threads are correct despite the GIL. The per-file processing loop remains sequential due to `DedupTracker` ordering dependencies.

### String Sanitisation

`sanitise()` replaces filesystem-illegal characters with Unicode lookalikes (defined in `constants.SANITISE_MAP`). Only the first leading dot is stripped (not `lstrip('.')`). Components are capped at 180 characters.

| Char | Replacement | Codepoint |
|---|---|---|
| `/` `\` | `∕` | U+2215 |
| `:` | `∶` | U+2236 |
| `*` | `∗` | U+2217 |
| `?` `"` | removed | — |
| `<` | `‹` | U+2039 |
| `>` | `›` | U+203A |
| `\|` | `│` | U+2502 |
| TAB | space | — |

### Output Directory Structure

```
DEST/Author/[Series/[NN - ]]Book/[DD-TNN - ]Chapter.ext
```

- `.m4b` files use book title as filename (not chapter title)
- Multi-disc (disc > 1): `D02-T03 - Title.ext`
- Single-disc with track: `03 - Title.ext`
- Extension always lowercased

### Windows Compatibility

- `os.path.normpath()` for all path comparisons
- `os.path.join()` for path construction (never hardcode `/`)
- Logger handles `UnicodeEncodeError` for cp1252 console output

## Testing

Tests use a `make_mp3` fixture (in `conftest.py`) that creates minimal valid MP3 files with proper MPEG frames and optional ID3 tags via mutagen. The fixture writes 5 valid MPEG1 Layer3 frames (128kbps/44100Hz) so mutagen can sync.

Audio extensions supported: mp3, m4a, m4b, m4p, flac, ogg, opus, aac, wav, wma, mp4, aiff, ape.
