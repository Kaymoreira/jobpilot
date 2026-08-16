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
- **Phase:** Specify ✅ · Design ✅ · Tasks ✅ · Execute ✅ · Verify ✅ **PASS**.
  M1 complete. `validate_state.py` exit 0; all `PJS-01..19` Verified.
- **Commits:** `9e92686` (docs) → `59b3a3b` T1 → `64bc7ac` T2 → `2f101f9` T3 →
  `fea4ef2` T4 → `c9c65a0` T5 → `8dd4c92` T6 → `757601b` verifier fix (test-only).
- **Verifier:** round 1 FAIL — 1 surviving mutant (`models.py:61` null-link branch)
  + 1 missing no-HTTP assertion (PJS-04). Both fixed in `757601b`; round 2 PASS,
  sensor 5/5 killed. Lesson L-001 (candidate): Pydantic v2 skips validators on
  defaults, so the default branch only runs when the field is passed explicitly —
  test `link=None` explicitly, not by omitting it.
- **Post-Verify (code-review fixes):** 3 commits landed after the Verify snapshot
  as review-guided corrections, test-first with all gates green, but WITHOUT a new
  independent Verifier pass: `a121be3` (oversized-body 422 detail as a list, PJS-10),
  `e897aa0` (log the internal cause server-side on a 500), `031972f` (M1 changelog
  entry). Treat these as un-reverified by an independent author until the next Verify.
- **Gate:** 63 tests (baseline 2), models.py 100%, overall 95.65%. No new dependencies.
- **Next milestone:** M2 (base CV / structured profile).
