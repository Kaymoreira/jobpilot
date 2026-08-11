# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `CONTRIBUTING.md` documenting engineering standards (Conventional Commits,
  SemVer, testing philosophy, quality gates, Definition of Done).
- This changelog.

## [0.1.0] - 2026-08-10

### Added
- Project skeleton (milestone M0): FastAPI application with a `/health`
  endpoint exposed through a `create_app()` factory.
- pytest test suite with a coverage gate (`--cov-fail-under=80`), verified on
  the failing path (low coverage exits non-zero).
- `.gitignore` covering virtualenv, coverage artifacts, local database, secrets
  (`.env`), and agent-skill tooling folders.

[Unreleased]: https://github.com/Kaymoreira/jobpilot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Kaymoreira/jobpilot/releases/tag/v0.1.0
