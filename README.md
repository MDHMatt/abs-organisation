# absorg

Organise audiobook libraries for [Audiobookshelf](https://www.audiobookshelf.org/) by reading embedded metadata tags.

![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)
![Version](https://img.shields.io/badge/version-2.3.2-green)
![License](https://img.shields.io/badge/license-Unlicense-lightgrey)
![Docker](https://img.shields.io/badge/docker-mdhmatt%2Fabs--organiser-blue)

`absorg` walks a source directory of audio files, reads their embedded metadata with [mutagen](https://mutagen.readthedocs.io/), and lays each file out under a structured `Author/[Series/[NN - ]]Book/[DD-TNN - ]Chapter.ext` hierarchy ready for Audiobookshelf to ingest. It deduplicates by content fingerprint, optionally collapses duplicate editions of the same book, and extracts embedded cover art on the way through. Dry-run mode is the default — every command is safe to try before any files move.

## Features

- **Metadata-driven path building** — author, series, book, track, and disc tags drive the destination layout.
- **File-level dedup** — content fingerprints catch identical files across the source tree.
- **Book-level dedup** — opt in with `--book-dedup` to keep the best edition (M4B over MP3, newer over older, higher bitrate, longer duration) and quarantine the rest.
- **Cover art extraction** — drops `cover.jpg` next to each book on live moves.
- **Parallel I/O** — fingerprinting and metadata extraction run on a thread pool sized from your CPU count.
- **Dry-run by default** — pass `--move` to apply changes.
- **Docker-ready** — Alpine + pip image, plus a `docker-compose.yml` to wire up Unraid-style volume mounts.
- **Cross-platform** — Windows path handling, cp1252 console fallback, and case-insensitive extension matching.

## Quick start — native

```bash
pip install -e .

# Dry run (default — no files moved)
absorg --source /path/to/unsorted --dest /path/to/library

# Apply changes
absorg --source /path/to/unsorted --dest /path/to/library --move
```

## Quick start — Docker

```bash
docker run --rm \
  -v /mnt/user/Media/Music/Audiobooks2:/source \
  -v /mnt/user/Media/Music/Audiobooks:/dest \
  -v /mnt/user/appdata/absorg/logs:/logs \
  -v /mnt/user/appdata/absorg/dupes:/dupes \
  mdhmatt/abs-organiser \
  --source /source --dest /dest --dupes /dupes --log /logs/absorg.log
```

A ready-to-edit [docker-compose.yml](docker-compose.yml) is included. Update the four `volumes:` paths under `services.absorg` to match your shares, then:

```bash
docker-compose run --rm absorg              # dry run
docker-compose run --rm absorg --move       # apply
```

## CLI reference

| Flag | Default | Description |
| --- | --- | --- |
| `--move` | off | Actually move files (default is dry-run) |
| `--source DIR` | `/audiobooks_unsorted` | Directory to scan recursively |
| `--dest DIR` | `/audiobooks` | Library root to organise into |
| `--dupes DIR` | `./audiobook_dupes` | Where to quarantine duplicate files |
| `--log FILE` | `./abs_organise.log` | Log file path (truncated each run) |
| `--no-cover` | off | Skip cover art extraction |
| `--book-dedup` | off | Book-level dedup: prefer M4B, prefer newer recordings |
| `--show-quality` | off | Log audio quality info (bitrate, codec, duration) per file |
| `--workers N` | 0 (auto) | Parallel I/O workers (0 = auto-detect from CPU count, max 16) |

## Output layout

```text
LIBRARY/
  Terry Pratchett/
    Discworld/
      01 - The Colour of Magic/
        01 - Chapter 1.mp3
        02 - Chapter 2.mp3
        cover.jpg
      02 - The Light Fantastic/
        01 - Chapter 1.mp3
        cover.jpg
```

- Standalone books (no series tag) drop directly under the author folder.
- Multi-disc audiobooks use a `D02-T03 - Title.ext` track prefix.
- M4B files use the book title as the filename instead of a chapter title, since Audiobookshelf treats them as a single-file book.

## Book-level dedup

Enable with `--book-dedup` when consolidating libraries that may contain duplicate editions of the same book — typically MP3 rips alongside M4B re-encodes, or older recordings sitting next to newer ones. The resolver scores each edition with a tie-breaker chain: M4B beats MP3, newer year wins next, then higher average bitrate, then longer total duration. Inferior editions are moved to the `--dupes` directory rather than being deleted, so you can review them before throwing anything away.

Recommended first run:

```bash
absorg --book-dedup --show-quality --source /unsorted --dest /library
```

This is dry-run by default and surfaces the per-book scoring decisions in the log so you can sanity-check them before adding `--move`.

## Development

```bash
pip install -e ".[dev]"        # editable + ruff + pytest
pytest tests/ -v               # full test suite
ruff check absorg/ tests/      # lint
```

Tests use a `make_mp3` fixture that synthesises minimal valid MPEG1 Layer3 frames plus optional ID3 tags via mutagen, so the suite has no external media dependency.

## Project layout

```text
absorg/
  cli.py            # Argument parsing and main() orchestration
  metadata.py       # mutagen tag extraction and resolution
  audioinfo.py      # Bitrate, duration, codec extraction
  normalise.py      # Author/book name normalisation for book-level dedup
  bookdedup.py      # Book-level dedup: inventory, scoring, resolution
  inference.py      # Path/filename fallbacks when tags are empty
  pathbuilder.py    # Sanitisation and destination path construction
  dedup.py          # Fingerprinting, DedupTracker, quarantine
  cover.py          # Embedded cover art extraction
  logger.py         # Coloured TTY logging with file tee
  constants.py      # Extensions, tag chains, sanitise/transliterate maps
tests/              # pytest suite (177 tests, no external media required)
```

For architecture, metadata resolution chains, and design decisions, see [CLAUDE.md](CLAUDE.md).

## License

Released into the public domain under [The Unlicense](LICENSE). Do whatever you want with it.

## See also

- [CLAUDE.md](CLAUDE.md) — detailed architecture, metadata resolution chains, and design decisions
- [Audiobookshelf](https://www.audiobookshelf.org/) — the self-hosted audiobook server this tool feeds
- [mutagen](https://mutagen.readthedocs.io/) — the underlying tag-reading library
