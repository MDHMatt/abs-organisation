# =============================================================================
# absorg — Audiobookshelf Library Organiser
# =============================================================================
# Self-contained image with Python and mutagen for metadata reading.
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

FROM python:3.12-alpine

# Copy and install the package
COPY pyproject.toml /app/
COPY absorg/ /app/absorg/
WORKDIR /app
RUN pip install --no-cache-dir .

# Declare expected volume mount points
VOLUME ["/source", "/dest", "/logs", "/dupes"]

# Run via the installed console script
ENTRYPOINT ["absorg"]

# Default to dry run — safe out of the box. Append --move to apply.
CMD ["--source", "/source", "--dest", "/dest", "--dupes", "/dupes", "--log", "/logs/absorg.log"]
