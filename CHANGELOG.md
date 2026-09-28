# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.3.6] - 2026-09-28

### Added

- Add automated tests for Python 3.11, 3.12, and 3.14 on every push and pull request.
- Add automated Ruff, formatting, syntax, package, Markdown, and Docker checks.
- Add weekly Dependabot updates for Python, npm, Docker, and GitHub Actions dependencies.
- Add one cross-platform `scripts/check.py` quality gate with a Linux shell wrapper.
- Add repository guidance for future contributors and agents.

### Changed

- Document the verified runtime policy, CI boundaries, current test count, and release process.
- Restrict Python package discovery to `absorg` so repository tooling cannot enter release artifacts.
- Normalise line endings and identify binary media through `.gitattributes`.

## [2.3.5] - 2026-04-11

### Fixed

- Detect and quarantine numbered duplicate copies within a single audiobook edition.
- Correct edition statistics before cross-edition scoring.

## [2.3.4] - 2026-04-10

### Changed

- Consolidate integer parsing, document constants, and split the command workflow into focused helpers.

## [2.3.3] - 2026-04-10

### Fixed

- Prevent year-prefixed books from being grouped by year alone.
- Prevent author role qualifiers from consuming following author names.
- Ignore parenthetical edition labels such as `Unabridged` during book matching.

## [2.3.2] - 2026-04-09

### Fixed

- Avoid doubling existing numeric track prefixes in destination filenames.
- Make equal-score book-edition selection deterministic.
- Avoid misleading bitrate explanations when displayed values are equal.

## [2.3.1] - 2026-04-08

### Fixed

- Separate distinct books found inside a shared series directory during book-level deduplication.

## [2.3.0] - 2026-04-06

### Changed

- Establish the 2.3 release line after the parallel-processing work.

## [2.2.0] - 2026-04-06

### Added

- Add book-level duplicate detection with format and quality-aware edition scoring.
- Add parallel fingerprint and metadata processing for network-backed libraries.

## [2.0.0] - 2026-04-02

### Changed

- Rewrite the original organiser as the installable `absorg` Python package.

[Unreleased]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.6...HEAD
[2.3.6]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.5...v2.3.6
[2.3.5]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.4...v2.3.5
[2.3.4]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.3...v2.3.4
[2.3.3]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.2...v2.3.3
[2.3.2]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.1...v2.3.2
[2.3.1]: https://github.com/MDHMatt/abs-organisation/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/MDHMatt/abs-organisation/releases/tag/v2.3.0
[2.2.0]: https://github.com/MDHMatt/abs-organisation/compare/v2.0.0...v2.2.0
[2.0.0]: https://github.com/MDHMatt/abs-organisation/releases/tag/v2.0.0
