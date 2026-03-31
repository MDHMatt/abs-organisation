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
#   docker run --rm \
#     -v /mnt/user/Audiobooks2:/source \
#     -v /mnt/user/Audiobooks:/dest \
#     absorg
#
# RUN (apply):
#   docker run --rm \
#     -v /mnt/user/Audiobooks2:/source \
#     -v /mnt/user/Audiobooks:/dest \
#     -v /mnt/user/appdata/absorg/logs:/logs \
#     -v /mnt/user/appdata/absorg/dupes:/dupes \
#     absorg --move
#
# Or use docker-compose (recommended for Unraid):
#   docker-compose run --rm absorg          # dry run
#   docker-compose run --rm absorg --move   # apply
# =============================================================================

FROM alpine:3.19

# Install all runtime dependencies in a single layer to keep the image small.
#   bash      — the script requires bash 4+ (declare -A, <<<, ${var,,})
#   ffmpeg    — provides both ffmpeg (cover extraction) and ffprobe (metadata)
#   coreutils — provides GNU stat (-c%s) and md5sum (used by fingerprint())
#   findutils — ensures find(1) supports -print0 consistently
#   grep      — used in usage() and metadata parsing
#   sed       — used in usage() to strip comment prefix from header
RUN apk add --no-cache \
    bash \
    ffmpeg \
    coreutils \
    findutils \
    grep \
    sed

# Copy the organiser script from the repo into the image
COPY absorg.sh /usr/local/bin/absorg.sh
RUN chmod +x /usr/local/bin/absorg.sh

# Declare expected volume mount points
VOLUME ["/source", "/dest", "/logs", "/dupes"]

# Run the script with bash explicitly (not sh — the script requires bash 4+)
ENTRYPOINT ["bash", "/usr/local/bin/absorg.sh"]

# Default to dry run — safe out of the box. Append --move to apply.
CMD ["--source", "/source", "--dest", "/dest", "--dupes", "/dupes", "--log", "/logs/absorg.log"]
