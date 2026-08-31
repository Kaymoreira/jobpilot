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
- Base CV / structured profile (milestone M2): a single canonical `Profile`
  (skills, seniority, optional salary expectation, location, years of experience,
  and verbatim raw CV) persisted to SQLite behind a `ProfileRepository` port,
  exposed through the profile endpoints:
  - `PUT /profile` authors or fully replaces the profile: `201` on first author,
    `200` on replace with the original `created_at` preserved and `updated_at`
    advanced. Skills are trimmed, blank-dropped, and de-duplicated
    case-insensitively (first-seen order) before persisting.
  - `GET /profile` reads the stored profile back; the empty state returns `404`
    (never a hollow `200`), so a downstream Matcher cannot mistake absence for a
    matchable profile.
  - Invalid profiles are rejected with `422` and persist nothing: no/blank
    skills, missing or bad `seniority` (closed enum), a salary range violating
    `0 < floor ≤ target ≤ ceiling`, a duplicate `(currency, contract)` pair,
    `years_experience` outside `0..60`, over-cap fields, and non-JSON/oversized
    bodies. Raw CV is stored verbatim, never parsed.
  - A persistence failure returns `500` with a generic body (no SQL or stack
    trace leaked) while the real cause is logged server-side.
- Matcher (milestone M3): the first LLM-backed component, scoring a stored `Job`
  against the stored `Profile` behind a `Matcher` port, exposed through the match
  endpoint:
  - `POST /jobs/{job_id}/match` returns an advisory `MatchResult` (a `0..100`
    score, a `strong`/`possible`/`weak`/`cannot_assess` verdict derived from
    score bands, grounded `gaps`, and a bounded `rationale`). The call is
    synchronous, ephemeral, and side-effect-free: a match writes nothing.
  - Fail-closed on every uncertainty: an absent profile, an LLM error/timeout,
    a refusal, a truncated or unparseable response, or an out-of-range score all
    resolve to `cannot_assess` with `score = null` (never clamped, never a high
    score). An unknown `job_id` is `404`; a storage read failure is a generic
    `500` (never a verdict). The real cause of a failure is logged server-side.
  - The LLM sits behind a port, so the suite runs offline against a fake; an
    offline, non-gating eval harness (`evals/matcher/`) measures the real model
    against a human-labeled corpus.
- New runtime dependency: `anthropic` (>= 1.2), the official SDK used by the
  Matcher adapter (`claude-opus-4-8` via structured `messages.parse`, single
  attempt with `max_retries=0` and a bounded timeout). The client is built
  lazily, so the app imports and starts with no `ANTHROPIC_API_KEY` set.

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
