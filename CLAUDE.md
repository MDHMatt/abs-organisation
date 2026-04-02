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

## Project Structure

```
absorg/
  __init__.py          # Package version
  __main__.py          # python -m absorg entry point
  cli.py               # Arg parsing, main() orchestration, summary
  metadata.py          # mutagen tag extraction, resolve_metadata()
  inference.py         # infer_from_path(), infer_from_filename()
  pathbuilder.py       # sanitise(), parse_int(), build_dest()
  dedup.py             # fingerprint(), DedupTracker, quarantine()
  cover.py             # extract_cover() via mutagen
  logger.py            # Colored TTY logging with file tee
  constants.py         # Extensions, unknown fallbacks, sanitisation map, tag chains
tests/
  conftest.py          # Shared fixtures (make_mp3, logger)
  test_sanitise.py     # sanitise() and parse_int()
  test_pathbuilder.py  # build_dest() path construction
  test_inference.py    # Path and filename inference
  test_metadata.py     # Tag loading and resolution
  test_dedup.py        # Fingerprinting and collision detection
  test_cover.py        # Cover art extraction
  test_cli.py          # CLI args, file discovery, end-to-end
```

## Execution Flow

```
main()
  ├─ parse_args()
  ├─ AbsorgLogger(log_path)
  ├─ _discover_audio_files()     → os.walk + extension filter
  └─ per file:
       ├─ resolve_metadata()     → mutagen tags → MetadataResult
       ├─ infer_from_path()      → directory-name fallback
       ├─ infer_from_filename()  → filename-pattern fallback
       ├─ build_dest()           → computes target path + sanitises
       ├─ tracker.check()        → fingerprint → dedup decision
       ├─ tracker.register()     → BEFORE dry-run guard (critical)
       ├─ move / dry-run         → shutil.move or log only
       └─ extract_cover()        → writes cover.jpg (live moves only)
```

## Key Design Decisions

### Metadata Resolution

Each field is resolved by trying a tag priority chain (defined in `constants.METADATA_TAG_CHAINS`). Mutagen uses different APIs per format, so `metadata.py` has format-specific normalisers (`_normalise_id3`, `_normalise_mp4`, `_normalise_vorbis`, `_normalise_asf`) that flatten everything to a `dict[str, str]` with lowercase keys. The `get_tag()` function walks the chain and returns the first non-empty value.

### Dedup Tracking

`DedupTracker.register()` must be called **before** the dry-run guard so that later files see claimed destinations even when no files are actually moved. This is critical for correct dedup in dry-run mode. The `no_meta` counter is only incremented on live moves.

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
