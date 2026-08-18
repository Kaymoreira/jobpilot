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
- **AD-009 — M2 profile is authored as structured data, not extracted from a CV.**
  The caller sends structured JSON; M2 validates + persists. Heuristic extraction
  from a CV document is the fail-open magnet AD-002 forbids; real extraction needs
  the LLM + eval harness (M3). M2 mirrors `PastedJobSource`. _2026-08-17_
- **AD-010 — One canonical profile, not many.** Single-user tool (briefing §6).
  `PUT /profile` (upsert-replace) + `GET /profile`, no id. A single profile keeps
  the empty-state contract unambiguous vs. a `200 []` list. _2026-08-17_
- **AD-011 — Empty profile state is `404`, never a hollow `200`.** `GET /profile`
  returns `404` until one is authored. Absence ≠ empty: a `200` hollow profile
  lets the M3 Matcher believe it has a basis to score → fail-open. Absence must
  be loud, not silent. _2026-08-17_
- **AD-012 — Minimum valid profile = ≥1 non-blank skill AND a seniority.**
  Everything else (salary, location, years, raw CV) optional; absence is an honest
  state. A profile with no skills/no level is a draft, not a matchable profile. _2026-08-17_
- **AD-013 — `seniority` is a closed enum** (`junior`/`pleno`/`pleno-senior`/`senior`).
  Free-text forces the Matcher to interpret the string (heuristic = fail-open); an
  enum compares deterministically and matches the candidate's own rubric. _2026-08-17_
- **AD-014 — `salary_expectation` is a list of ranges keyed by `(currency, contract)`;
  absent combos are indeterminate, never "any".** Each entry has `floor ≤ target ≤
  ceiling`. "Not defined for PJ/USD" is a first-class absent state; a single number
  lets the Matcher read `null`/`0` as "any salary ok" (fail-open). `salary_expectation`
  is itself optional. _2026-08-17_

## Handoff

- **Feature:** `base-cv-profile` (M2 — canonical `Profile` + author/read surface).
- **Branch:** `feat/m2-base-cv-profile`.
- **Phase:** Specify ✅ · Design ✅ · Tasks ✅ · **Execute ✅ · Verify ✅ PASS**.
  M2 complete: all 22 `BCP-01..22` Verified.
- **Commits:** `931bca7` T1 (value objects + `ProfileCreate`) → `aa7e38d` T2
  (`Profile` + `new_from`) → `cfe7f76` T3 (`ProfileRepository` port + sqlite
  adapter + fake + contract test) → `3c7dd13` (test-only: cover the `Location`
  free-text over-cap branch T1 missed) → `01b2779` T4 (profile router) →
  `329acd4` T5 (app wiring + e2e).
- **Verifier:** round 1 PASS, no fix round needed. Discrimination sensor injected
  7 mutants over the fail-open-critical surfaces — **7/7 killed, 0 survivors**:
  drop the ≥1-skill guard, drop the `0<floor≤target≤ceiling` guard, disable
  case-insensitive skills dedup (`casefold`), corrupt salary JSON deserialization,
  stop preserving `created_at` on replace, flip the 201-vs-200 create condition,
  never return the 404 empty state. Each maps to a failing-path test that caught it.
- **Gate:** 131 tests (M1 baseline 63; +68 for M2). models.py 100%, repository.py
  100%, routes/profile.py 100%; overall 97.76% (≥80% gate green). No new deps.
- **Sensor note:** ran the sensor as a throwaway `_sensor.py` (literal
  patch → full suite → restore). On Windows, Python text-mode writes rewrote LF as
  CRLF on restore; recovered with `git checkout --`. **Lesson L-002:** on Windows,
  write the sensor's restore in binary / with `newline=""`, or run it on a scratch
  branch, so the throwaway can't drift line endings on a normalized-LF repo.
- **Next milestone:** M3 (Matcher — reads a `Profile` + a `Job` → `MatchResult`;
  the M2 `404` empty state is the "no basis to match yet" signal).

### Prior M2 planning context (kept)

- **Phase (at plan time):** Specify ✅ (22 reqs `BCP-01..22`) · Design ✅ · Tasks ✅.
- **Specify decisions:** structured-authored profile (AD-009), single canonical
  profile (AD-010), `404` empty state (AD-011), min = ≥1 skill + seniority
  (AD-012), seniority enum (AD-013), salary as `(currency,contract)` ranges with
  explicit-absent (AD-014). Plus BCP-22: 500 uses a generic body (no SQL/stacktrace
  leak) + logs the real cause server-side, mirroring M1's `e897aa0`.
- **Design highlights:** reuses M1 wholesale (port+adapter, `BodySizeLimitMiddleware`,
  `RepositoryError`, `create_app`, `app.state`+`Depends` seam, JSON-in-TEXT). Three
  new things: (1) single-row upsert — `profile` table with `id INTEGER PK CHECK(id=1)`
  + `ON CONFLICT DO UPDATE`, route `get()`s first to pick `201` vs `200` and preserve
  `created_at`; (2) nested value objects `SalaryRange`/`Location` with `model_validator`s;
  (3) fail-closed `404` empty state. Parametrized contract test over Sqlite+Fake
  `ProfileRepository`. Lesson L-001 (test optional fields explicitly) flagged for
  optional-field branches.
- **Tasks:** 5 atomic tasks, strictly sequential (T1 value objects+`ProfileCreate` →
  T2 `Profile`+`new_from` → T3 `ProfileRepository`+sqlite adapter+fake+contract test →
  T4 profile router → T5 app wiring+e2e). All 22 `BCP` mapped to ≥1 task; validation
  tests co-located (no test-only task, per skill's deferral gate). `validate_tasks`
  exit 0 (2 cosmetic warnings: co-located test-double files flagged as granularity
  smell — false positive, kept intentionally). One commit per task, messages predefined.
- **Next:** Execute — implement T1..T5 test-first (red→green), atomic commit per task,
  then the automatic fresh-Verifier + discrimination sensor after T5.
- **Prior feature (M1) — kept for reference below.**

---

### Prior handoff — `pasted-job-source` (M1) — COMPLETE

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
- **Post-Verify (code-review fixes):** 3 commits landed after the initial Verify
  snapshot as review-guided corrections, test-first with all gates green:
  `a121be3` (oversized-body 422 detail as a list, PJS-10), `e897aa0` (log the
  internal cause server-side on a 500), `031972f` (M1 changelog entry).
- **Re-Verify (scoped):** ran a discrimination sensor over the two code surfaces
  the fixes touched — the `BodySizeLimitMiddleware` 422 list response (`app.py`)
  and the `RepositoryError -> 500` logging path (`routes/jobs.py`). 8 targeted
  mutants injected, **8/8 killed, 0 survivors** → **PASS**. Notable kills: reverting
  detail to a bare string / empty list, altering `type`/`loc`/`msg`, dropping the
  log call, and downgrading `logger.exception` to `logger.error` (loses the
  traceback the caplog test demands). `a121be3`/`e897aa0` are now reverified;
  `031972f` is docs-only (no code surface).
- **Gate:** 63 tests (baseline 2), models.py 100%, overall 95.65%. No new dependencies.
- **Next milestone:** M2 (base CV / structured profile).
