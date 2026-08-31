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
- **AD-015 — `MatchResult` verdict is a closed enum with an explicit uncertainty
  state; `cannot_assess` carries `score = null`, not `0`.** Verdict ∈
  `strong`/`possible`/`weak`/`cannot_assess`. On *any* evaluation failure (absent
  Profile, LLM error/timeout, malformed output) verdict = `cannot_assess` and
  score = `null`. A `0` would make "bad fit" and "couldn't evaluate" the same
  output — the fail-open collapse M3 exists to prevent. Downstream must handle a
  null score explicitly; that's intentional. _2026-08-25_
- **AD-016 — LLM returns score (int 0–100) + rationale only; verdict is derived
  from bands; invalid score fails closed, never clamps.** Bands (proposed, tuned
  in Design): `0–39 weak`, `40–74 possible`, `75–100 strong`. Single source of
  truth = the number, so score and verdict cannot contradict by construction, and
  the band map is a pure LLM-free unit-testable function. A score outside `0..100`,
  wrong type, or missing → `cannot_assess`; clamping `150→100` would be a silent
  fail-open. _2026-08-25_
- **AD-017 — Match is synchronous + ephemeral; unknown `job_id` → 404, absent
  Profile → 200 `cannot_assess`.** `POST /jobs/{job_id}/match` runs the LLM and
  returns the `MatchResult`; nothing is stored (persistence + staleness deferred
  to M5, its real consumer — YAGNI, and storing now = stale-score fail-open). The
  addressed resource (job) genuinely missing is an honest `404`; an absent Profile
  is "no basis to judge", not "not found", so it is a `200 cannot_assess` (per
  AD-015). _2026-08-25_
- **AD-018 — `MatchResult` carries structured `gaps: list[str]` + a bounded
  rationale; no-fabrication is measured, not runtime-guaranteed.** `gaps` = job
  requirements with no Profile evidence — turns "no fabrication" into a red/green
  test (probe: missing skill must appear in `gaps` AND verdict ≠ `strong`).
  `rationale` is always present, ≤500 chars trimmed, and states the reason on
  `cannot_assess`. Grounding is enforced by prompt + eval harness; an LLM's
  honesty can't be a hard runtime guarantee, so we *measure* fabrication rate, not
  *prove* its absence. **Refinement (reviewer round 1):** on `cannot_assess`,
  `gaps = []` (consistent with `score = null`) — an untrusted/failed run surfaces
  no partial gaps (MATCH-20); and `gaps` is a *shape* contract, "not inventing" is
  prompt-intended + harness-measured (MATCH-17), not a runtime check. _2026-08-25_
- **AD-019 — Two-layer testing; M3 ships a minimal-but-real, human-labeled eval
  harness.** Layer 1: faked LLM behind a port, deterministic, IN the coverage gate
  (mutation-testing target). Layer 2: real LLM, OFFLINE, metrics-vs-thresholds,
  NOT a blocking CI check — a flaky gate is a fail-open gate. M3 ships ~8–12
  human-labeled cases (never AI-labeled, or we grade the model against itself) +
  runner + metrics (precision/recall on strong-vs-not, fabrication rate,
  `cannot_assess` correctness); tiny corpus → directional stats, stated plainly.
  _2026-08-25_
- **AD-020 — Advisory-only is a side-effect-free / zero-writes invariant.** A
  match writes to no repository, mutates no state, triggers no outbound action —
  an explicit, load-bearing requirement enforced by a spy-repository test (run a
  match, assert zero writes), not an accident of the ephemeral decision. Makes
  "the human decides" (briefing §1) a proven guarantee. _2026-08-25_
- **AD-021 — LLM failure policy = single attempt, bounded timeout, fail closed;
  no retry; log the real cause server-side.** Any LLM error/timeout/malformed
  output → `cannot_assess`; no retry in MVP (retry imports nondeterminism and
  masks a flaky provider — a soft fail-open). The real cause is logged server-side
  (mirrors M2's `logger.exception`) while the client sees only `cannot_assess`, so
  a flaky provider stays diagnosable without being masked or leaking internals.
  Exact timeout value + any future retry/backoff → Design. **Provider/model choice
  is deferred to Design** (via `claude-api`, default latest Claude). _2026-08-25_
- **AD-022 — LLM = official `anthropic` SDK + `claude-opus-4-8` via
  `messages.parse`; single attempt = `max_retries=0` + bounded `timeout`.** Model
  per the `claude-api` skill's mandated default (latest Claude). Structured output
  via `client.messages.parse(output_format=MatcherLLMOutput)` → `response.parsed_output`
  (no hand-parsing). `thinking=adaptive`, `effort=medium`, no `temperature`
  (removed on 4.8 — reinforces the eval harness). `max_retries=0` disables the
  SDK's auto-retry so AD-021's "single attempt, no retry" is real; `timeout=60s`
  → `APITimeoutError` → `MatcherError` → `cannot_assess`. Client built **lazily**
  so import/startup/tests need no API key. First third-party runtime dependency.
  _2026-08-25_
- **AD-023 — Loose LLM contract + one central fail-closed mapper + self-validating
  `MatchResult`.** The port returns an untrusted `MatcherLLMOutput` (`score:int`,
  `rationale`, `gaps`) with **no range bounds** (structured outputs strip numeric
  min/max anyway), or raises `MatcherError`. A single pure `interpret()` enforces
  `0..100` (never clamp), non-empty rationale, gaps normalization, verdict from
  bands, and routes every failure to `cannot_assess` — so all fail-open paths pass
  through one mutation-tested function, and the `FakeMatcher` can simulate every
  case offline. `MatchResult` `model_validator` makes the contract structural
  (score↔verdict↔gaps↔null), a natural mutation target. _2026-08-25_

## Handoff

- **Feature:** `matcher` (M3 — `Job` × `Profile` → `MatchResult`; the first LLM
  component). Spec at `.specs/features/matcher/spec.md`.
- **Branch:** `feat/m3-matcher` (rebased onto current `main` = M1+M2 merged, tip
  `e11a808`). **Tracking issue: #5** — the M3 PR closes it (`Closes #5`).
- **Phase:** **Specify ✅ (reviewer r1)** · **Design ✅ (reviewer r1)** · **Tasks ✅**
  · **Execute ✅** · **Verify ✅ PASS**. All 7 tasks implemented test-first, one
  commit each. M3 complete pending PR.
- **Execute commits:** `cfc3c64` (docs: spec/design/tasks) → `43c7019` T1
  (`MatchResult`+`Verdict`+band fn) → `d6c8aa3` T2 (port+`interpret`+`match_job`
  +`FakeMatcher`) → `d8c8d92` T3 (grounded thin-job-aware prompt) → `4ce664d` T4
  (`AnthropicMatcher`, `anthropic>=1.2` pinned) → `7de883a` T5 (match endpoint +
  zero-writes spy) → `2bf761f` T6 (app wiring + e2e) → `43463a7` T7 (offline eval
  harness + pure metric tests). The prompt (T3) was surfaced to the user for
  review during Execute per the design r1 requirement.
- **Gate:** 204 tests pass (M2 baseline was 149), overall coverage 97.99%
  (`--cov-fail-under=80` green); `models.py`/`routes/matcher.py` 100%,
  `matching.py` 97% (only cosmetic location-render branches uncovered). `evals/`
  confirmed outside the coverage source. `anthropic 1.2.0` installed; the app
  imports/starts with no `ANTHROPIC_API_KEY` (lazy client) — asserted by e2e.
- **Verify (discrimination sensor):** 3 fail-open-critical surfaces mutated and
  each caught by the suite (restored via `git checkout`, no L-002 CRLF drift):
  (1) `interpret` out-of-range guard → `if False` → 3 tests failed; (2)
  `MatchResult` validator band-consistency check → `if False` → 1 test failed;
  (3) `match_job` profile-absent short-circuit → disabled → 3 tests failed.
  **3/3 mutations killed, 0 survivors → PASS.** Full suite green after all
  restores.
- **Deviation from Tasks plan (both fail-*closed*, not fail-open):** (a) T4's lazy
  real-client construction is covered by a monkeypatch test asserting
  `max_retries=0`+`timeout`, so no `# pragma: no cover` was needed there; (b) T5
  adds a `RepositoryError → generic 500` guard on the reads (with a test) so a
  storage blip can't masquerade as a verdict — consistent with M1/M2, beyond the
  literal T5 done-when.
- **Tasks (`.specs/features/matcher/tasks.md`):** 7 atomic, strictly-sequential,
  test-first tasks, all 20 `MATCH` reqs mapped, one commit each. T1 `MatchResult`
  + `Verdict` + band fn (`models.py`); T2 matcher port + `interpret` + `match_job`
  + `FakeMatcher` (`matching.py`); **T3 the reviewable prompt** (`SYSTEM_PROMPT` +
  `render`, text surfaced for review); T4 `AnthropicMatcher` (injected-client
  offline tests, adds `anthropic` to `pyproject.toml`, uses `claude-api` skill for
  exact SDK syntax); T5 `routes/matcher.py` (`POST /jobs/{job_id}/match`); T6 app
  wiring + e2e + zero-writes spy; T7 eval harness `evals/matcher/` + pure
  `metrics.py` unit tests. Coverage-critical src done at T6 (Build gate); T7 adds
  tests + non-src `evals/`. Verifier + sensor run after the final task over the
  T1–T6 fail-open surfaces. `validate_tasks` exit 0 (4 cosmetic multi-file
  warnings — co-located test double / dep-add / e2e file / cohesive eval harness —
  false positives kept intentionally, as in M2). `validate_state` exit 0.
- **Design reviewer round 1 (applied):** (1) gaps now bounded — `GAP_MAX=128` per
  entry, `MAX_GAPS=20` count; `interpret()` trims/drops over-cap (advisory prose,
  not fail-closed, same policy as rationale); `MatchResult` validator enforces both
  (MATCH-03). (2) Prompt is a first-class reviewable artifact — Tasks gives
  `SYSTEM_PROMPT`+`render()` their own authored+reviewed task covering grounding /
  output format / conservative thin-job scoring; prompt text surfaced for review.
  (3) `MatcherLLMOutput` pinned to `matching.py` (transient wire contract);
  `MatchResult`/`verdict_for_score`/`*_MAX` constants stay in `models.py`.
- **Design (`.specs/features/matcher/design.md`):** reuses the M1/M2
  route→models→port→`app.state`+`Depends` seam, but the port hides an LLM. Load-
  bearing pieces: (1) a single fail-closed mapper `interpret()` all uncertainty
  funnels through; (2) a self-validating `MatchResult` (`model_validator` ties
  score↔verdict↔gaps↔null); (3) key-free lazy client + `max_retries=0` +
  `timeout` for single-attempt fail-closed + zero-writes advisory. New module
  `matching.py` (`Matcher` Protocol, `AnthropicMatcher`, `MatcherError`,
  `interpret`, `match_job`), new `routes/matcher.py` (`POST /jobs/{job_id}/match`),
  `MatchResult`/`MatcherLLMOutput`/`verdict_for_score` in `models.py`,
  `FakeMatcher` in `tests/fakes.py`. Eval harness in `evals/matcher/` (outside
  `src/` and `tests/`, non-gating; pure `metrics.py` unit-tested).
- **Provider/model (AD-022):** `anthropic` SDK + `claude-opus-4-8` via
  `messages.parse`; `max_retries=0`, `timeout=60s`, adaptive thinking, effort
  medium. First third-party runtime dep — add to `pyproject.toml`, pin at Execute.
- **Reviewer round 1 (applied):** (1) MATCH-03 reworded — `gaps` is a *shape*
  contract; "not inventing" is prompt-intended + harness-**measured** (MATCH-17),
  never a runtime check (removes contradiction with AD-018 + the gaps edge case).
  (2) Added thin-job probe to the eval corpus (MATCH-19): a title/company-only job
  must NOT score `strong` — overconfidence on sparse input is measured, not assumed.
  (3) Pinned `cannot_assess → gaps = []` (MATCH-20), consistent with `score = null`
  — an untrusted run surfaces no partial signal. The two `n` defaults (rationale
  truncation; thin job → low score not `cannot_assess`) approved as-is.
- **Contract decided:** `MatchResult {score: int 0–100 | null, verdict:
  strong|possible|weak|cannot_assess, gaps: list[str], rationale: str ≤500}`;
  `score = null` iff `verdict = cannot_assess`. Endpoint `POST /jobs/{job_id}/match`,
  synchronous, ephemeral, side-effect-free.
- **Requirements:** 20 EARS reqs `MATCH-01..20` (P1: 01–14 + 20 score/fail-closed/
  advisory/seam; P2: 15–19 eval harness incl. thin-job probe). All `Pending` —
  Tasks phase not started.
- **Guardrails locked as reqs:** human-in-the-loop = zero-writes invariant
  (MATCH-11/12, AD-020); fail-open = every uncertainty → `cannot_assess`+null,
  never a high score (MATCH-06..10, AD-015/016/017/021); honesty = structured
  `gaps` + measured fabrication (MATCH-03/17, AD-018); testability = deterministic
  port + offline eval harness (MATCH-13..18, AD-019).
- **Resolved in Design:** provider/model (AD-022), band cutoffs (`0–39`/`40–74`/
  `75–100`), timeout (60s) + `max_retries=0`, numeric-string coercion (schema int
  + Pydantic; non-int → fail closed), narrow LLM contract (`MatcherLLMOutput`).
- **Lessons carried:** L-001 (Pydantic v2 skips validators on defaults — test the
  score bound with an explicit value, not omission); L-002 (Windows sensor restore
  must be binary/`newline=""` to avoid LF→CRLF drift).
- **Next:** Tasks — break M3 into atomic, strictly-ordered tasks, each mapping ≥1
  `MATCH` req, test-first, one commit per task: (T1) `models.py` — `Verdict`,
  `*_MAX` constants, `verdict_for_score`, self-validating `MatchResult`; (T2)
  `matching.py` — `MatcherLLMOutput`, `Matcher` Protocol, `MatcherError`,
  `interpret()` (gaps/rationale bounding, fail-closed), `match_job()`; (T3)
  **authored+reviewed prompt task** — `SYSTEM_PROMPT` + `render(job, profile)`
  covering grounding / parse output format / conservative thin-job scoring, text
  surfaced for review; (T4) `AnthropicMatcher` with injected-client unit tests +
  add `anthropic` to `pyproject.toml` (pin); (T5) `routes/matcher.py`; (T6) app
  wiring + e2e + spy-repo zero-writes test; (T7) eval harness `evals/matcher/`
  (corpus + runner) + pure `metrics.py` unit tests. Prompt is a first-class
  artifact (T3), not an Execute detail.

### Prior handoff — `base-cv-profile` (M2) — COMPLETE

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
