# JobPilot — Project State

Project memory for spec-driven work. Decisions log is append-only (`AD-NNN`).
Handoff is the single most-recent snapshot.

## Decisions (AD-NNN)

- **AD-001 — Spec artifacts live in `.specs/`, not `specs/active/`.** The skill's
  deterministic gates only resolve `.specs/`; gate integrity is the anti-fail-open
  mechanism and outranks the browse-path preference. No pointer file (new repo,
  no prior convention). _2026-08-10_
- **AD-002 — M1 input model is hybrid.** `PastedJobSource` takes required `title`
  + `company` and optional `description`/`requirements`/`link`. No intelligent
  blob parsing until the LLM exists (M3); heuristic extraction is the fail-open
  magnet M1 is designed to avoid. _2026-08-10_
- **AD-003 — Pasted `link` is stored, never fetched.** No outbound HTTP in M1;
  fetching is `ScraperJobSource` territory (M7+, opt-in). A malformed link is
  stored as `null` + warning, not a 422 — failing the request on an unused,
  optional field is over-blocking. _2026-08-10_
- **AD-004 — Fail-open boundary is "blank after trim", not min-length.** Only
  empty/blank required fields, oversized body (50 KB), and per-field over-cap
  (title/company > 512 chars) reject with 422. No arbitrary minimum-length rule
  (that's just another heuristic). _2026-08-10_
- **AD-005 — 422 uses the FastAPI/Pydantic default envelope.** Tests assert on
  `detail[].loc` + `type`, never the human `msg` text. Uniform across endpoints
  and matches schemathesis (Fase 2). _2026-08-10_
- **AD-006 — Persistence sits behind a `JobRepository` port.** Enables the
  atomicity failing-path test (inject a repo whose `add()` raises → assert 500 +
  unchanged row count) and keeps SQLite swappable. Port vs. ORM choice decided in
  Design. _2026-08-10_
- **AD-007 — Duplicates and `status` are out of M1.** Each paste = new Job row;
  the `new/ready/sent/discarded` lifecycle belongs to the `ApplicationQueue` (M5),
  not the canonical `Job`. _2026-08-10_
- **AD-008 — Persistence is raw `sqlite3` behind a `JobRepository` Protocol.**
  Not SQLModel/SQLAlchemy. Keeps the canonical `Job` decoupled from storage, adds
  zero audit surface, gives mutation testing (Fase 2) a real target, and makes the
  atomicity failing-path test a one-line stub. Swap to SQLAlchemy Core later is
  cheap because the port isolates it. _2026-08-11_

## Handoff

- **Feature:** `pasted-job-source` (M1 — canonical `Job` + `PastedJobSource`).
- **Branch:** `feat/m1-job-pasted-source`.
- **Phase:** Specify ✅ · Design ✅ (approved) · Tasks ✅ drafted — all three validators
  clean (0/0). Spec has 19 IDs `PJS-01..19`; 6 tasks `T1..T6`.
- **Next:** Execute — awaiting user approval of `tasks.md`. 6 tasks ≤ ~8 → single
  batch, inline (no sub-agents); Verifier runs automatically after T6.
- **Scope:** Large (Pydantic models + SQLite behind `JobRepository` port + 3 endpoints
  + body-size guard). No new dependencies (all stdlib + existing FastAPI/Pydantic).
