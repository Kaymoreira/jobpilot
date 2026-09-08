# Generator (M4) Tasks

## Execution Protocol (MANDATORY — do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/generator/design.md`
**Status**: ✅ Complete — all 7 tasks implemented test-first (one commit each),
Build gate green (274 tests, 98.14% coverage), discrimination sensor 8/8 killed.

---

## Test Coverage Matrix

> Confirmed from `pyproject.toml` (`--cov-fail-under=80`, branch coverage, `source = ["jobpilot"]`), `CONTRIBUTING.md` (test-first; happy **and** failing path), and the M1/M2/M3 test layout under `tests/`. The gate is `pytest` + coverage (no `mypy`/`ruff` gate). `tests/fakes.py` already hosts `FakeJobRepository`/`FakeProfileRepository`/`FakeMatcher`; `FakeGenerator` is appended there. The M3 `match_job` + `AnthropicMatcher` are **reused as-is** (LLM call #1) — the generator adds LLM call #2. The eval harness lives in `evals/` (outside `src/`), so its runner/corpus are **not** in the coverage source; only the pure `metrics.py` gets unit tests (correctness, not coverage).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain models (`models.py` — `GenStatus`, `DRAFT_MAX`, `GENERATED_REASON`, self-validating `GenerateResult`, `cannot_generate`) | unit | Every validator branch: `draft None` iff `cannot_generate`; on `generated` → non-empty & ≤ `DRAFT_MAX` | `tests/test_generator_models.py` | `python -m pytest` |
| Generation core (`generation.py` — `Generator` port, `GeneratorError`, `build_result`, `generate_letter`) | unit | Every fail-closed branch in `build_result`/`generate_letter`, driven by `FakeMatcher` + `FakeGenerator` (no network) | `tests/test_generation.py` | `python -m pytest` |
| Prompt (`generation.py` — `SYSTEM_PROMPT`, `render`) | unit | `render` embeds Job + Profile fields **and omits `salary_expectation`**; gaps under the "internal guidance — do NOT mention" header; `SYSTEM_PROMPT` asserts grounding / gap-honesty / non-disclosure / job-language / no-salary phrases | `tests/test_generator_prompt.py` | `python -m pytest` |
| LLM adapter (`generation.py` — `AnthropicGenerator`) | unit (offline, injected client) | `messages.create` success → draft text; each failure (`AnthropicError`, `APITimeoutError`, `refusal`/`max_tokens` stop reason, missing/empty text block) → `GeneratorError`; client built with `max_retries=0` + `timeout` | `tests/test_anthropic_generator.py` | `python -m pytest` |
| API route + app wiring (`routes/generator.py`, `app.py`) | integration (e2e via `TestClient`) | 200 happy (generated); 404 unknown job; absent-profile → `cannot_generate`; match-`cannot_assess` → `cannot_generate`; generation-failure → `cannot_generate` (+caplog); `RepositoryError` → 500; **spy-repo zero-writes** | `tests/test_generator_api.py`, `tests/test_app_e2e.py` (extend) | `python -m pytest` |
| Eval metrics (`evals/generator/metrics.py`) | unit (pure; **outside** coverage source) | fabrication rate, gap-honesty, language-appropriateness, thin-job padding on synthetic inputs | `tests/test_generator_eval_metrics.py` | `python -m pytest` |

## Gate Check Commands

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (models, generation core, prompt) — fast, no coverage bar | `python -m pytest tests/test_generator_models.py tests/test_generation.py tests/test_generator_prompt.py -q --no-cov` |
| Full | After the adapter, route, and eval-metrics tasks | `python -m pytest -q` |
| Build | After the final src task — enforces the 80% coverage gate | `python -m pytest` |

> Full and Build run the same suite; Build is called out because `--cov-fail-under=80` (in `pyproject.toml` `addopts`) must be green with the failing paths exercised. The coverage-critical src is complete at **T6**; **T7** adds tests + non-src (`evals/`) code only.

---

## A note on "validation tests"

Per the skill's Test Co-location gate, there is **no test-only task** (test deferral is the anti-pattern it forbids). Validation is tested where the validated code is created:

- **Unit-level** contract enforcement (`GenerateResult` validator, `build_result`/`generate_letter` fail-closed paths, prompt content incl. the salary-omission) → co-located in **T1/T2/T3**.
- **Adapter** failure-mapping (each fault → `GeneratorError`) with an **injected fake `anthropic` client** (no network) → co-located in **T4**.
- **E2E** through the real stack (404, absent-profile / match-failed / generation-failed `cannot_generate`, `RepositoryError`→500, **zero-writes spy**) → co-located in **T5/T6**.
- **Eval metric math** (pure) → co-located in **T7**.

Every task writes its failing-path tests first (red → green): prove the gate blocks before trusting it passes.

---

## Execution Plan

Phases are ordered and run sequentially — each phase completes before the next begins. 7 tasks total → single batch, executed inline (no sub-agents). A fresh Verifier + discrimination sensor runs automatically after the final task, targeting the fail-open-critical surfaces in T1–T6.

### Phase 1: Domain + generation core + prompt

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

### T1: Add the `GenerateResult` contract, `GenStatus`, and bounds

**What**: The canonical, self-validating advisory result — `GenStatus` enum, `DRAFT_MAX` + `GENERATED_REASON` constants, and `GenerateResult` (with the `cannot_generate` constructor and the `model_validator` that ties `draft`↔`status` and enforces non-empty + `≤ DRAFT_MAX` on success).
**Where**: `src/jobpilot/models.py` (append; leave `Job`/`Profile`/`MatchResult` unchanged)
**Depends on**: None
**Reuses**: Pydantic (transitive via FastAPI); mirrors the `MatchResult` + `cannot_assess` shape
**Requirement**: GEN-03, GEN-05 (draft cap in validator), GEN-15

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `GenStatus = Literal["generated","cannot_generate"]`; `DRAFT_MAX = 6000`; `GENERATED_REASON = "ok"` defined
- [ ] `GenerateResult` has `status: GenStatus`, `draft: str | None`, `reason: str`; `GenerateResult.cannot_generate(reason)` → `status="cannot_generate", draft=None, reason=reason`
- [ ] `model_validator(mode="after")` enforces: on `cannot_generate` → `draft is None`; on `generated` → `draft` is present, `draft.strip()` non-empty, and `len(draft) <= DRAFT_MAX`
- [ ] Unit tests (test-first) cover: `cannot_generate("x")` → `status=="cannot_generate"`, `draft is None`, `reason=="x"`; a `generated` result with a real draft is accepted; constructing `generated` with `draft=None` raises; constructing `generated` with an empty/whitespace draft raises; constructing `generated` with a `> DRAFT_MAX` draft raises; constructing `cannot_generate` with a non-null draft raises (Lesson **L-001** — build each shape with **explicit** field values, not by omission)
- [ ] Gate check passes: `python -m pytest tests/test_generator_models.py -q --no-cov`
- [ ] Test count: ~7 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(models): add GenerateResult contract, GenStatus, and draft bounds`

---

### T2: Add the generator port, `build_result`, and `generate_letter` orchestration

**What**: `src/jobpilot/generation.py` — the `Generator` Protocol, `GeneratorError`, the success-side mapper `build_result()`, and the side-effect-free `generate_letter()` orchestration (which reuses the M3 `match_job` for LLM call #1 and funnels every failure to `cannot_generate`); plus `FakeGenerator` in `tests/fakes.py`.
**Where**: `src/jobpilot/generation.py` (new); `tests/fakes.py` (append)
**Depends on**: T1
**Reuses**: `GenerateResult`/`DRAFT_MAX`/`GENERATED_REASON` (T1), `MatchResult`/`Job`/`Profile` (models), `match_job` + `Matcher` (`matching.py`), stdlib `logging`; the port+fake pattern from the repositories/matcher
**Requirement**: GEN-01, GEN-02, GEN-04, GEN-05, GEN-10, GEN-11, GEN-12, GEN-13, GEN-15, GEN-18, GEN-19, GEN-20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `class GeneratorError(Exception)`; `class Generator(Protocol)` with `generate(job: Job, profile: Profile, match: MatchResult) -> str`
- [ ] `build_result(raw_draft: str) -> GenerateResult`: empty `raw_draft.strip()` → `GenerateResult.cannot_generate("generation failed")`; else `GenerateResult(status="generated", draft=raw_draft.strip()[:DRAFT_MAX], reason=GENERATED_REASON)` (truncate, never fail — GEN-05)
- [ ] `generate_letter(job: Job, profile: Profile | None, matcher: Matcher, generator: Generator) -> GenerateResult`: `profile is None` → `cannot_generate("profile absent")` with **no** LLM call (GEN-10); `match = match_job(job, profile, matcher)`; `match.verdict == "cannot_assess"` → `cannot_generate("match failed")` with **no** `generator.generate` call (GEN-11); else `try: raw = generator.generate(job, profile, match)` → on `GeneratorError`, `logger.exception("generation failed")` + `cannot_generate("generation failed")` (GEN-12); on success `return build_result(raw)`
- [ ] `FakeGenerator` (in `tests/fakes.py`): constructed with a canned draft string **or** an exception to raise; records whether `generate` was called
- [ ] Unit tests (test-first, all offline via `FakeMatcher` + `FakeGenerator`) cover: `build_result` — normal draft → `generated`; whitespace draft → `cannot_generate`; `> DRAFT_MAX` draft → `generated` truncated to `DRAFT_MAX`. `generate_letter` — **absent profile → `cannot_generate("profile absent")` and NEITHER matcher NOR generator called**; **match `cannot_assess` (FakeMatcher raising / returning bad output) → `cannot_generate("match failed")` and generator NOT called**; `weak` verdict → generator called → `generated` (generate-on-weak, GEN-04); `possible`/`strong` → `generated`; `generator` raises `GeneratorError` → `cannot_generate("generation failed")` + `logger.exception` (`caplog`); generator returns `""` → `cannot_generate`
- [ ] Gate check passes: `python -m pytest tests/test_generator_models.py tests/test_generation.py -q --no-cov`
- [ ] Test count: ~11 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(generation): add generator port, build_result, and generate_letter`

---

### T3: Author and review the LLM prompt (`SYSTEM_PROMPT` + `render`)

**What**: The reviewable prompt artifact — `SYSTEM_PROMPT` (grounding, honest gap framing, gap-machinery non-disclosure, job-language, no-salary) and `render(job, profile, match) -> str` (the user-message content, reusing M3's field rendering but **OMITTING `salary_expectation`** and appending the gaps under the "internal guidance — do NOT mention" header). **The prompt text is surfaced for review as part of this task.**
**Where**: `src/jobpilot/generation.py` (append)
**Depends on**: T2
**Reuses**: `Job`/`Profile`/`MatchResult` (models), the M3 `render` field-rendering approach (`matching.py`) as the pattern — **not** shared code (M3's render must stay unchanged; the generator gets its own `render` with salary omitted)
**Requirement**: GEN-07, GEN-08, GEN-09

**Tools**:

- MCP: NONE
- Skill: `stop-slop` (keep the prompt prose clean; internal, not recruiter-facing)

**Done when**:

- [ ] `SYSTEM_PROMPT` covers, in plain text: (a) **advisory/draft-only** framing; (b) **grounding** — "use ONLY the Profile and the Job; the Profile is both structured fields AND raw CV text; never invent skills/employers/titles/dates/degrees/qualifications; do not upgrade or embellish a stated fact"; (c) **honest gap framing** — address gaps as areas to grow / adjacent strengths, never claim a gap as possessed; (d) **non-disclosure** — the gap list is internal guidance; never mention any analysis/score/match/evaluation/"gaps"; the letter must read naturally; (e) **language** — write in the Job posting's language, falling back to the CV's language; (f) **no salary** — "Do not mention salary, compensation, or pay expectations — those are handled elsewhere in the application."; (g) **human voice / anti-AI-tells** (the letter goes straight to a recruiter; AI-tells out it as machine-written) — write in natural, human language: NO em dashes (use commas or periods), NO filler transitions ("moreover", "furthermore", "in conclusion"), NO clichéd openers ("I am writing to express my interest"), plain specific phrasing over purple prose; (h) **output** — only the letter text, no preamble/markdown/notes
- [ ] `render(job, profile, match)` returns a string embedding the Job's `title`/`company`/`description`/`requirements`, the Profile's `skills`/`seniority`/`years_experience`/`location`/`raw_cv` (verbatim), and `match.gaps` under a "GAPS (internal guidance — do NOT mention in the letter)" header (`(none)` when empty) — and **does NOT include `salary_expectation`** anywhere
- [ ] The prompt text is **printed/surfaced in the task output for human review** before proceeding
- [ ] Unit tests (test-first) assert: `render` output contains the job title, company, each requirement, each profile skill + seniority, the `raw_cv` text, and each gap; `render` output **does NOT contain** the salary figure/currency (build a profile with a `salary_expectation` and assert its values are absent from the render); `render` with empty gaps shows `(none)`; `SYSTEM_PROMPT` contains the grounding phrase, the non-disclosure phrase, the no-salary phrase, the job-language phrase, and the anti-AI-tells / no-em-dash phrasing (assert on key substrings)
- [ ] Gate check passes: `python -m pytest tests/test_generator_prompt.py -q --no-cov`
- [ ] Test count: ~8 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(generation): author grounded, machinery-hiding cover-letter prompt`

---

### T4: Add the `AnthropicGenerator` adapter (offline-tested via injected client)

**What**: `AnthropicGenerator` implementing the `Generator` port over the `anthropic` SDK — lazy client (`max_retries=0` + `timeout`), plain `messages.create` (read the `text` block), and mapping of every failure (`AnthropicError`, `APITimeoutError`, `refusal`/`max_tokens` stop reason, missing/empty text block, any adapter-boundary fault) to `GeneratorError`.
**Where**: `src/jobpilot/generation.py` (append)
**Depends on**: T2, T3
**Reuses**: `Generator`/`GeneratorError` (T2), `SYSTEM_PROMPT`/`render` (T3), the `anthropic` SDK (already a dependency — pinned by M3, **no new dep**), the `AnthropicMatcher` adapter shape (`matching.py:170`)
**Requirement**: GEN-12, GEN-13, GEN-18, GEN-19, GEN-27

**Tools**:

- MCP: NONE
- Skill: `claude-api` (confirm exact `messages.create` / content-block / `stop_reason` / timeout / `max_retries` SDK syntax before writing — do not guess bindings)

**Done when**:

- [ ] `AnthropicGenerator(*, model="claude-opus-4-8", timeout=60.0, effort="medium", max_tokens=2048, client=None)`; `generate` builds `anthropic.Anthropic(max_retries=0, timeout=self.timeout)` **lazily on first call** (or uses the injected `client`), calls `messages.create(model=..., max_tokens=self.max_tokens, system=SYSTEM_PROMPT, messages=[{"role":"user","content":render(job,profile,match)}], thinking={"type":"adaptive"}, output_config={"effort":self.effort})`, checks `stop_reason`, extracts the `text` block, returns it
- [ ] `stop_reason in {"refusal","max_tokens"}` → `GeneratorError`; the text block missing or empty/whitespace → `GeneratorError`; any `anthropic.AnthropicError` (or `APITimeoutError`) → `GeneratorError` (`from exc`); a broad adapter-boundary `except Exception` → `GeneratorError` (mirrors `AnthropicMatcher`)
- [ ] The lazy real-client construction line carries `# pragma: no cover`; every other branch is covered by injecting a fake client object
- [ ] Unit tests (test-first, **no network**, injected fake client) cover: fake client returns a message with a `text` block + `stop_reason="end_turn"` → `generate` returns the text; `stop_reason=="refusal"` → `GeneratorError`; `stop_reason=="max_tokens"` → `GeneratorError`; empty/whitespace text block → `GeneratorError`; no text block (thinking only) → `GeneratorError`; fake raises `anthropic.APITimeoutError` → `GeneratorError`; fake raises an `anthropic.APIError` → `GeneratorError`; assert the client was built (or called) with `max_retries=0` and the configured `timeout`
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~8 tests pass (no silent deletions)

**Tests**: unit (offline, injected client)
**Gate**: full

**Commit**: `feat(generation): add AnthropicGenerator adapter with single-attempt fail-closed calls`

---

### T5: Add the generate endpoint behind the generator + matcher + repository ports

**What**: `routes/generator.py` — `POST /jobs/{job_id}/generate` (no request body): read the Job (`404` if absent) + singleton Profile behind a `RepositoryError`→500 guard, return `generate_letter(job, profile, matcher, generator)`; plus the `get_generator(request)` dependency provider (reusing `get_matcher`).
**Where**: `src/jobpilot/routes/generator.py` (new)
**Depends on**: T2
**Reuses**: `generate_letter`/`Generator` (T2), `GenerateResult` (T1), `FakeGenerator` (T2), `get_matcher` (`routes/matcher.py:30`), `get_repository` (`routes/jobs.py:24`), `get_profile_repository` (`routes/profile.py:29`), `RepositoryError`+`INTERNAL_ERROR_BODY` 500 shape (`routes/matcher.py:44`), `FakeJobRepository`/`FakeProfileRepository`/`FakeMatcher` (`tests/fakes.py`), FastAPI `APIRouter`
**Requirement**: GEN-01, GEN-06, GEN-10, GEN-11, GEN-14, GEN-16, GEN-17, GEN-21

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `POST /jobs/{job_id}/generate` (`response_model=GenerateResult`, **no body param**): `try: job = job_repo.get(job_id); profile = profile_repo.get()` `except RepositoryError:` → `logger.exception(...)` + generic `500` (`INTERNAL_ERROR_BODY`); `if job is None: raise HTTPException(404)`; `return generate_letter(job, profile, matcher, generator)`
- [ ] `get_generator(request) -> Generator` resolves `request.app.state.generator`; `get_matcher` reused for the internal match; repos resolved via the existing providers (the test override seam)
- [ ] Tests (test-first) build an app including the router with `app.state.generator = FakeGenerator(...)`, `app.state.matcher = FakeMatcher(...)`, `app.state.repo = FakeJobRepository()`, `app.state.profile_repo = FakeProfileRepository()` and cover: existing job + profile + `possible` fake match + canned draft → `200` `{status:"generated", draft:"...", reason:"ok"}`; unknown `job_id` → `404`; job present but **no profile** → `200` `{status:"cannot_generate", draft:null, reason:"profile absent"}` (asserts asymmetry vs the 404); match `cannot_assess` (FakeMatcher raising) → `200` `cannot_generate` + `reason` "match failed" and generator NOT called; `FakeGenerator` raising `GeneratorError` → `200` `cannot_generate` (+ `caplog` shows the logged cause); `RepositoryError` on read → `500` generic body; a request **body** is ignored
- [ ] **Zero-writes invariant**: a spy `FakeJobRepository`/`FakeProfileRepository` (recording writes) asserts a generate performs **no** `add`/`upsert` and no outbound action (GEN-16/17)
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~9 tests pass (no silent deletions)

**Tests**: integration (e2e via `TestClient`)
**Gate**: full

**Commit**: `feat(api): add advisory generate endpoint behind generator, matcher, and repository ports`

---

### T6: Wire the `AnthropicGenerator` and generate router into the app

**What**: Extend `create_app()` to expose `app.state.generator = AnthropicGenerator()` (key-free lazy client) and `include_router(generator_router)`; add end-to-end tests through the real stack (with the generator + matcher dependencies overridden by fakes, since e2e must not hit the network).
**Where**: `src/jobpilot/app.py` (modify); `tests/test_app_e2e.py` (extend)
**Depends on**: T4, T5
**Reuses**: `create_app()` factory (`app.py:88`), `AnthropicGenerator` (T4), generate router (T5), the existing sqlite connection + repos + `AnthropicMatcher`, `FakeMatcher`/`FakeGenerator` (T2)
**Requirement**: GEN-01, GEN-10, GEN-14, GEN-16, GEN-17

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `create_app()` sets `app.state.generator = AnthropicGenerator()` (constructs no Anthropic client at startup — lazy) and includes the generate router; app still starts with **no** `ANTHROPIC_API_KEY` set
- [ ] End-to-end tests via `TestClient(create_app(db_path=":memory:"))` with `app.state.generator`/`app.state.matcher` set to fakes: create a job via `POST /jobs`, author a profile via `PUT /profile`, then `POST /jobs/{id}/generate` → `200` `generated`; generate against a **fresh** store (no profile) → `200` `cannot_generate` ("profile absent"); generate an unknown `job_id` → `404`; a generate makes **no** change to the stored job or profile (re-`GET` both, unchanged — zero-writes through the real stack)
- [ ] `/health`, M1 `jobs`, M2 `profile`, and M3 `match` routes still pass (no regression)
- [ ] Gate check passes: `python -m pytest` (Build — coverage gate ≥ 80% green with failing paths exercised)
- [ ] Test count: ~6 new tests pass (no silent deletions)

**Tests**: integration (e2e via `TestClient`)
**Gate**: build

**Commit**: `feat(app): wire AnthropicGenerator and generate router into the app`

---

### T7: Add the offline eval harness (corpus, runner, metrics) + metric unit tests

**What**: `evals/generator/` — a small **human-labeled** `corpus.json` (incl. a fabrication probe, a gap-honesty probe, and a thin-job probe), a pure `metrics.py` (fabrication rate, gap-honesty, language-appropriateness, thin-job padding), and `run_eval.py` (runs the real `match_job` + `AnthropicGenerator` per case, prints a report that states the small-corpus / directional caveat). Metric math is unit-tested; the runner's network call is not gated.
**Where**: `evals/generator/corpus.json`, `evals/generator/metrics.py`, `evals/generator/run_eval.py` (new, outside `src/`); `tests/test_generator_eval_metrics.py` (new)
**Depends on**: T4
**Reuses**: `AnthropicGenerator` (T4), `AnthropicMatcher` + `match_job` (M3), `GenerateResult` (T1)
**Requirement**: GEN-22, GEN-23, GEN-24, GEN-25, GEN-26

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `corpus.json` holds a few **human-authored** cases (labels are the user's, never AI-generated — a placeholder corpus + a `README` noting the user fills real labels is acceptable for the harness to run); each case = `{job, profile, forbidden_facts: [str], gap_label?: str, expected_language: str, is_thin_job_probe: bool}`; includes at least one **fabrication probe** (a forbidden fact absent from the profile), one **gap-honesty probe** (a labeled gap), and one **thin-job probe** (title/company only)
- [ ] `metrics.py` exposes **pure** functions computing, given `(case, letter_text)` inputs: `fabrication_rate` (does the letter assert a `forbidden_fact`?), `gap_claimed` (is the `gap_label` phrased as possessed?), `language_matches` (letter language vs `expected_language`), and thin-job padding detection — no I/O, no network; the matching is heuristic and honestly caveated as approximate
- [ ] `run_eval.py` loads the corpus, runs the real `match_job` + `AnthropicGenerator` per case, computes metrics via `metrics.py`, and prints a report that **explicitly states the corpus is small and the stats are directional, not robust**; documented as offline + non-gating (requires `ANTHROPIC_API_KEY`); the network call is `# pragma: no cover` / not collected
- [ ] Unit tests (test-first, **no network**) for `metrics.py`: hand-built `(case, letter_text)` inputs yield the expected fabrication-rate / gap-honesty / language / thin-job-padding results, incl. edge cases (a letter that leaks a forbidden fact, a letter that claims a gap, a wrong-language letter, a thin-job letter that invents specifics)
- [ ] `evals/` is confirmed outside the coverage source (not counted toward the 80% gate); `python -m pytest` stays green
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~6 tests pass (no silent deletions)

**Tests**: unit (pure metrics; harness itself non-gating)
**Gate**: full

**Commit**: `feat(evals): add offline generator eval harness and metric unit tests`

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

Execution is strictly sequential (no `[P]`) in the topological order **T1, T2, T3, T4, T5, T6, T7**. 7 tasks ≤ ~8 → single batch, inline execution. A fresh Verifier + discrimination sensor runs automatically after the final task, targeting the fail-open-critical surfaces built in T1–T6 (`GenerateResult` validator, `build_result`, `generate_letter`'s profile-absent / match-failed / generation-failed funnels, the adapter's stop-reason + empty-text mapping, the route's 404/`cannot_generate` asymmetry + `RepositoryError`→500, and the zero-writes invariant).

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: GenerateResult + GenStatus + bounds | contract + consts, 1 file (cohesive) | ✅ Granular |
| T2: port + build_result + generate_letter | one module's core logic (port, mapper, orchestration) | ✅ Granular |
| T3: prompt | 1 constant + 1 render fn, same module (cohesive artifact) | ✅ Granular |
| T4: AnthropicGenerator | 1 adapter class | ✅ Granular |
| T5: generate endpoint | 1 router file (1 endpoint, one resource) | ✅ Granular |
| T6: app wiring | 1 file (`app.py`) + e2e | ✅ Granular |
| T7: eval harness | corpus + pure metrics + runner (one cohesive offline tool) | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | (start of Phase 1) | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T2 | T2 → T3 | ✅ Match |
| T4 | T2, T3 | T2 → T4, T3 → T4 | ✅ Match |
| T5 | T2 | T2 → T5 | ✅ Match |
| T6 | T4, T5 | T4 → T6, T5 → T6 | ✅ Match |
| T7 | T4 | T4 → T7 | ✅ Match |

All dependencies point backward; no `[P]` tasks (strictly sequential execution). T5 depends only on T2 (the generator + matcher are injected), so it is drawn from T2, not from T4.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Domain models | unit | unit | ✅ OK |
| T2 | Generation core | unit | unit | ✅ OK |
| T3 | Prompt | unit | unit | ✅ OK |
| T4 | LLM adapter | unit (offline, injected client) | unit | ✅ OK |
| T5 | API route | integration (e2e) | integration | ✅ OK |
| T6 | API app wiring | integration (e2e) | integration | ✅ OK |
| T7 | Eval metrics | unit | unit | ✅ OK |

No task defers its tests. The adapter's network line is `# pragma: no cover` (offline branches fully tested via an injected client — not a deferral). The eval runner's network call is non-gating by design (AD-019/AD-028); its pure metrics are unit-tested in T7.

> **Known cosmetic multi-file warnings** (kept intentionally, as in M2/M3): T2 touches `generation.py` + `tests/fakes.py` (the co-located test double); T4 is adapter-only (no new dep this time); T6 touches `app.py` + the e2e file; T7 is the cohesive eval harness (`corpus.json` + `metrics.py` + `run_eval.py`). These are the same false-positive granularity smells accepted in M2/M3, not real splits.

---

## Requirement Coverage (all 27 mapped to ≥1 task)

GEN-01→T2,T5,T6 · GEN-02→T2 · GEN-03→T1 · GEN-04→T2 · GEN-05→T1,T2 · GEN-06→T5 · GEN-07→T3 · GEN-08→T3 · GEN-09→T3 · GEN-10→T2,T5,T6 · GEN-11→T2,T5 · GEN-12→T2,T4 · GEN-13→T2,T4 · GEN-14→T5,T6 · GEN-15→T1,T2 · GEN-16→T5,T6 · GEN-17→T5,T6 · GEN-18→T2,T4 · GEN-19→T2,T4 · GEN-20→T2 · GEN-21→T5 · GEN-22→T7 · GEN-23→T7 · GEN-24→T7 · GEN-25→T7 · GEN-26→T7 · GEN-27→T4
