# Base CV / Structured Profile (M2) Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/base-cv-profile/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Confirmed from `pyproject.toml` (`--cov-fail-under=80`, branch coverage), `CONTRIBUTING.md` (test-first; happy **and** failing path), and the M1 test layout under `tests/`. No `mypy`/`ruff` configured yet, so the gate is `pytest` + coverage only. `tests/fakes.py` already exists (hosts `FakeJobRepository`); the profile fake is appended there.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain models (`models.py` — `SalaryRange`/`Location`/`ProfileCreate` validators, `Profile`, `new_from`) | unit | All branches; 1:1 to spec ACs; every listed edge case has a test | `tests/test_profile_models.py` | `python -m pytest` |
| Repository (`repository.py` — `ProfileRepository` port, `SqliteProfileRepository`) | integration | Port contract (get/upsert roundtrip, replace, JSON fields) + atomicity/failure path | `tests/test_profile_repository.py` | `python -m pytest` |
| API routes + app wiring (`routes/profile.py`, `app.py`) | integration (e2e via `TestClient`) | Both routes: happy + full 422 rejection matrix + 404 empty state + 500 failure/no-leak | `tests/test_profile_api.py`, `tests/test_app_e2e.py` (extend) | `python -m pytest` |

## Gate Check Commands

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (models) — fast, no coverage bar | `python -m pytest tests/test_profile_models.py -q --no-cov` |
| Full | After integration/e2e tasks | `python -m pytest -q` |
| Build | After the final task — enforces the 80% coverage gate | `python -m pytest` |

> Full and Build run the same suite; Build is called out because `--cov-fail-under=80` (in `pyproject.toml` `addopts`) must be green at the end with the failing paths exercised.

---

## A note on "validation tests"

Per the skill's Test Co-location gate, there is **no test-only task** (test deferral is the anti-pattern it forbids). Validation is tested where the validated code is created:

- **Unit-level** validator behavior (skills normalization, salary cross-field rules, enum, caps, ranges) → co-located in **T1**.
- **API-level** 422 rejection matrix (the `loc`/`type` contract per endpoint) → co-located in **T4**.
- **E2E** rejection through the real stack (oversized body, failing repo) → co-located in **T5**.

Every task below writes its own failing-path tests first (red → green), matching the QE philosophy: prove the gate blocks before trusting it passes.

---

## Execution Plan

Phases are ordered and run sequentially — each phase completes before the next begins, and tasks within a phase execute in order. 5 tasks total → single batch, executed inline (no sub-agents). A fresh Verifier runs automatically after T5.

### Phase 1: Domain models

```
T1 → T2
```

### Phase 2: Persistence port + adapter + contract test

```
T2 → T3
```

### Phase 3: API routes + app wiring

```
T3 → T4 → T5
```

---

## Task Breakdown

### T1: Add value objects and validated `ProfileCreate` input model

**What**: The Pydantic input layer — `Seniority`/`Contract` literals, `SalaryRange` and `Location` value objects, and `ProfileCreate` with all field/model validation.
**Where**: `src/jobpilot/models.py` (append; leave `Job`/`JobCreate` unchanged)
**Depends on**: None
**Reuses**: Pydantic (transitive via FastAPI); stdlib `re`
**Requirement**: BCP-03, BCP-04, BCP-05, BCP-06, BCP-09, BCP-10, BCP-11, BCP-12, BCP-14, BCP-15, BCP-19, BCP-20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `Seniority = Literal["junior","pleno","pleno-senior","senior"]`, `Contract = Literal["CLT","PJ","other"]` defined
- [ ] `SalaryRange` has `currency` (validated `^[A-Z]{3}$`), `contract`, `floor`/`target`/`ceiling` with a `model_validator` enforcing `0 < floor <= target <= ceiling`
- [ ] `Location` has `remote_preference: Literal["remote","hybrid","onsite"]`, `open_to_international: bool = False`, `base_location`/`timezone` (optional, trimmed, ≤512)
- [ ] `ProfileCreate` has `skills`, `seniority`, `years_experience` (`ge=0, le=60`, optional), `salary_expectation: list[SalaryRange] = []`, `location` (optional), `raw_cv` (optional, trimmed, ≤50 KB)
- [ ] `skills` validator: trims, drops blanks, de-duplicates case-insensitively preserving first-seen order, each ≤128 chars, ≥1 remaining else `value_error`
- [ ] `ProfileCreate` `model_validator` rejects duplicate `(currency, contract)` pairs in `salary_expectation`
- [ ] Unknown fields (`created_at`/`updated_at`) are dropped, not stored
- [ ] Unit tests (test-first) cover: skills trim/blank-drop/ci-dedup/order/≤128/empty→error; seniority bad value→error; salary floor>ceiling→error, zero/negative→error, valid ok; duplicate currency+contract→error; `years_experience` out of `0..60`→error, valid & absent ok; `raw_cv` trimmed & >50 KB→error; empty `salary_expectation` list accepted; optional fields absent accepted; server fields dropped
- [ ] Gate check passes: `python -m pytest tests/test_profile_models.py -q --no-cov`
- [ ] Test count: ~16 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(models): add value objects and validated ProfileCreate input model`
**Status**: Complete

---

### T2: Add canonical `Profile` model and `new_from` factory

**What**: The canonical stored/response `Profile` (adds server-owned `created_at`/`updated_at`) plus `Profile.new_from(data, *, created_at=None)` that preserves `created_at` on replace and always advances `updated_at`.
**Where**: `src/jobpilot/models.py` (modify)
**Depends on**: T1
**Reuses**: `ProfileCreate` and value objects from T1; stdlib `datetime`
**Requirement**: BCP-01, BCP-02, BCP-06, BCP-18

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `Profile` carries all `ProfileCreate` fields (normalized) plus `created_at: datetime`, `updated_at: datetime`
- [ ] `Profile.new_from(data)` sets `created_at=datetime.now(UTC)` and `updated_at=datetime.now(UTC)` on first create
- [ ] `Profile.new_from(data, created_at=existing)` reuses the passed `created_at` (replace) while `updated_at` is a fresh `datetime.now(UTC)`
- [ ] Unit tests (test-first) cover: create sets both timestamps as timezone-aware UTC; replace preserves the passed `created_at` and yields `updated_at >= created_at`; two `new_from` calls without a passed `created_at` produce distinct/advancing `updated_at`; caller-supplied `created_at`/`updated_at` on `ProfileCreate` are ignored; Unicode/emoji in skills/raw_cv preserved
- [ ] Gate check passes: `python -m pytest tests/test_profile_models.py -q --no-cov`
- [ ] Test count: ~6 new tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(models): add canonical Profile model and new_from factory`
**Status**: Complete

---

### T3: Add `ProfileRepository` port, sqlite adapter, fake, and contract test

**What**: The `ProfileRepository` Protocol, `SqliteProfileRepository` (single-row `CHECK(id=1)` schema, atomic `ON CONFLICT DO UPDATE` upsert, `get`, JSON-in-TEXT for `skills`/`salary_expectation`/`location`), a `FakeProfileRepository` test double, and a parametrized port contract test.
**Where**: `src/jobpilot/repository.py` (append; test double added to tests/fakes.py)
**Depends on**: T2
**Reuses**: `Profile` (T2), the existing `RepositoryError` (`repository.py:34`), the `Job` adapter's JSON-in-TEXT technique; stdlib `sqlite3`, `json`
**Requirement**: BCP-04, BCP-05, BCP-07, BCP-16, BCP-17, BCP-18, BCP-20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `ProfileRepository(Protocol)` with `get() -> Profile | None`, `upsert(profile) -> Profile`
- [ ] `SqliteProfileRepository` creates the schema idempotently (`profile` table, `id INTEGER PRIMARY KEY CHECK (id = 1)`); `upsert` writes the single row via `INSERT ... ON CONFLICT(id) DO UPDATE` + commit; on `sqlite3.Error` rolls back and raises the shared `RepositoryError` (prior row intact)
- [ ] `skills`, `salary_expectation`, `location` round-trip through `json.dumps`/`loads`; absent `location` stored as `NULL`; empty `salary_expectation` stored as `[]`
- [ ] `FakeProfileRepository` (in-memory) added to `tests/fakes.py` as a faithful double for T4's injection
- [ ] **Port contract test** (`pytest.mark.parametrize` over `SqliteProfileRepository(:memory:)` **and** `FakeProfileRepository`) asserts identical behavior: `get()` on empty → `None`; `upsert` then `get` returns an equal `Profile`; a second `upsert` replaces (one logical profile, `created_at` preserved by the caller-passed value, fields overwritten); salary/skills/location survive roundtrip. Both impls MUST pass the same assertions
- [ ] Sqlite-only integration tests additionally cover: forced failure (e.g. closed/broken conn) → `RepositoryError` **and** the previously stored profile unchanged (atomicity, BCP-16/-17); the `CHECK(id=1)` invariant keeps a single row across repeated upserts
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~12 tests pass (contract suite ×2 impls + sqlite-only cases; no silent deletions)

**Tests**: integration
**Gate**: full

**Commit**: `feat(repository): add ProfileRepository port, sqlite adapter, and contract test`
**Status**: Complete

---

### T4: Add profile endpoints behind the repository port

**What**: `routes/profile.py` with `PUT /profile` (create→201 / replace→200, `created_at` preserved) and `GET /profile` (200/404), the `get_profile_repository(request)` dependency, and in-route `RepositoryError → 500` with a generic body + `logger.exception`.
**Where**: `src/jobpilot/routes/profile.py`
**Depends on**: T3
**Reuses**: `ProfileCreate`/`Profile` (T1/T2), `ProfileRepository`/`RepositoryError` (T3), `FakeProfileRepository` from `tests/fakes.py` (T3, contract-tested), the M1 500-handling pattern (`routes/jobs.py:31-40`), FastAPI `APIRouter`
**Requirement**: BCP-01, BCP-02, BCP-07, BCP-08, BCP-09, BCP-10, BCP-11, BCP-12, BCP-13, BCP-15, BCP-16, BCP-17, BCP-21, BCP-22

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `PUT /profile` returns `201` + `Profile` when none existed, `200` + `Profile` on replace (route `get()`s first, sets `response.status_code = 201` on create, passes existing `created_at` into `Profile.new_from`)
- [ ] `GET /profile` returns `200` + `Profile` if a row exists, `404` with no body otherwise
- [ ] `get_profile_repository` resolves `request.app.state.profile_repo`; route catches `RepositoryError` → `500` with a **generic** body built from a constant (`{"detail": "internal error"}`), never `str(exc)`, and calls `logger.exception(...)`
- [ ] Tests (test-first) build an app including the router with `app.state.profile_repo = FakeProfileRepository()` (or a failing stub via override) and cover the **422 rejection matrix**: no/blank skills → 422 `loc` names `skills`; bad `seniority` → 422; bad salary range → 422; duplicate currency+contract → 422; `years_experience` out of range → 422; empty body → 422; non-JSON content-type → 422 (BCP-21)
- [ ] Tests cover happy + state: `PUT` create → 201; second `PUT` → 200 with `created_at` preserved and `updated_at` advanced; `GET` before any `PUT` → 404; `GET` after → 200 identical values; a rejected (422) replace leaves the prior profile unchanged (BCP-16)
- [ ] Repo-failure test asserts **both**: status `500` with nothing changed, **and** the body leaks no internals (no `Traceback`, no SQL, no exception message; body equals the generic constant); a `caplog` assertion proves the cause was logged at exception level with a traceback (BCP-22)
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~16 tests pass (no silent deletions)

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): add profile endpoints behind the repository port`
**Status**: Complete

---

### T5: Wire the sqlite profile repository and router into the app

**What**: Extend `create_app()` to build `SqliteProfileRepository` on the **same** connection, expose it on `app.state.profile_repo`, and `include_router(profile_router)`; add end-to-end tests through the real stack.
**Where**: `src/jobpilot/app.py` (modify; e2e tests extend tests/test_app_e2e.py)
**Depends on**: T4
**Reuses**: `create_app()` factory (`app.py:85`), the existing sqlite connection + `BodySizeLimitMiddleware` (reused unchanged — covers oversized `PUT /profile`), `SqliteProfileRepository` (T3), profile router (T4)
**Requirement**: BCP-01, BCP-02, BCP-05, BCP-07, BCP-08, BCP-13, BCP-16, BCP-17, BCP-18, BCP-22

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `create_app(db_path=":memory:")` yields a fully wired app exposing both `jobs` and `profile` routers; `profile_repo` shares the same connection as `repo`
- [ ] End-to-end tests via `TestClient(create_app(db_path=":memory:"))` cover the real stack: `PUT /profile` → 201 → `GET /profile` returns identical values (persistence proof, not echo); second `PUT` → 200 with `created_at` preserved and `updated_at` advanced; `GET` on a fresh store → 404 (empty state fails closed); an oversized `PUT` body (>50 KB) → 422 via the reused middleware, nothing persisted; Unicode/emoji round-trips through storage; a dependency-overridden failing `profile_repo` → 500 with the prior state unchanged and no leak
- [ ] `/health` and the M1 `jobs` routes still pass (no regression)
- [ ] Gate check passes: `python -m pytest` (Build — coverage gate ≥ 80% green with failing paths exercised)
- [ ] Test count: ~8 new tests pass (no silent deletions)

**Tests**: integration
**Gate**: build

**Commit**: `feat(app): wire sqlite profile repository and router into the app`
**Status**: Complete

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3

T1 → T2 → T3 → T4 → T5
```

Execution is strictly sequential. 5 tasks ≤ ~8 → single batch, inline execution, no sub-agents. A fresh Verifier still runs automatically after T5.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: value objects + ProfileCreate | input models + validators, 1 file (cohesive input layer) | ✅ Granular |
| T2: Profile model + factory | 1 model + factory, same file | ✅ Granular |
| T3: repository port + adapter + fake + contract test | 1 port + one adapter + its double/contract test (cohesive) | ✅ Granular |
| T4: profile endpoints | 1 router file (2 endpoints, one resource) | ✅ Granular |
| T5: app wiring | 1 file (`app.py`) + e2e | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | (start of Phase 1) | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T2 | T2 → T3 (Phase 2 start) | ✅ Match |
| T4 | T3 | T3 → T4 (Phase 3 start) | ✅ Match |
| T5 | T4 | T4 → T5 | ✅ Match |

All dependencies point backward. No forward-phase dependency; no `[P]` tasks (strictly sequential).

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Domain models | unit | unit | ✅ OK |
| T2 | Domain models | unit | unit | ✅ OK |
| T3 | Repository | integration | integration | ✅ OK |
| T4 | API routes | integration (e2e) | integration | ✅ OK |
| T5 | API app wiring | integration (e2e) | integration | ✅ OK |

No task defers its tests. Every code layer with a required test type writes those tests in the same task.

---

## Requirement Coverage (all 22 mapped to ≥1 task)

BCP-01→T2,T4,T5 · BCP-02→T2,T4,T5 · BCP-03→T1 · BCP-04→T1,T3 · BCP-05→T1,T3,T5 · BCP-06→T1,T2 · BCP-07→T3,T4,T5 · BCP-08→T4,T5 · BCP-09→T1,T4 · BCP-10→T1,T4 · BCP-11→T1,T4 · BCP-12→T1,T4 · BCP-13→T4,T5 · BCP-14→T1 · BCP-15→T1,T4 · BCP-16→T3,T4,T5 · BCP-17→T3,T4,T5 · BCP-18→T2,T3,T5 · BCP-19→T1 · BCP-20→T1,T3 · BCP-21→T4 · BCP-22→T4,T5
</content>
