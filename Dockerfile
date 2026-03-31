# =============================================================================
# absorg — Audiobookshelf Library Organiser
# =============================================================================
# Self-contained image with all dependencies (bash, ffmpeg, ffprobe, md5sum).
# The absorg.sh script is copied in at build time.
#
# BUILD:
#   docker build -t absorg .
#
# RUN (dry run — safe, nothing moves):
#   docker run --rm -v /mnt/user/audiobooks:/audiobooks absorg
#
# RUN (apply):
#   docker run --rm -v /mnt/user/audiobooks:/audiobooks absorg --move
#
# RUN (separate source and destination):
#   docker run --rm \
#     -v /mnt/user/audiobooks_unsorted:/source \
#     -v /mnt/user/audiobooks:/dest \
#     absorg --source /source --dest /dest --move
#
# LOGS:
#   Mount a host directory to /logs to persist the log file:
#   docker run --rm \
#     -v /mnt/user/audiobooks:/audiobooks \
#     -v /mnt/user/appdata/absorg:/logs \
#     absorg --log /logs/absorg.log --move
# =============================================================================

FROM alpine:3.19

# Install all runtime dependencies in a single layer to keep the image small.
#   bash     — the script uses bash-specific features (declare -A, <<<, etc.)
#   ffmpeg   — provides both ffmpeg (cover extraction) and ffprobe (metadata)
#   coreutils — provides GNU stat (-c%s) and md5sum (used by fingerprint())
#   curl     — available for convenience / future use
#   findutils — ensures find(1) supports -print0 consistently
RUN apk add --no-cache \
    bash \
    ffmpeg \
    coreutils \
    curl \
    findutils \
    grep \
    sed

# Copy the organiser script from the repo into the image
COPY absorg.sh /usr/local/bin/absorg.sh
RUN chmod +x /usr/local/bin/absorg.sh

# Default volume mount points matching ABS Docker conventions.
# Override at runtime with --source / --dest flags.
VOLUME ["/audiobooks"]

# Run the script with bash explicitly (not sh — the script requires bash 4+)
ENTRYPOINT ["bash", "/usr/local/bin/absorg.sh"]

# Default to dry run with standard paths — safe out of the box
CMD ["--source", "/audiobooks", "--dest", "/audiobooks"]
