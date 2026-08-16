# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- PastedJobSource (milestone M1): a canonical `Job` persisted to SQLite behind
  a `JobRepository` port, exposed through the jobs endpoints:
  - `POST /jobs` validates a pasted posting and persists it (`201`); blank or
    missing required fields, over-cap `title`/`company` (> 512 chars), and
    non-JSON bodies are rejected with `422` and nothing is persisted.
  - `GET /jobs/{id}` reads a stored job back (`404` when unknown).
  - `GET /jobs` lists stored jobs, newest first.
- Request body-size limit (50 KB): oversized bodies are rejected with `422`
  before parsing; the guard counts actual streamed bytes and ignores a
  client-supplied `Content-Length`.
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
