# Repository guidance

## Purpose

`absorg` organises audiobook files for Audiobookshelf. Dry-run behaviour is the
default and must remain the default. Any change to move, quarantine, duplicate,
or conflict handling needs focused regression tests.

## Supported runtimes

- Python 3.11 is the supported floor.
- Python 3.12 is the Docker runtime.
- CI also tests the current stable Python release.

Runtime support was checked against the official Python version status page on
2026-09-28. Dependabot cannot detect Python end-of-life dates, so this check must
be repeated manually when changing a runtime pin.

## Development gate

Install the development dependencies and run the complete local gate:

```bash
python -m pip install -e ".[dev]"
python scripts/check.py
```

The gate covers Ruff lint and formatting, Python syntax compilation, the full
pytest suite, package creation, and Markdown linting. `scripts/check.sh` is the
Linux wrapper for the same gate. CI additionally builds the Docker image and
checks its command-line entry point.

## Change discipline

- Keep `CHANGELOG.md` in Keep a Changelog format.
- Keep `pyproject.toml` and `absorg/__init__.py` versions identical.
- Add or update tests for behavioural changes.
- Do not weaken duplicate detection or convert quarantine into deletion.
- Preserve unrelated work and avoid generated or media files in Git.
