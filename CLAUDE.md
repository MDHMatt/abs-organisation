# CLAUDE.md — AI Assistant Guide for abs-organisation

## Repository Overview

This repository contains **absorg.sh**, a single-file Bash utility that organises audiobook libraries for [Audiobookshelf](https://www.audiobookshelf.org/). It reads embedded metadata tags from audio files using `ffprobe`, then moves (or dry-runs the move of) each file into a structured hierarchy under a destination directory. It also extracts cover art and deduplicates files.

The entire project is four files:

```
absorg.sh            # Main script (~1,238 lines of Bash)
Dockerfile           # Alpine 3.19 container image
docker-compose.yml   # Compose config for Unraid NAS setups
LICENSE              # Unlicense (public domain)
```

---

## Technology Stack

| Layer | Tool |
|---|---|
| Language | Bash 4+ |
| Container base | Alpine Linux 3.19 |
| Metadata reading | `ffprobe` (ffmpeg suite) — **mandatory** |
| Cover extraction | `ffmpeg` — optional (disabled at runtime if absent) |
| File fingerprinting | `md5sum` + `stat` — **mandatory** |
| Orchestration | Docker / Docker Compose |
| Package manager | APK (Alpine, only inside the container) |

No npm, pip, Go modules, or other language toolchains are used.

---

## How the Script Works

### Execution Flow

```
main()
  └─ parse_args
  └─ check_deps          (ffprobe, md5sum; optional ffmpeg)
  └─ find audio files    (find -print0, null-delimited)
       └─ process_file() per file
            ├─ load_tags()          → ffprobe JSON → associative array
            ├─ resolve_metadata()   → 11 fields with fallback chain
            ├─ infer_from_path()    → directory-name fallback
            ├─ infer_from_filename()→ filename-pattern fallback
            ├─ build_dest()         → computes target path
            ├─ check_dedup()        → fingerprint → quarantine or conflict-rename
            ├─ extract_cover()      → writes cover.jpg (if enabled)
            └─ move/dry-run         → mv or log only
  └─ print summary
```

### Metadata Resolution Priority

For each field, the first non-empty tag wins:

| Field | Tag priority (highest → lowest) |
|---|---|
| Author | `album_artist` › `artist` › `composer` › `narrator` › `sort_artist` |
| Book | `album` › `work` › `tvshow` |
| Track title | `title` |
| Track number | `track` › `TRCK` › `trkn` |
| Disc number | `disc` › `TPOS` › `disk` › `disknumber` |
| Series | `TXXX:SERIES` › `grouping` › `TIT1` › `work` |
| Series index | `TXXX:SERIES-PART` › `movementnumber` › `©mvi` |
| Narrator | `narrator` › `TXXX:NARRATOR` |
| Year | `date` › `TDRC` › `year` › `©day` › `TYER` |
| Subtitle | `subtitle` › `TXXX:SUBTITLE` › `TIT3` |
| Genre | `genre` › `TCON` › `©gen` |

If tags are absent, `infer_from_path()` tries to derive author/book from the directory structure, then `infer_from_filename()` tries filename patterns. Ultimate fallback: `_Unknown Author` / `_Unknown Book`.

### Output Directory Structure

```
DEST/
├── Author Name/
│   ├── Series Name/
│   │   ├── 01 - Book Title/
│   │   │   ├── 01 - Chapter Title.m4b
│   │   │   └── cover.jpg
│   │   └── 02 - Another Book/
│   └── Standalone Book/
│       ├── 01 - Chapter.mp3
│       └── cover.jpg
└── _Unknown Author/
    └── _Unknown Book/
        └── file.mp3
```

### Deduplication

Each file gets a fingerprint: `SIZE:MD5(first 1MB)`.

- **Duplicate** (same fingerprint, same destination): quarantined to `DUPES_DIR`.
- **Conflict** (different fingerprint, same destination path): destination renamed with `.2`, `.3`, … suffix.
- **Already-organised** (file already at computed destination from a prior run): same dedup logic applies; idempotent runs are safe.

Tracking is done in an in-memory associative array `SEEN_DESTS` for the current run.

### String Sanitisation

`sanitise()` replaces characters that are illegal on common filesystems with Unicode lookalikes so paths remain human-readable:

| Illegal char | Replacement |
|---|---|
| `/` | `∕` (U+2215) |
| `:` | `∶` (U+2236) |
| `*` | `∗` (U+2217) |
| `?` | `？` (U+FF1F) |
| `"` | `＂` (U+FF02) |
| `<` | `＜` (U+FF1C) |
| `>` | `＞` (U+FF1E) |
| `\|` | `｜` (U+FF5C) |
| `\` | `﹨` (U+FE68) |

Path components are capped at 180 characters. Leading dots are stripped to prevent hidden directories.

---

## Running the Script

### Dry-run (default — safe, no files moved)

```bash
# Locally
bash absorg.sh --source /path/to/unsorted --dest /path/to/library

# Docker
docker build -t absorg .
docker run --rm -v /audiobooks:/audiobooks absorg

# Compose
docker-compose run --rm absorg
```

### Apply changes

```bash
bash absorg.sh --source /path/to/unsorted --dest /path/to/library --move

docker run --rm -v /audiobooks:/audiobooks absorg --move

docker-compose run --rm absorg --move
```

### All CLI flags

| Flag | Default | Description |
|---|---|---|
| `--move` | off | Actually move files (default is dry-run) |
| `--source DIR` | `/audiobooks_unsorted` | Directory to scan recursively |
| `--dest DIR` | `/audiobooks` | Library root to organise into |
| `--dupes DIR` | `./audiobook_dupes` | Where to quarantine duplicate files |
| `--log FILE` | `./abs_organise.log` | Append-only log file path |
| `--no-cover` | off | Skip cover art extraction |
| `--help` | — | Print usage and exit |

---

## Code Conventions

### Bash Version Requirement

The script requires **Bash 4+** for:
- `declare -A` associative arrays (`SEEN_DESTS`)
- `${var,,}` lowercase expansion
- `<<<` here-strings

Do not use Bash 3 syntax or `/bin/sh` features.

### Error Handling

```bash
set -uo pipefail   # Enabled at top of script
# -e is intentionally OMITTED — many operations legitimately return non-zero
```

- Use `|| true` for expected non-zero exits (e.g. `grep` finding no match, `ffprobe` on a corrupt file).
- Use `(( var++ )) || true` for counter increments to avoid exit-on-zero-expression.
- Validate explicitly with `[[ -f "$file" ]]` etc. rather than relying on errexit.

### Logging

All output goes to both stdout and the log file via a `tee -a "$LOG_FILE"` pipeline established in `main()`. Use the colour helpers:

| Function | Colour | Use for |
|---|---|---|
| `log` | default | General info |
| `logr` | red | Errors |
| `logy` | yellow | Warnings / dry-run notes |
| `logg` | green | Success / files moved |
| `logc` | cyan | File paths being processed |
| `logm` | magenta | Deduplication events |
| `logd` | dim | Verbose/debug detail |

ANSI codes are only emitted when stdout is a TTY; they are absent in log files.

### Function Conventions

- Every major operation is its own function (see execution flow above).
- Local variables inside functions use `local` declarations.
- Functions that return values do so by setting a global like `DEST_PATH` or by echoing to a subshell.
- Null-safe file iteration: `find … -print0 | while IFS= read -r -d '' file; do … done`.

### Supported Audio Extensions

```
mp3 m4a m4b m4p flac ogg opus aac wav wma mp4 aiff ape
```

These are defined in `AUDIO_EXTENSIONS` array at the top of the script.

---

## Modifying the Script

### Adding a New Metadata Field

1. Add a new `get_tag` call inside `resolve_metadata()` with the tag priority list.
2. Add the field to `build_dest()` if it should affect the output path.
3. Update the sanitisation call if the field is used in a path component.

### Adding a New Audio Extension

Add the extension (lowercase, no dot) to `AUDIO_EXTENSIONS` near the top of `absorg.sh`.

### Changing the Output Path Format

All path-building logic lives in `build_dest()` (around line 747). The format is:

```
DEST / Author / [Series / ##-]Book / [DD-]TT - Title.ext
```

Edit `build_dest()` to change the hierarchy or naming pattern.

### Changing Deduplication Behaviour

Dedup logic is in `fingerprint()`, `check_dedup()`, and `quarantine()` (lines 346–1040). The fingerprint is `SIZE:MD5(first 1MB)`. Changing to a full-file checksum would make the script significantly slower on large collections but more accurate.

---

## Docker / Compose Notes

- The Dockerfile uses a **single RUN layer** to minimise image size.
- The default `CMD` is a dry-run: `--source /audiobooks --dest /audiobooks`. Override at runtime.
- `docker-compose.yml` includes an `x-audiobook-paths` YAML anchor at the top — edit the two path values there to match your Unraid share paths before running.
- The container is designed as a **one-shot tool** (restart policy: `no`), not a long-running service.

---

## Development Workflow

There is no build step, test suite, or CI pipeline. The workflow is:

1. Edit `absorg.sh` directly.
2. Run a dry-run against a test audiobook directory to verify output.
3. Inspect the log file and stdout for any unexpected warnings.
4. When satisfied, run with `--move` to apply.

### Suggested Manual Test Sequence

```bash
# 1. Dry-run only
bash absorg.sh --source ./test-books --dest ./output --log ./test.log

# 2. Review the log
cat ./test.log

# 3. Apply if log looks correct
bash absorg.sh --source ./test-books --dest ./output --log ./test.log --move

# 4. Verify directory tree
find ./output -type f | sort
```

---

## Key Files Reference

| File | Lines | Purpose |
|---|---|---|
| `absorg.sh:1–81` | Script header | Usage docs, option descriptions |
| `absorg.sh:95–113` | ANSI colours | TTY-conditional colour codes |
| `absorg.sh:119–143` | Defaults | Source/dest paths, flags, extensions |
| `absorg.sh:185–224` | Arg parsing | `--move`, `--source`, etc. |
| `absorg.sh:230–257` | Log helpers | `log`, `logr`, `logy`, `logg`, `logc`, `logm`, `logd` |
| `absorg.sh:286–340` | String helpers | `sanitise()`, `parse_int()` |
| `absorg.sh:346–396` | Fingerprinting | `fingerprint()` — dedup hash |
| `absorg.sh:402–604` | Metadata | `load_tags()`, `get_tag()`, `resolve_metadata()` |
| `absorg.sh:610–689` | Path inference | `infer_from_path()`, `infer_from_filename()` |
| `absorg.sh:695–741` | Cover art | `extract_cover()` |
| `absorg.sh:747–863` | Path building | `build_dest()` |
| `absorg.sh:869–1040` | Dedup logic | `quarantine()`, `find_free_dest()`, `check_dedup()` |
| `absorg.sh:1048–1141` | File processing | `process_file()` — main per-file orchestrator |
| `absorg.sh:1149–1237` | Entry point | `main()` — discovery loop, summary |
| `Dockerfile` | — | Alpine 3.19 image; installs all deps |
| `docker-compose.yml` | — | Volume paths for Unraid; override CMD for `--move` |
