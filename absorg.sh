#!/bin/bash

# =============================================================================

# Audiobookshelf Library Organiser — Robust Edition with Deduplication

# =============================================================================

# Scans a source directory for audio files, reads ALL embedded metadata in a

# single ffprobe call per file, moves them into Audiobookshelf’s recommended

# Author/[Series/]Book/ structure, and handles duplicates safely.

# 

# Run inside the ABS Docker container (ffprobe is already available there):

# 

# docker exec -it audiobookshelf bash

# bash /path/to/organise_audiobooks.sh             # dry run

# bash /path/to/organise_audiobooks.sh –move      # apply

# 

# OPTIONS:

# –move              Apply changes. Default is a safe dry run.

# –source DIR        Source of unorganised files  (default: /audiobooks_unsorted)

# –dest   DIR        Organised library root        (default: /audiobooks)

# –dupes  DIR        Where to move duplicate files (default: ./audiobook_dupes)

# –log    FILE       Log file path                 (default: ./abs_organise.log)

# –no-cover          Skip embedded cover art extraction

# –help              Show this message

# 

# DUPLICATE HANDLING:

# When two files resolve to the same destination, a fast fingerprint

# (file size + MD5 of first 1 MB) is used to classify the collision:

# 

# DUPLICATE  — fingerprints match: same content.

# The second file is moved to –dupes DIR for review.

# 

# CONFLICT   — fingerprints differ: different content, same destination name

# (e.g. two different editions of a book with identical tags).

# The second file is renamed with a numeric suffix (.2, .3 …)

# and placed in the destination alongside the first.

# 

# EXISTING   — destination already occupied from a previous run.

# Same fingerprint logic applies: quarantine or rename.

# 

# REQUIREMENTS: ffprobe, md5sum (both present in the ABS Docker image).

# ffmpeg is optional — only needed for cover art extraction.

# =============================================================================

# -u  : treat unset variables as errors — catches typos in variable names early.

# -o pipefail : a pipeline fails if any command in it fails, not just the last.

# NOTE: -e (exit on error) is deliberately omitted. Many commands here legitimately

# return non-zero (grep finding no match, ffprobe on a malformed file, etc.).

# We use explicit || true and conditional checks instead.

set -uo pipefail

# =============================================================================

# Colours

# =============================================================================

# Only emit ANSI escape codes when stdout is a real terminal.

# When the script is piped or redirected the codes would appear as literal

# garbage in the log file, so we fall back to empty strings.

if [[ -t 1 ]]; then
RED=’\033[0;31m’; YELLOW=’\033[1;33m’; GREEN=’\033[0;32m’
CYAN=’\033[0;36m’; BOLD=’\033[1m’; DIM=’\033[2m’; RESET=’\033[0m’
MAGENTA=’\033[0;35m’
else
RED=’’; YELLOW=’’; GREEN=’’; CYAN=’’; BOLD=’’; DIM=’’; RESET=’’; MAGENTA=’’
fi

# =============================================================================

# Configuration defaults

# =============================================================================

# These paths match the typical ABS Docker volume mount points.

# Override them at runtime with –source / –dest / –dupes / –log.

SOURCE_DIR=”/audiobooks_unsorted”
DEST_DIR=”/audiobooks”
DUPES_DIR=”./audiobook_dupes”
LOG_FILE=”./abs_organise.log”
DRY_RUN=true        # Safe by default — must explicitly pass –move to apply
EXTRACT_COVER=true  # Set to false via –no-cover, or automatically if ffmpeg absent

# Fallback folder names used when metadata AND path inference both fail.

# Leading underscore sorts them to the top in file managers for easy review.

UNKNOWN_AUTHOR=”_Unknown Author”
UNKNOWN_BOOK=”_Unknown Book”

# All container formats ffprobe supports that are used for audiobooks.

# mp4 is included because some tools export audiobooks as .mp4 with audio-only.

AUDIO_EXTENSIONS=(mp3 m4a m4b m4p flac ogg opus aac wav wma mp4 aiff ape)

# =============================================================================

# Run-time counters  (all initialised here so they’re always defined)

# =============================================================================

CNT_MOVED=0
CNT_SKIPPED=0
CNT_FAILED=0
CNT_NO_META=0    # Files moved using inferred metadata (no embedded tags)
CNT_COVER=0
CNT_DUPE=0       # Files quarantined as identical-content duplicates
CNT_CONFLICT=0   # Files renamed because different content mapped to the same path

# =============================================================================

# Dedup tracking

# =============================================================================

# Associative array: resolved destination path -> fingerprint of the first

# source file that claimed that destination during this run.

# 

# We store the PRE-COMPUTED FINGERPRINT rather than the source file path.

# Storing the path would be a bug: in live (–move) mode the source file is

# moved before a later duplicate might be checked against it, so the original

# path would no longer exist on disk.

declare -A SEEN_DESTS

# =============================================================================

# Argument parsing

# =============================================================================

usage() {

# Print the header comment block from this file, stripping the # prefix.

# Works as long as the script is invoked with a real path (e.g. bash script.sh).

# Will not work if the script is piped to bash via stdin.

grep ‘^#’ “$0” | grep -v ‘#!/’ | sed ‘s/^# {0,1}//’
exit 0
}

parse_args() {

# Use a while+shift loop rather than for-in so we can consume the next

# positional argument for options that take a value (e.g. –source /path).

while [[ $# -gt 0 ]]; do
case “$1” in
–move)      DRY_RUN=false ;;
–dry-run)   DRY_RUN=true ;;
–no-cover)  EXTRACT_COVER=false ;;
# Both “–source /path” and “–source=/path” forms are supported.
–source)    shift; SOURCE_DIR=”${1:?–source requires a path}” ;;
–source=*)  SOURCE_DIR=”${1#*=}” ;;
–dest)      shift; DEST_DIR=”${1:?–dest requires a path}” ;;
–dest=*)    DEST_DIR=”${1#*=}” ;;
–dupes)     shift; DUPES_DIR=”${1:?–dupes requires a path}” ;;
–dupes=*)   DUPES_DIR=”${1#*=}” ;;
–log)       shift; LOG_FILE=”${1:?–log requires a path}” ;;
–log=*)     LOG_FILE=”${1#*=}” ;;
–help|-h)   usage ;;
*) echo “Unknown option: $1”; usage ;;
esac
shift
done
}

# =============================================================================

# Logging helpers

# =============================================================================

# All output is written to both stdout and the log file via tee.

# printf ‘%b\n’ interprets backslash escapes (needed for ANSI codes) without

# the portability issues of ‘echo -e’.

_log() { printf ‘%b\n’ “$1” | tee -a “$LOG_FILE”; }
log()  { _log “$1”; }
logr() { _log “${RED}$1${RESET}”; }       # Red   — errors
logy() { _log “${YELLOW}$1${RESET}”; }    # Yellow — warnings
logg() { _log “${GREEN}$1${RESET}”; }     # Green  — success
logc() { _log “${CYAN}$1${RESET}”; }      # Cyan   — file being processed
logm() { _log “${MAGENTA}$1${RESET}”; }   # Magenta — dedup events
logd() { _log “${DIM}$1${RESET}”; }       # Dim    — skipped / low-priority

# Safe counter increment.

# Plain “(( CNT++ ))” is unsafe under “set -e” because arithmetic expressions

# that evaluate to zero return exit code 1, causing the script to abort when

# a counter transitions from 0 to 1. “|| true” suppresses that exit code.

# We use eval here so the function accepts the variable NAME as a string.

inc() { eval “(( $1++ ))” || true; }

# =============================================================================

# Dependency check

# =============================================================================

check_deps() {
local ok=true

# ffprobe is mandatory — used for all metadata extraction

command -v ffprobe &>/dev/null || { logr “ERROR: ffprobe not found. Run inside the ABS Docker container.”; ok=false; }

# md5sum is mandatory — used by the fingerprint function for dedup

command -v md5sum  &>/dev/null || { logr “ERROR: md5sum not found.”; ok=false; }

# ffmpeg is optional — only needed for cover art extraction

command -v ffmpeg  &>/dev/null || { logy “WARNING: ffmpeg not found — cover extraction disabled.”; EXTRACT_COVER=false; }
$ok || exit 1
}

# =============================================================================

# String helpers

# =============================================================================

# sanitise STRING

# Makes a string safe to use as a filesystem path component by replacing

# characters that are illegal or problematic on Linux, macOS, or Windows

# (the latter matters if the NAS share is ever accessed via SMB).

# 

# We substitute visually similar Unicode characters rather than deleting them

# outright, so the folder names remain readable. E.g. “Author: A Story” becomes

# “Author∶ A Story” rather than “Author A Story”.

sanitise() {
local s=”$1”
s=”${s////∕}”    # U+2215 DIVISION SLASH  — looks like / but isn’t a path sep
s=”${s//\/∕}”    # Backslash — same replacement
s=”${s//:/∶}”     # U+2236 RATIO           — looks like a colon
s=”${s//*/∗}”    # U+2217 ASTERISK OPERATOR
s=”${s//?/}”     # Question mark — no good substitute, just remove
s=”${s//"/}”     # Double quote  — no good substitute, just remove
s=”${s//</‹}”     # U+2039 SINGLE LEFT ANGLE QUOTATION MARK
s=”${s//>/›}”     # U+203A SINGLE RIGHT ANGLE QUOTATION MARK
s=”${s//|/│}”     # U+2502 BOX DRAWINGS LIGHT VERTICAL
s=”${s//	/ }”    # Literal TAB character (not a space) — replace with space

# Collapse runs of spaces and strip leading/trailing whitespace

s=$(printf ‘%s’ “$s” | tr -s ’ ’ | sed ‘s/^[[:space:]]*//;s/[[:space:]]*$//’)

# Strip leading dots — prevents creating hidden directories (e.g. “.hidden/”)

s=”${s#.}”

# 180-char limit keeps paths well under the 255-byte filename limit even

# with multi-byte UTF-8 characters, and leaves room for parent path segments.

printf ‘%s’ “${s:0:180}”
}

# parse_int STRING

# Extracts the leading integer from strings like “3”, “03”, or “3/12”.

# The “N/Total” format is used by many taggers for track and disc numbers.

# Returns an empty string if no leading integer is found.

parse_int() { printf ‘%s’ “$1” | grep -o ‘^[0-9]*’ | head -1; }

# =============================================================================

# Fast file fingerprint

# =============================================================================

# fingerprint FILE

# Outputs a string of the form “SIZE:MD5_OF_FIRST_1MB”.

# 

# Why not a full MD5? A 10 GB m4b file takes ~30 s to checksum fully.

# The first megabyte contains the container header and the start of the audio

# stream — more than enough entropy to distinguish genuinely different files.

# The file size is included as a first-pass discriminator: two files of

# different sizes are always different, avoiding the md5 call entirely in the

# common case (which is checked by the caller comparing fingerprint strings).

# 

# Why not just size? Two different books could theoretically have the same byte

# count, especially with padding or fixed-bitrate encodings.

# 

# Collision probability for real-world audio files: astronomically low.

fingerprint() {
local file=”$1”
local size

# stat -c%s is the GNU coreutils form; -f%z is the BSD/macOS form.

# The ABS container (Alpine/Debian) uses GNU, but the fallback keeps this

# portable in case the script is ever run outside Docker.

size=$(stat -c%s “$file” 2>/dev/null || stat -f%z “$file” 2>/dev/null || echo “0”)

# dd reads exactly 1 MB (or the whole file if smaller) and pipes to md5sum.

# stderr is suppressed to hide dd’s progress output.

local partial_md5
partial_md5=$(dd if=”$file” bs=1M count=1 2>/dev/null | md5sum | cut -d’ ’ -f1)

printf ‘%s:%s’ “$size” “$partial_md5”
}

# =============================================================================

# Metadata extraction

# =============================================================================

# Global cache for the raw tag dump of the current file.

# load_tags() writes this once per file; get_tag() reads it multiple times.

# Keeping it global avoids passing a potentially large string as a function

# argument, and sidesteps subshell isolation issues with local variables.

FILE_TAGS=””

# load_tags FILE

# Populates $FILE_TAGS with all format-level and stream-level tags from FILE

# in a single ffprobe invocation.

# 

# We request both format_tags (container-level, e.g. ID3 in MP3) and

# stream_tags (per-stream, e.g. some encoders write tags to the audio stream

# rather than the container). Output format is one “TAG:key=value” line each.

load_tags() {
FILE_TAGS=$(ffprobe -v quiet   
-show_entries “format_tags:stream_tags”   
-of default=noprint_wrappers=1   
“$1” 2>/dev/null || true)
}

# get_tag KEY [KEY2 KEY3 …]

# Searches $FILE_TAGS case-insensitively for the first non-empty value matching

# any of the supplied key names. Returns the value via stdout.

# 

# Multiple keys are tried in order to handle the many competing tag conventions

# across formats (ID3v2, iTunes atoms, MusicBrainz TXXX frames, etc.).

# Returns an empty string (exit 0) if no key is found — not an error.

get_tag() {
local key val
for key in “$@”; do
# “<<< $FILE_TAGS” avoids a subshell (unlike echo “$FILE_TAGS” | grep).
# cut -d= -f2- preserves values that themselves contain ‘=’ signs.
val=$(grep -i “^TAG:${key}=” <<< “$FILE_TAGS” | head -1 | cut -d= -f2-)
[[ -n “$val” ]] && { printf ‘%s’ “$val”; return 0; }
done
return 0
}

# resolve_metadata FILE

# Calls load_tags once, then extracts all relevant fields into META_* globals.

# 

# OUTPUTS (global variables set by this function):

# META_AUTHOR       — book author / album artist

# META_BOOK         — book / album title

# META_TITLE        — chapter / track title

# META_TRACK        — track number (integer part only)

# META_DISC         — disc number (integer part only)

# META_SERIES       — series name (empty if not tagged or same as book title)

# META_SERIES_INDEX — position within the series (integer)

# META_NARRATOR     — narrator name

# META_YEAR         — publication year (4 digits)

# META_SUBTITLE     — book subtitle

# META_GENRE        — genre (used for logging only)

resolve_metadata() {
load_tags “$1”

# ── Author ─────────────────────────────────────────────────────────────────

# album_artist (TPE2) is preferred over artist (TPE1) because in a

# multi-chapter rip, individual track artist tags may vary (e.g. different

# chapter narrators) while album_artist stays constant across all tracks.

# composer and narrator are last-resort fallbacks for poorly tagged files.

META_AUTHOR=$(get_tag   
“album_artist” “albumartist” “album artist” “TPE2”   
“artist” “TPE1”   
“composer” “TCOM”   
“narrator” “TXXX:NARRATOR” “TXXX:narrated_by”   
“sort_artist” “artistsort” “TSO2”)

# ── Book title ─────────────────────────────────────────────────────────────

# ‘album’ is the universal book-title tag across all audio formats.

# ‘work’ (©wrk) is the iTunes/m4b equivalent for the overall work title,

# commonly set by tools like Overdrive and Libro.fm.

META_BOOK=$(get_tag   
“album” “TALB”   
“work” “©wrk” “TXXX:WORK”   
“tvshow”)

# ── Chapter title ──────────────────────────────────────────────────────────

META_TITLE=$(get_tag “title” “TIT2” “©nam”)

# ── Track and disc numbers ─────────────────────────────────────────────────

# Many taggers write “N/Total” (e.g. “3/12”). parse_int strips the “/Total”

# part, leaving just the track index.

local track_raw disc_raw
track_raw=$(get_tag “track” “TRCK” “trkn”)
META_TRACK=$(parse_int “$track_raw”)
disc_raw=$(get_tag “disc” “TPOS” “disk” “disknumber”)
META_DISC=$(parse_int “$disc_raw”)

# ── Series name ────────────────────────────────────────────────────────────

# No single standard exists for series tags. We try all known conventions:

# TXXX:SERIES      — used by beets, MusicBrainz Picard, Overdrive

# grouping / TIT1  — iTunes “grouping” field, often repurposed for series

# work / ©wrk      — iTunes “work” atom (also used for standalone titles)

META_SERIES=$(get_tag   
“TXXX:SERIES” “series”   
“TXXX:SERIES_NAME” “series_name” “TXXX:SERIESNAME”   
“grouping” “TIT1”   
“work” “©wrk”)

# Some taggers copy the book title into the series field. Discard it if so,

# otherwise we’d create a pointless extra directory level.

[[ “$META_SERIES” == “$META_BOOK” ]] && META_SERIES=””

# ── Series index ───────────────────────────────────────────────────────────

# TXXX:SERIES-PART is the MusicBrainz/beets convention.

# movementnumber / ©mvi are the iTunes “movement number” atoms, used by

# some tools (e.g. m4b-tool) to encode the series position.

local series_part_raw
series_part_raw=$(get_tag   
“TXXX:SERIES-PART” “TXXX:SERIES_PART” “TXXX:SERIESPART”   
“series-part” “series_part” “seriespart”   
“movementnumber” “©mvi” “movement”)
META_SERIES_INDEX=$(parse_int “$series_part_raw”)

# ── Narrator ───────────────────────────────────────────────────────────────

# TXXX:NARRATOR is non-standard but widely used. composer/TCOM is a weak

# fallback — some rippers misuse it for the narrator — but it’s better than

# nothing for display purposes. It is NOT used for folder structure.

META_NARRATOR=$(get_tag   
“narrator” “TXXX:NARRATOR” “TXXX:narrated_by” “TXXX:NARRATED_BY”   
“composer” “TCOM”)

# ── Year ───────────────────────────────────────────────────────────────────

# TDRC may contain a full ISO date (e.g. “2021-03-15”); we take only the

# first 4 characters (the year). Used for display/logging only.

local date_raw
date_raw=$(get_tag “date” “TDRC” “year” “©day” “TYER”)
META_YEAR=”${date_raw:0:4}”

# ── Subtitle and genre ─────────────────────────────────────────────────────

# Neither affects folder structure — logged for information only.

META_SUBTITLE=$(get_tag “subtitle” “TXXX:SUBTITLE” “TIT3”)
META_GENRE=$(get_tag    “genre”    “TCON”          “©gen”)
}

# =============================================================================

# Path / filename inference  (fallback when embedded tags are absent)

# =============================================================================

# infer_from_path FILE

# Attempts to derive author and book title from the existing directory

# structure relative to SOURCE_DIR. Sets INFER_AUTHOR and INFER_BOOK globals.

# 

# Recognised layouts (in priority order):

# SOURCE/Author Name/Book Title/file.mp3   → author + book

# SOURCE/Author Name - Book Title/file     → author + book (split on “ - “)

# SOURCE/Book Title/file.mp3               → book only

infer_from_path() {
local file=”$1”

# Strip the source prefix to get a path relative to SOURCE_DIR.

local rel=”${file#”${SOURCE_DIR}/”}”
local dir
dir=$(dirname “$rel”)

INFER_AUTHOR=””
INFER_BOOK=””

# File sits directly in SOURCE_DIR with no subdirectory — nothing to infer.

[[ “$dir” == “.” ]] && return

if [[ “$dir” == */* ]]; then
# Two or more directory levels: treat first as author, second as book.
INFER_AUTHOR=$(cut -d/ -f1 <<< “$dir”)
INFER_BOOK=$(  cut -d/ -f2 <<< “$dir”)
elif [[ “$dir” == *” - “* ]]; then
# Single level with canonical “ - “ separator.
INFER_AUTHOR=$(sed ‘s/ - .*//’   <<< “$dir”)
INFER_BOOK=$(  sed ’s/^[^-]*- /’ <<< “$dir”)
else
# Single directory with no separator — assume it’s the book title.
INFER_BOOK=”$dir”
fi
}

# infer_from_filename FILENAME

# Last-resort inference from the filename itself.

# Sets INFER_FILE_AUTHOR and INFER_FILE_BOOK globals.

# 

# Recognised patterns:

# “Author Name - Book Title.mp3”     → author + book

# “01 - Chapter Title.mp3”           → book only (leading number → no author)

infer_from_filename() {
local base=”${1%.*}”   # Strip file extension
INFER_FILE_AUTHOR=””
INFER_FILE_BOOK=””

if [[ “$base” == *” - “* ]]; then
local p1 p2
p1=$(cut -d- -f1 <<< “$base” | sed ‘s/^ *//;s/ *$//’)
p2=$(cut -d- -f2 <<< “$base” | sed ‘s/^ *//;s/ *$//’)
# If the first segment is purely numeric, it’s a track number, not an author.
if [[ “$p1” =~ ^[0-9]+$ ]]; then
INFER_FILE_BOOK=”$p2”
else
INFER_FILE_AUTHOR=”$p1”
INFER_FILE_BOOK=”$p2”
fi
fi
}

# =============================================================================

# Cover art extraction

# =============================================================================

# extract_cover SOURCE_FILE DEST_DIR

# Extracts the first embedded image from SOURCE_FILE and saves it as

# DEST_DIR/cover.jpg. Skips silently if cover.jpg already exists.

# 

# NOTE: We deliberately do NOT pass -vcodec copy. That flag would copy the

# raw video stream bytes unchanged, which is wrong when the embedded art is

# PNG-encoded (common in MP3 files) — you’d get a .jpg file with PNG content

# inside it. Without -vcodec, ffmpeg auto-selects the encoder from the output

# filename extension, correctly converting PNG art to JPEG.

extract_cover() {
local src=”$1” dest_dir=”$2”
local cover=”${dest_dir}/cover.jpg”

# Idempotent: if a cover already exists for this book folder, leave it alone.

[[ -f “$cover” ]] && return 0

# -an        : discard audio streams (we only want the image)

# -frames:v 1: extract exactly one video frame (the cover art)

# -y         : overwrite output without prompting (safe — we checked above)

if ffmpeg -v quiet -y -i “$src” -an -frames:v 1 “$cover” 2>/dev/null; then
if [[ -s “$cover” ]]; then
logg “    Cover extracted -> cover.jpg”
inc CNT_COVER
else
# ffmpeg exited 0 but wrote an empty file — file had no embedded art
rm -f “$cover”
fi
else
# ffmpeg failed (e.g. no video stream at all) — clean up the empty file
rm -f “$cover” 2>/dev/null || true
fi
}

# =============================================================================

# Build destination path

# =============================================================================

# build_dest FILE

# Resolves all metadata and inference sources for FILE and computes the

# canonical destination path.

# 

# OUTPUTS (global variables set by this function):

# DEST_DIR_OUT   — destination directory (without trailing slash)

# DEST_FILE_OUT  — full destination file path

# NO_META_OUT    — “true” if no embedded tags were found (used for warnings)

# 

# Directory structure produced:

# With series:    DEST/Author/Series/NN - Book/filename.ext

# Without series: DEST/Author/Book/filename.ext

# 

# Filename conventions:

# .m4b            : BookTitle.m4b  (single-file audiobook — no track prefix)

# Multi-file      : NN - ChapterTitle.ext

# Multi-disc      : D01-T03 - ChapterTitle.ext

build_dest() {
local file=”$1”
local filename; filename=$(basename “$file”)
local ext_lower=”${filename##*.}”; ext_lower=”${ext_lower,,}”

# Run all three metadata sources

resolve_metadata “$file”
infer_from_path “$file”
infer_from_filename “$filename”

# Fill in blanks: embedded tags take priority, then path inference, then filename

local author=”$META_AUTHOR” book=”$META_BOOK”
NO_META_OUT=false

[[ -z “$author” && -n “$INFER_AUTHOR”      ]] && author=”$INFER_AUTHOR”
[[ -z “$author” && -n “$INFER_FILE_AUTHOR” ]] && author=”$INFER_FILE_AUTHOR”
[[ -z “$book”   && -n “$INFER_BOOK”        ]] && book=”$INFER_BOOK”
[[ -z “$book”   && -n “$INFER_FILE_BOOK”   ]] && book=”$INFER_FILE_BOOK”

# If we still have nothing, the file lands in the unknown buckets

[[ -z “$author” || -z “$book” ]] && NO_META_OUT=true

# Sanitise each path component independently — never sanitise the full path

# at once, as that would convert the directory separators too.

local ca cb
ca=$(sanitise “${author:-$UNKNOWN_AUTHOR}”)
cb=$(sanitise “${book:-$UNKNOWN_BOOK}”)

# ── Directory ──────────────────────────────────────────────────────────────

local dest_dir
if [[ -n “$META_SERIES” ]]; then
local cs; cs=$(sanitise “$META_SERIES”)
if [[ -n “$META_SERIES_INDEX” ]]; then
# Zero-pad the index so alphabetical sort = correct reading order
dest_dir=”${DEST_DIR}/${ca}/${cs}/$(printf ‘%02d’ “$META_SERIES_INDEX”) - ${cb}”
else
dest_dir=”${DEST_DIR}/${ca}/${cs}/${cb}”
fi
else
dest_dir=”${DEST_DIR}/${ca}/${cb}”
fi

# ── Filename ───────────────────────────────────────────────────────────────

local dest_filename

if [[ “$ext_lower” == “m4b” ]]; then
# m4b files are single-file audiobooks (the whole book in one container).
# Naming them after the book — not the chapter title — prevents confusing
# filenames like “Prologue.m4b” or “Chapter 1.m4b” when the title tag
# happens to contain a chapter name.
dest_filename=”${cb}.m4b”
else
# Build a sortable numeric prefix from disc and track numbers.
# Multi-disc: D01-T03 keeps discs sorted independently of each other.
# Single-disc: plain zero-padded track number (01, 02, …).
local prefix=””
if [[ -n “$META_DISC” && “$META_DISC” -gt 1 ]]; then
prefix=“D$(printf ‘%02d’ “$META_DISC”)-T$(printf ‘%02d’ “${META_TRACK:-0}”)”
elif [[ -n “$META_TRACK” ]]; then
prefix=$(printf ‘%02d’ “$META_TRACK”)
fi

```
local ct; ct=$(sanitise "${META_TITLE:-${filename%.*}}")
# "${prefix:+${prefix} - }" expands to "prefix - " if prefix is non-empty,
# or to nothing if prefix is empty — avoids a leading " - " in the name.
dest_filename="${prefix:+${prefix} - }${ct}.${ext_lower}"
```

fi

DEST_DIR_OUT=”$dest_dir”
DEST_FILE_OUT=”${dest_dir}/${dest_filename}”
}

# =============================================================================

# Deduplication

# =============================================================================

# quarantine FILE REASON VERSUS

# Moves FILE into DUPES_DIR, preserving its path relative to SOURCE_DIR.

# Called when a file is identified as a content-identical duplicate.

# 

# REASON : “DUPLICATE” (logged for traceability)

# VERSUS : Description of what it collided with (logged for traceability)

quarantine() {
local file=”$1”
local reason=”$2”
local versus=”$3”

# Mirror the source sub-path under DUPES_DIR so the user can see where

# each duplicate came from when reviewing the quarantine folder.

local rel=”${file#”${SOURCE_DIR}/”}”
local dupe_dest=”${DUPES_DIR}/${rel}”

logm “  ${reason}: quarantining -> ${dupe_dest}”
logm “           collides with: ${versus}”

if ! $DRY_RUN; then
mkdir -p “$(dirname “$dupe_dest”)”
mv – “$file” “$dupe_dest” || logr “  FAILED to quarantine $file”
else
logm “  [DRY RUN — would quarantine]”
fi

inc CNT_DUPE
}

# find_free_dest DEST_PATH

# Returns the first path of the form “base.N.ext” (N = 2, 3, …) that is

# neither present on disk nor already claimed in SEEN_DESTS.

# 

# Used when two files with different content resolve to the same destination

# name — we keep both, renaming the later arrival rather than discarding it.

# 

# SEEN_DESTS is checked as well as the filesystem so that during a dry run

# (where nothing is actually moved) we don’t suggest the same renamed path

# for multiple conflicting files.

find_free_dest() {
local dest=”$1”
local base=”${dest%.*}”   # Everything before the final dot
local ext=”${dest##*.}”   # Everything after the final dot
local n=2
local candidate
while true; do
candidate=”${base}.${n}.${ext}”
if [[ ! -e “$candidate” && -z “${SEEN_DESTS[$candidate]+_}” ]]; then
printf ‘%s’ “$candidate”
return
fi
(( n++ ))
done
}

# check_dedup FILE DEST_FILE

# Determines whether FILE should be moved, renamed, or quarantined.

# 

# Returns 0 and sets DEDUP_DEST_OUT to the (possibly adjusted) destination

# if the move should proceed.

# Returns 1 if the file has been handled by quarantine() and the caller

# should skip the move.

# 

# Two collision checks are performed in this order:

# 

# 1. SEEN_DESTS  — catches collisions between source files in this run.

# Stores fingerprints rather than source paths to avoid the stale-path

# problem: in live mode the first source file has already been moved by

# the time a later duplicate arrives, so its original path no longer exists.

# 

# 2. On-disk check — catches collisions with files placed by a previous run

# (i.e. the script is being re-run after a partial completion).

check_dedup() {
local file=”$1”
local dest_file=”$2”

DEDUP_DEST_OUT=”$dest_file”

# ── 1. In-run collision (SEEN_DESTS) ──────────────────────────────────────

if [[ -n “${SEEN_DESTS[$dest_file]+_}” ]]; then
local fp_new fp_first
fp_new=$(fingerprint “$file”)
fp_first=”${SEEN_DESTS[$dest_file]}”   # Already-computed fingerprint — no stale path

```
if [[ "$fp_new" == "$fp_first" ]]; then
  # Fingerprints match → identical content → true duplicate
  quarantine "$file" "DUPLICATE" "earlier file claiming same destination"
  return 1
else
  # Fingerprints differ → same metadata, different content (e.g. two editions)
  local renamed
  renamed=$(find_free_dest "$dest_file")
  logy "  CONFLICT: different content maps to same destination"
  logy "           renaming to: $renamed"
  DEDUP_DEST_OUT="$renamed"
  inc CNT_CONFLICT
  return 0
fi
```

fi

# ── 2. Pre-existing file on disk (re-run collision) ────────────────────────

if [[ -e “$dest_file” ]]; then
local fp_new fp_existing
fp_new=$(fingerprint “$file”)
fp_existing=$(fingerprint “$dest_file”)

```
if [[ "$fp_new" == "$fp_existing" ]]; then
  # Already at destination with the same content — nothing to do
  logd "  EXISTING DUPLICATE: already at destination (fingerprints match)"
  logd "           $dest_file"
  inc CNT_DUPE
  inc CNT_SKIPPED
  return 1
else
  # Different content occupies this slot — rename the incoming file
  local renamed
  renamed=$(find_free_dest "$dest_file")
  logy "  EXISTING CONFLICT: different file already at destination"
  logy "           renaming to: $renamed"
  DEDUP_DEST_OUT="$renamed"
  inc CNT_CONFLICT
  return 0
fi
```

fi

return 0   # No collision — proceed normally
}

# =============================================================================

# Process one file

# =============================================================================

# process_file FILE

# Orchestrates metadata resolution, path building, dedup checking, and the

# actual file move (or dry-run simulation) for a single audio file.

process_file() {
local file=”$1”
local filename; filename=$(basename “$file”)

build_dest “$file”
local dest_file=”$DEST_FILE_OUT”
local dest_dir=”$DEST_DIR_OUT”
local no_meta=”$NO_META_OUT”

# ── Already in the right place ─────────────────────────────────────────────

# This happens when the script is re-run after a partial or complete prior

# run and some files are already at their canonical destinations.

if [[ “$file” == “$dest_file” ]]; then
logd “  SKIP (already in place): $filename”
inc CNT_SKIPPED
return 0
fi

# ── Log the plan for this file ─────────────────────────────────────────────

logc “  FILE     : $file”
log  “  Author   : $(sanitise “${META_AUTHOR:-?}”)”
log  “  Book     : $(sanitise “${META_BOOK:-?}”)”
[[ -n “$META_SERIES”   ]] && log “  Series   : $META_SERIES${META_SERIES_INDEX:+ #$META_SERIES_INDEX}”
[[ -n “$META_TITLE”    ]] && log “  Chapter  : $META_TITLE”
[[ -n “$META_TRACK”    ]] && log “  Track    : $META_TRACK${META_DISC:+  Disc: $META_DISC}”
[[ -n “$META_YEAR”     ]] && log “  Year     : $META_YEAR”
[[ -n “$META_NARRATOR” ]] && log “  Narrator : $META_NARRATOR”
[[ -n “$META_SUBTITLE” ]] && log “  Subtitle : $META_SUBTITLE”
[[ -n “$META_GENRE”    ]] && log “  Genre    : $META_GENRE”
“$no_meta” && logy “  WARNING  : No embedded tags — inferred from path/filename”
log  “  –> $dest_file”

# ── Deduplication ──────────────────────────────────────────────────────────

# check_dedup returns 1 if the file was quarantined (caller does nothing more).

# It may also update DEDUP_DEST_OUT if a conflict rename was needed.

if ! check_dedup “$file” “$dest_file”; then
log “”
return 0
fi

# Use the (possibly adjusted) destination from check_dedup

dest_file=”$DEDUP_DEST_OUT”
dest_dir=$(dirname “$dest_file”)

[[ “$DEDUP_DEST_OUT” != “$DEST_FILE_OUT” ]] && log “  FINAL –> $dest_file”

# Register the final destination → fingerprint mapping so subsequent files

# can detect in-run collisions without accessing a potentially-moved source.

SEEN_DESTS[”$dest_file”]=$(fingerprint “$file”)

# ── Dry run ────────────────────────────────────────────────────────────────

if $DRY_RUN; then
log “  [DRY RUN — would move]”
inc CNT_MOVED
log “”
return 0
fi

# ── Live move ──────────────────────────────────────────────────────────────

mkdir -p “$dest_dir”

if mv – “$file” “$dest_file”; then
logg “  MOVED”
inc CNT_MOVED
# Track files where we had to guess the metadata
“$no_meta” && inc CNT_NO_META
# Attempt cover art extraction from the first file moved into each book folder.
# extract_cover() is idempotent — it skips if cover.jpg already exists.
$EXTRACT_COVER && extract_cover “$dest_file” “$dest_dir”
else
logr “  FAILED”
inc CNT_FAILED
fi

log “”
}

# =============================================================================

# Entry point

# =============================================================================

main() {
parse_args “$@”

# Truncate (not append) the log at the start of each run so it reflects only

# the current execution. The terminal always shows the full output anyway.

: > “$LOG_FILE”

log “${BOLD}══════════════════════════════════════════════════════${RESET}”
log “${BOLD}  Audiobookshelf Organiser  —  $(date ‘+%Y-%m-%d %H:%M:%S’)${RESET}”
log “${BOLD}══════════════════════════════════════════════════════${RESET}”
log “  Source      : $SOURCE_DIR”
log “  Destination : $DEST_DIR”
log “  Dupes dir   : $DUPES_DIR”
log “  Log         : $LOG_FILE”
log “  Cover art   : $( $EXTRACT_COVER && echo yes || echo no )”
if $DRY_RUN; then
logy “  Mode        : DRY RUN — nothing will be moved (add –move to apply)”
else
logg “  Mode        : LIVE — files will be moved”
fi
log “”

check_deps

[[ -d “$SOURCE_DIR” ]] || { logr “ERROR: source not found: $SOURCE_DIR”; exit 1; }

# Build the find(1) expression dynamically from AUDIO_EXTENSIONS.

# The pattern is: -iname “*.mp3” -o -iname “*.m4b” -o …

# The trailing -o is removed after the loop (unset of last element).

local find_args=()
for ext in “${AUDIO_EXTENSIONS[@]}”; do
find_args+=( -iname “*.${ext}” -o )
done
unset ‘find_args[-1]’

# Count first so we can display progress as [N/Total]

local total
total=$(find “$SOURCE_DIR” ( “${find_args[@]}” ) 2>/dev/null | wc -l)
log “Found ${BOLD}${total}${RESET} audio file(s)”
log “──────────────────────────────────────────────────────”

# Process files in sorted order for deterministic, reproducible behaviour.

# -print0 / read -d ‘’ handles filenames containing spaces, newlines, or

# other special characters safely — never use newline-delimited find output

# for file operations.

local n=0
while IFS= read -r -d ‘’ file; do
inc n
log “”
log “${BOLD}[${n}/${total}]${RESET}”
process_file “$file”
done < <(find “$SOURCE_DIR” ( “${find_args[@]}” ) -print0 2>/dev/null | sort -z)

# ── Summary ────────────────────────────────────────────────────────────────

log “”
log “${BOLD}══════════════════════════════════════════════════════${RESET}”
if $DRY_RUN; then
logy “DRY RUN complete”
log  “  Would move    : ${BOLD}${CNT_MOVED}${RESET} files”
log  “  Skipped       : ${CNT_SKIPPED} (already in place)”
log  “  Duplicates    : ${CNT_DUPE} (would quarantine to ${DUPES_DIR})”
log  “  Conflicts     : ${CNT_CONFLICT} (would rename with suffix)”
logy “  Run with –move to apply.”
else
logg “Complete”
log  “  Moved         : ${BOLD}${CNT_MOVED}${RESET} files”
log  “  Skipped       : ${CNT_SKIPPED}”
log  “  Covers        : ${CNT_COVER} extracted”
log  “  Duplicates    : ${CNT_DUPE} quarantined -> ${DUPES_DIR}”
log  “  Conflicts     : ${CNT_CONFLICT} renamed with suffix”
log  “  Failed        : ${CNT_FAILED}”
(( CNT_NO_META > 0 )) &&   
logy “  WARNING: ${CNT_NO_META} file(s) had no tags — check ‘${UNKNOWN_AUTHOR}/’”
(( CNT_DUPE > 0 )) &&   
logy “  Review duplicates in: ${DUPES_DIR}”
fi
log “${BOLD}══════════════════════════════════════════════════════${RESET}”
}

main “$@”