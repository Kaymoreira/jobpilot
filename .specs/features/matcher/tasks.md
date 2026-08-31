# Matcher (M3) Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/matcher/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Confirmed from `pyproject.toml` (`--cov-fail-under=80`, branch coverage, `source = ["jobpilot"]`), `CONTRIBUTING.md` (test-first; happy **and** failing path), and the M1/M2 test layout under `tests/`. No `mypy`/`ruff` gate yet — the gate is `pytest` + coverage. `tests/fakes.py` already hosts `FakeJobRepository`/`FakeProfileRepository`; `FakeMatcher` is appended there. The eval harness lives in `evals/` (outside `src/`), so its runner/corpus are **not** in the coverage source; only the pure `metrics.py` gets unit tests (correctness, not coverage).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain models (`models.py` — `Verdict`, `*_MAX` consts, `verdict_for_score`, self-validating `MatchResult`, `cannot_assess`) | unit | All band boundaries + every validator branch (score↔verdict↔gaps↔null, rationale/gaps caps) | `tests/test_matcher_models.py` | `python -m pytest` |
| Matching core (`matching.py` — `MatcherLLMOutput`, `Matcher` port, `MatcherError`, `interpret`, `match_job`) | unit | Every fail-closed branch in `interpret`/`match_job`, driven by `FakeMatcher` (no network) | `tests/test_matching.py` | `python -m pytest` |
| Prompt (`matching.py` — `SYSTEM_PROMPT`, `render`) | unit | `render` embeds the Job + Profile fields; `SYSTEM_PROMPT` asserts grounding / output-format / thin-job phrases | `tests/test_matcher_prompt.py` | `python -m pytest` |
| LLM adapter (`matching.py` — `AnthropicMatcher`) | unit (offline, injected client) | parse-success → `MatcherLLMOutput`; each failure (validation, `APIError`, `APITimeoutError`, refusal/incomplete) → `MatcherError`; client built with `max_retries=0` + `timeout` | `tests/test_anthropic_matcher.py` | `python -m pytest` |
| API route + app wiring (`routes/matcher.py`, `app.py`) | integration (e2e via `TestClient`) | 200 happy; 404 unknown job; absent-profile → `cannot_assess`; LLM-failure → `cannot_assess` (+caplog); **spy-repo zero-writes** | `tests/test_matcher_api.py`, `tests/test_app_e2e.py` (extend) | `python -m pytest` |
| Eval metrics (`evals/matcher/metrics.py`) | unit (pure; **outside** coverage source) | precision/recall on strong-vs-not, fabrication rate, `cannot_assess` correctness on synthetic inputs | `tests/test_eval_metrics.py` | `python -m pytest` |

## Gate Check Commands

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (models, matching core, prompt) — fast, no coverage bar | `python -m pytest tests/test_matcher_models.py tests/test_matching.py tests/test_matcher_prompt.py -q --no-cov` |
| Full | After the adapter, route, and eval-metrics tasks | `python -m pytest -q` |
| Build | After the final src task — enforces the 80% coverage gate | `python -m pytest` |

> Full and Build run the same suite; Build is called out because `--cov-fail-under=80` (in `pyproject.toml` `addopts`) must be green with the failing paths exercised. The coverage-critical src is complete at **T6**; **T7** adds tests + non-src (`evals/`) code only.

---

## A note on "validation tests"

Per the skill's Test Co-location gate, there is **no test-only task** (test deferral is the anti-pattern it forbids). Validation is tested where the validated code is created:

- **Unit-level** contract enforcement (band boundaries, `MatchResult` validator, `interpret` fail-closed paths, prompt content) → co-located in **T1/T2/T3**.
- **Adapter** failure-mapping (each exception → `MatcherError`) with an **injected fake `anthropic` client** (no network) → co-located in **T4**.
- **E2E** through the real stack (404, absent-profile `cannot_assess`, LLM-failure `cannot_assess` + caplog, **zero-writes spy**) → co-located in **T5/T6**.
- **Eval metric math** (pure) → co-located in **T7**.

Every task writes its failing-path tests first (red → green): prove the gate blocks before trusting it passes.

---

## Execution Plan

Phases are ordered and run sequentially — each phase completes before the next begins. 7 tasks total → single batch, executed inline (no sub-agents). A fresh Verifier + discrimination sensor runs automatically after the final task, targeting the fail-open-critical surfaces in T1–T6.

### Phase 1: Domain + matching core + prompt

```
T1 → T2 → T3
```

### Phase 2: LLM adapter

```
T2 → T4
T3 → T4
```

### Phase 3: API route, app wiring, eval harness

```
T2 → T5
T4 → T6
T5 → T6
T4 → T7
```

---

## Task Breakdown

### T1: Add `MatchResult` contract, `Verdict`, and the band function

**What**: The canonical, self-validating advisory result — `Verdict` enum, the `*_MAX` constants, the pure `verdict_for_score` band function, and `MatchResult` (with `cannot_assess` constructor and the `model_validator` that ties score↔verdict↔gaps↔null and enforces the rationale/gaps caps).
**Where**: `src/jobpilot/models.py` (append; leave `Job`/`Profile` unchanged)
**Depends on**: None
**Reuses**: Pydantic (transitive via FastAPI)
**Requirement**: MATCH-02, MATCH-03 (gaps cap), MATCH-04, MATCH-10, MATCH-20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `Verdict = Literal["strong","possible","weak","cannot_assess"]`; `WEAK_MAX=39`, `POSSIBLE_MAX=74`, `RATIONALE_MAX=500`, `GAP_MAX=128`, `MAX_GAPS=20` defined
- [ ] `verdict_for_score(score:int) -> Verdict` returns `weak` (≤39), `possible` (40–74), `strong` (≥75) — pure, no LLM
- [ ] `MatchResult` has `score:int|None`, `verdict:Verdict`, `gaps:list[str]=[]`, `rationale:str`; `MatchResult.cannot_assess(reason)` → `score=None, verdict="cannot_assess", gaps=[], rationale=reason.strip()[:500]`
- [ ] `model_validator(mode="after")` enforces: `len(rationale)<=500`; `len(gaps)<=20`; each gap `<=128`; on `cannot_assess` → `score is None` **and** `gaps==[]`; on a decided verdict → `score` present, `0<=score<=100`, `verdict==verdict_for_score(score)`
- [ ] Unit tests (test-first) cover: each band incl. boundaries `39/40/74/75`; `cannot_assess()` yields null score + empty gaps + trimmed reason; constructing `cannot_assess` with a non-null score or non-empty gaps raises; a decided `MatchResult` whose `verdict` contradicts its band raises; a decided `MatchResult` with `score=None` raises; out-of-range score raises; over-length rationale raises; >20 gaps raises; a >128-char gap raises; `gaps=[]` accepted explicitly (Lesson L-001 — pass it explicitly, not by omission)
- [ ] Gate check passes: `python -m pytest tests/test_matcher_models.py -q --no-cov`
- [ ] Test count: ~14 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(models): add MatchResult contract, Verdict, and score-band function`

---

### T2: Add the matcher port, `interpret`, and `match_job` orchestration

**What**: `src/jobpilot/matching.py` — the loose `MatcherLLMOutput` wire contract, the `Matcher` Protocol, `MatcherError`, the single fail-closed mapper `interpret()`, and the side-effect-free `match_job()` orchestration; plus `FakeMatcher` in `tests/fakes.py`.
**Where**: `src/jobpilot/matching.py` (new); `tests/fakes.py` (append)
**Depends on**: T1
**Reuses**: `MatchResult`/`verdict_for_score`/`*_MAX` (T1), `Job`/`Profile` (models), stdlib `logging`; the port+fake pattern from the repositories
**Requirement**: MATCH-03, MATCH-04, MATCH-06, MATCH-07, MATCH-08, MATCH-10, MATCH-13, MATCH-14, MATCH-20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `MatcherLLMOutput(BaseModel)`: `score:int`, `rationale:str`, `gaps:list[str]=[]` — **no** `ge`/`le` on score (range enforced downstream); extra fields ignored
- [ ] `class MatcherError(Exception)`; `class Matcher(Protocol)` with `evaluate(job:Job, profile:Profile) -> MatcherLLMOutput`
- [ ] `interpret(raw:MatcherLLMOutput) -> MatchResult`: `not (0<=score<=100)` → `cannot_assess("...out-of-range...")` (**never clamp**); empty `rationale.strip()` → `cannot_assess("...empty rationale...")`; else decided result with `verdict_for_score`, `gaps=[g.strip()[:GAP_MAX] for g in raw.gaps if g.strip()][:MAX_GAPS]`, `rationale=raw.rationale.strip()[:RATIONALE_MAX]`
- [ ] `match_job(job:Job, profile:Profile|None, matcher:Matcher) -> MatchResult`: `profile is None` → `cannot_assess("no profile...")` with **no** `matcher.evaluate` call; on `MatcherError` → `logger.exception(...)` + `cannot_assess("...could not be completed")`; on success → `interpret(raw)`, and if the result is `cannot_assess` also `logger.warning("unusable matcher output: %r", raw)`
- [ ] `FakeMatcher` (in `tests/fakes.py`): constructed with a canned `MatcherLLMOutput` **or** an exception to raise; records whether `evaluate` was called
- [ ] Unit tests (test-first, all offline via `FakeMatcher`) cover: valid → decided `MatchResult` with band verdict; score `150`/`-1` → `cannot_assess`, score is null (never clamped); empty/whitespace rationale → `cannot_assess`; over-long gap trimmed to ≤128 and >20 gaps dropped to 20; blank gaps dropped; **absent profile → `cannot_assess` and `FakeMatcher.evaluate` NOT called**; `MatcherError` raised → `cannot_assess` and `logger.exception` emitted (`caplog`); unusable content → `logger.warning` emitted
- [ ] Gate check passes: `python -m pytest tests/test_matcher_models.py tests/test_matching.py -q --no-cov`
- [ ] Test count: ~14 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(matching): add matcher port, fail-closed interpret, and match_job`

---

### T3: Author and review the LLM prompt (`SYSTEM_PROMPT` + `render`)

**What**: The reviewable prompt artifact — `SYSTEM_PROMPT` (grounding, output-format, conservative thin-job scoring) and `render(job, profile) -> str` (the user-message content). **The prompt text is surfaced for review as part of this task.**
**Where**: `src/jobpilot/matching.py` (append)
**Depends on**: T2
**Reuses**: `Job`/`Profile` (models), `MatcherLLMOutput` shape (T2) as the format the prompt asks for
**Requirement**: MATCH-03 (grounding intent), MATCH-19 (conservative thin-job scoring)

**Tools**:

- MCP: NONE
- Skill: `stop-slop` (keep the prompt prose clean; internal, not recruiter-facing — no em-dash rule needed, but avoid slop)

**Done when**:

- [ ] `SYSTEM_PROMPT` covers, in plain text: (a) **grounding** — "use ONLY the Profile and the Job; never invent skills, experience, or qualifications the Profile does not contain"; (b) **output format** — an integer `score` 0–100, a short `rationale`, and `gaps` = the Job's requirements for which the Profile shows no evidence (empty list when none); (c) **conservative thin-job scoring** — a sparse posting (little/no description or requirements) must NOT read as a strong fit
- [ ] `render(job, profile)` returns a string embedding the Job's `title`/`company`/`description`/`requirements` and the Profile's `skills`/`seniority`/`years_experience`/`salary_expectation`/`location` (raw_cv optional), in a stable, readable layout
- [ ] The prompt text is **printed/surfaced in the task output for human review** before proceeding
- [ ] Unit tests (test-first) assert: `render` output contains the job title, company, each requirement, and each profile skill + seniority; `render` with a thin job (empty description/requirements) still produces valid text without inventing content; `SYSTEM_PROMPT` contains the grounding phrase, the `gaps` definition, and the thin-job caution (assert on key substrings)
- [ ] Gate check passes: `python -m pytest tests/test_matcher_prompt.py -q --no-cov`
- [ ] Test count: ~5 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(matching): author grounded, thin-job-aware matcher prompt`

---

### T4: Add the `AnthropicMatcher` adapter (offline-tested via injected client)

**What**: `AnthropicMatcher` implementing the `Matcher` port over the `anthropic` SDK — lazy client (`max_retries=0` + `timeout`), `messages.parse(output_format=MatcherLLMOutput)`, and mapping of every failure (validation, `APIError`, `APITimeoutError`, refusal/incomplete stop reason) to `MatcherError`. Adds `anthropic` to `pyproject.toml`.
**Where**: `src/jobpilot/matching.py` (append); `pyproject.toml` (add dependency)
**Depends on**: T2, T3
**Reuses**: `Matcher`/`MatcherError`/`MatcherLLMOutput` (T2), `SYSTEM_PROMPT`/`render` (T3), the `anthropic` SDK
**Requirement**: MATCH-07, MATCH-08, MATCH-13, MATCH-14

**Tools**:

- MCP: NONE
- Skill: `claude-api` (confirm exact `messages.parse` / `output_format` / timeout / `max_retries` SDK syntax before writing — do not guess bindings)

**Done when**:

- [ ] `anthropic` added to `[project].dependencies` in `pyproject.toml` (pin a version that supports `messages.parse` structured outputs; exact pin chosen now against the installed version)
- [ ] `AnthropicMatcher(*, model="claude-opus-4-8", timeout=60.0, effort="medium", client=None)`; `evaluate` builds `anthropic.Anthropic(max_retries=0, timeout=self.timeout)` **lazily on first call** (or uses the injected `client`), calls `messages.parse(model=..., max_tokens=..., system=SYSTEM_PROMPT, messages=[{"role":"user","content":render(job,profile)}], output_format=MatcherLLMOutput, thinking={"type":"adaptive"}, output_config={"effort":self.effort})`, checks `stop_reason`, returns `response.parsed_output`
- [ ] Any `anthropic.APIError`/`APITimeoutError`, a `refusal`/incomplete (`max_tokens`) stop reason, or a Pydantic validation error is wrapped and re-raised as `MatcherError` (`from exc`)
- [ ] The lazy real-client construction line carries `# pragma: no cover`; every other branch is covered by injecting a fake client object
- [ ] Unit tests (test-first, **no network**, injected fake client) cover: fake client returns a parsed `MatcherLLMOutput` → `evaluate` returns it; fake raises `anthropic.APITimeoutError` → `MatcherError`; fake raises an `anthropic.APIError` → `MatcherError`; response with `stop_reason=="refusal"` → `MatcherError`; response that fails `output_format` validation → `MatcherError`; assert the client was built (or called) with `max_retries=0` and the configured `timeout`
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~6 tests pass (no silent deletions)

**Tests**: unit (offline, injected client)
**Gate**: full

**Commit**: `feat(matching): add AnthropicMatcher adapter with single-attempt fail-closed calls`

---

### T5: Add the match endpoint behind the matcher + repository ports

**What**: `routes/matcher.py` — `POST /jobs/{job_id}/match` (no request body): read the Job (`404` if absent), read the singleton Profile, return `match_job(...)`; plus the `get_matcher(request)` dependency provider.
**Where**: `src/jobpilot/routes/matcher.py` (new)
**Depends on**: T2
**Reuses**: `match_job`/`Matcher` (T2), `MatchResult` (T1), `FakeMatcher` (T2), `get_repository` (`routes/jobs.py:24`), `get_profile_repository` (`routes/profile.py:29`), `FakeJobRepository`/`FakeProfileRepository` (`tests/fakes.py`), FastAPI `APIRouter`
**Requirement**: MATCH-01, MATCH-05, MATCH-06, MATCH-07, MATCH-08, MATCH-09, MATCH-11, MATCH-12

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `POST /jobs/{job_id}/match` (`response_model=MatchResult`, **no body param**): `job = job_repo.get(job_id)`; `if job is None: raise HTTPException(404)`; `profile = profile_repo.get()`; `return match_job(job, profile, matcher)`
- [ ] `get_matcher(request) -> Matcher` resolves `request.app.state.matcher`; job/profile repos resolved via the existing providers (the test override seam)
- [ ] Tests (test-first) build an app including the router with `app.state.matcher = FakeMatcher(...)`, `app.state.repo = FakeJobRepository()`, `app.state.profile_repo = FakeProfileRepository()` and cover: existing job + profile + fake score 82 → `200` `{score:82, verdict:"strong", gaps:[...], rationale:...}`; unknown `job_id` → `404`; job present but **no profile** → `200` `cannot_assess` + `score=null` + `gaps=[]` (asserts asymmetry vs the 404); fake raises `MatcherError` → `200` `cannot_assess` (+ `caplog` shows the logged cause); fake returns score `150` → `200` `cannot_assess`; a request **body** is ignored (no field is settable)
- [ ] **Zero-writes invariant**: a spy `FakeJobRepository`/`FakeProfileRepository` (recording writes) asserts a match performs **no** `add`/`upsert` and no outbound action (MATCH-11/12)
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~9 tests pass (no silent deletions)

**Tests**: integration (e2e via `TestClient`)
**Gate**: full

**Commit**: `feat(api): add advisory match endpoint behind matcher and repository ports`

---

### T6: Wire the `AnthropicMatcher` and match router into the app

**What**: Extend `create_app()` to expose `app.state.matcher = AnthropicMatcher()` (key-free lazy client) and `include_router(matcher_router)`; add end-to-end tests through the real stack (with the matcher dependency overridden by a `FakeMatcher`, since e2e must not hit the network).
**Where**: `src/jobpilot/app.py` (modify); `tests/test_app_e2e.py` (extend)
**Depends on**: T4, T5
**Reuses**: `create_app()` factory (`app.py:86`), `AnthropicMatcher` (T4), matcher router (T5), the existing sqlite connection + repos, `FakeMatcher` (T2)
**Requirement**: MATCH-01, MATCH-06, MATCH-09, MATCH-11, MATCH-12

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `create_app()` sets `app.state.matcher = AnthropicMatcher()` (constructs no Anthropic client at startup — lazy) and includes the matcher router; app still starts with **no** `ANTHROPIC_API_KEY` set
- [ ] End-to-end tests via `TestClient(create_app(db_path=":memory:"))` with `app.dependency_overrides[get_matcher]` (or `app.state.matcher`) set to a `FakeMatcher`: create a job via `POST /jobs`, author a profile via `PUT /profile`, then `POST /jobs/{id}/match` → `200` decided `MatchResult`; match against a **fresh** store (no profile) → `200` `cannot_assess`; match an unknown `job_id` → `404`; a match makes **no** change to the stored job or profile (re-`GET` both, unchanged — zero-writes through the real stack)
- [ ] `/health`, M1 `jobs`, and M2 `profile` routes still pass (no regression)
- [ ] Gate check passes: `python -m pytest` (Build — coverage gate ≥ 80% green with failing paths exercised)
- [ ] Test count: ~6 new tests pass (no silent deletions)

**Tests**: integration (e2e via `TestClient`)
**Gate**: build

**Commit**: `feat(app): wire AnthropicMatcher and match router into the app`

---

### T7: Add the offline eval harness (corpus, runner, metrics) + metric unit tests

**What**: `evals/matcher/` — a small **human-labeled** `corpus.json` (incl. a fabrication probe and a thin-job probe), a pure `metrics.py` (precision/recall on strong-vs-not, fabrication rate, `cannot_assess` correctness), and `run_eval.py` (runs the real `AnthropicMatcher` per case, prints a report that states the small-corpus / directional caveat). Metric math is unit-tested; the runner's network call is not gated.
**Where**: `evals/matcher/corpus.json`, `evals/matcher/metrics.py`, `evals/matcher/run_eval.py` (new, outside `src/`); `tests/test_eval_metrics.py` (new)
**Depends on**: T4
**Reuses**: `AnthropicMatcher` (T4), `interpret`/`MatchResult` (T1/T2)
**Requirement**: MATCH-15, MATCH-16, MATCH-17, MATCH-18, MATCH-19

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `corpus.json` holds ~8–12 **human-authored** cases (labels are the user's, never AI-generated — a placeholder corpus + a `README` noting the user fills real labels is acceptable for the harness to run); each case = `{job, profile, expected_band, is_fabrication_probe, is_thin_job_probe, expected_gap?}`; includes at least one **fabrication probe** (job requires a skill the profile lacks) and one **thin-job probe** (title/company only)
- [ ] `metrics.py` exposes **pure** functions computing: precision & recall of the strong-vs-not decision, fabrication rate (of probes: gap NOT named or verdict `strong`), and `cannot_assess` correctness — given a list of `(expected, MatchResult)` pairs; no I/O, no network
- [ ] `run_eval.py` loads the corpus, runs the real `AnthropicMatcher` per case, computes metrics via `metrics.py`, and prints a report that **explicitly states the corpus is small and the stats are directional, not robust**; documented as offline + non-gating (requires `ANTHROPIC_API_KEY`); the network call is `# pragma: no cover` / not collected
- [ ] Unit tests (test-first, **no network**) for `metrics.py`: hand-built `(expected, MatchResult)` lists yield the expected precision/recall/fabrication-rate/`cannot_assess`-correctness numbers, incl. edge cases (all-strong, none-strong, a fabrication probe that leaks, a thin job scored strong)
- [ ] `evals/` is confirmed outside the coverage source (not counted toward the 80% gate); `python -m pytest` stays green
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~6 tests pass (no silent deletions)

**Tests**: unit (pure metrics; harness itself non-gating)
**Gate**: full

**Commit**: `feat(evals): add offline matcher eval harness and metric unit tests`

---

## Phase Execution Map

The full dependency graph (edges are `dependency → task`, matching every `Depends on`):

```
T1 → T2
T2 → T3
T2 → T4
T3 → T4
T2 → T5
T4 → T6
T5 → T6
T4 → T7
```

Execution is strictly sequential (no `[P]`) in the topological order **T1, T2, T3, T4, T5, T6, T7**. 7 tasks ≤ ~8 → single batch, inline execution. A fresh Verifier + discrimination sensor runs automatically after the final task, targeting the fail-open-critical surfaces built in T1–T6 (`MatchResult` validator, `interpret`, `match_job`, the adapter's failure mapping, the route's 404/`cannot_assess` asymmetry, and the zero-writes invariant).

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: MatchResult + Verdict + band fn | contract + one pure fn, 1 file (cohesive) | ✅ Granular |
| T2: port + interpret + match_job | one module's core logic (port, mapper, orchestration) | ✅ Granular |
| T3: prompt | 1 constant + 1 render fn, same module (cohesive artifact) | ✅ Granular |
| T4: AnthropicMatcher | 1 adapter class + dependency add | ✅ Granular |
| T5: match endpoint | 1 router file (1 endpoint, one resource) | ✅ Granular |
| T6: app wiring | 1 file (`app.py`) + e2e | ✅ Granular |
| T7: eval harness | corpus + pure metrics + runner (one cohesive offline tool) | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | (start of Phase 1) | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T2 | T2 → T3 | ✅ Match |
| T4 | T2, T3 | T3 → T4 (T3 depends on T2, so both feed T4) | ✅ Match |
| T5 | T2 | T2 → T5 | ✅ Match |
| T6 | T4, T5 | T4 → T6, T5 → T6 | ✅ Match |
| T7 | T4 | T4 → T7 | ✅ Match |

All dependencies point backward; no `[P]` tasks (strictly sequential execution). T5 depends only on T2 (the matcher is injected), so it is drawn from T2, not from T4.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Domain models | unit | unit | ✅ OK |
| T2 | Matching core | unit | unit | ✅ OK |
| T3 | Prompt | unit | unit | ✅ OK |
| T4 | LLM adapter | unit (offline, injected client) | unit | ✅ OK |
| T5 | API route | integration (e2e) | integration | ✅ OK |
| T6 | API app wiring | integration (e2e) | integration | ✅ OK |
| T7 | Eval metrics | unit | unit | ✅ OK |

No task defers its tests. The adapter's network line is `# pragma: no cover` (offline branches fully tested via an injected client — not a deferral). The eval runner's network call is non-gating by design (AD-019); its pure metrics are unit-tested in T7.

---

## Requirement Coverage (all 20 mapped to ≥1 task)

MATCH-01→T5,T6 · MATCH-02→T1 · MATCH-03→T1,T2,T3,T7 · MATCH-04→T1,T2 · MATCH-05→T5 · MATCH-06→T2,T5,T6 · MATCH-07→T2,T4 · MATCH-08→T2,T4 · MATCH-09→T5,T6 · MATCH-10→T1,T2 · MATCH-11→T5,T6 · MATCH-12→T5,T6 · MATCH-13→T2,T4 · MATCH-14→T2,T4 · MATCH-15→T7 · MATCH-16→T7 · MATCH-17→T7 · MATCH-18→T7 · MATCH-19→T3,T7 · MATCH-20→T1,T2
