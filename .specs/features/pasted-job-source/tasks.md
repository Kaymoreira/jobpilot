# PastedJobSource + canonical Job (M1) Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/pasted-job-source/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `CONTRIBUTING.md` (test-first; happy **and** failing path; coverage gate), `pyproject.toml` (`--cov-fail-under=80`, branch coverage), sample test `tests/test_health.py` (`TestClient(create_app())`). No `mypy`/`ruff` configured yet, so the gate is `pytest` + coverage only.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain models (`models.py` - `JobCreate` validators, `Job`, `new_from`) | unit | All branches; 1:1 to spec ACs; every listed edge case has a test | `tests/test_models.py` | `python -m pytest` |
| Repository (`repository.py` - `SqliteJobRepository`) | integration | Key query paths (add/get/list roundtrip, JSON requirements) + error/atomicity path | `tests/test_repository.py` | `python -m pytest` |
| API routes + app wiring (`routes/jobs.py`, `app.py`) | integration (e2e via `TestClient`) | All routes: happy + every listed edge case + error/failure paths | `tests/test_jobs_api.py`, `tests/test_body_limit.py` | `python -m pytest` |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (models) - fast, no coverage bar | `python -m pytest tests/test_models.py -q --no-cov` |
| Full | After integration/e2e tasks | `python -m pytest -q` |
| Build | After the final task / phase completion - enforces the 80% coverage gate | `python -m pytest` |

> Full and Build run the same suite; Build is called out because `--cov-fail-under=80` (in `pyproject.toml` `addopts`) must be green at the end with the failing paths exercised.

---

## Execution Plan

Phases are ordered and run sequentially - each phase completes before the next begins, and tasks within a phase execute in order. 6 tasks total → single batch, executed inline (no sub-agents).

### Phase 1: Domain models

```
T1 → T2
```

### Phase 2: Persistence port + adapter

```
T2 → T3
```

### Phase 3: API + app wiring

```
T3 → T4 → T5 → T6
```

---

## Task Breakdown

### T1: Add validated `JobCreate` input model

**What**: The Pydantic input model for a pasted job with all field validation (trim; non-blank + ≤512 for `title`/`company`; lenient link).
**Where**: `src/jobpilot/models.py`
**Depends on**: None
**Reuses**: Pydantic (transitive via FastAPI); `logging` stdlib
**Requirement**: PJS-03, PJS-04, PJS-08, PJS-11, PJS-18, PJS-19

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `JobCreate` defines `title`, `company` (required), `description`, `requirements` (default `[]`), `link` (default `None`)
- [ ] Validators: strip whitespace on `title`/`company`/`description`; blank `title`/`company` raises `value_error`; `title`/`company` > 512 chars (after trim) raises; malformed `link` coerced to `None` with a `logger.warning`, never raises
- [ ] Unknown fields (`id`/`source`/`created_at`) are dropped, not stored
- [ ] Unit tests cover: trim, blank→error (both fields), >512→error, valid link kept, malformed link→None+warning, unknown fields dropped
- [ ] Gate check passes: `python -m pytest tests/test_models.py -q --no-cov`
- [ ] Test count: ~8 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(models): add validated JobCreate input model`
**Status**: ✅ Complete (12 tests)

---

### T2: Add canonical `Job` model and `new_from` factory

**What**: The canonical stored/response `Job` model plus `Job.new_from(JobCreate)` that server-generates `id`/`source`/`created_at` and normalizes defaults.
**Where**: `src/jobpilot/models.py` (modify)
**Depends on**: T1
**Reuses**: `JobCreate` from T1; stdlib `uuid`, `datetime`
**Requirement**: PJS-02, PJS-05, PJS-07, PJS-13, PJS-15, PJS-16

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `Job` has `id`, `source: Literal["pasted"]="pasted"`, `title`, `company`, `description=""`, `requirements=[]`, `link=None`, `created_at`
- [ ] `Job.new_from` sets `id=uuid4().hex`, `created_at=datetime.now(UTC)`, `source="pasted"`, normalizes absent `description` to `""`
- [ ] Unit tests cover: source is always `"pasted"`; absent description/requirements → `""`/`[]`; two calls yield distinct ids (PJS-16); Unicode/emoji preserved (PJS-15); `created_at` is timezone-aware UTC
- [ ] Gate check passes: `python -m pytest tests/test_models.py -q --no-cov`
- [ ] Test count: ~6 new tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(models): add canonical Job model and new_from factory`
**Status**: ✅ Complete (7 tests)

---

### T3: Add `JobRepository` port and sqlite adapter

**What**: The `JobRepository` Protocol, `RepositoryError`, and `SqliteJobRepository` (schema init, atomic add, get, newest-first list, `requirements` as JSON TEXT).
**Where**: `src/jobpilot/repository.py`
**Depends on**: T2
**Reuses**: `Job` from T2; stdlib `sqlite3`, `json`
**Requirement**: PJS-06, PJS-12, PJS-13, PJS-14, PJS-16

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `JobRepository(Protocol)` with `add`, `get`, `list_all`; `RepositoryError(Exception)` defined
- [ ] `SqliteJobRepository` creates the schema idempotently; `add` inserts + commits, and on `sqlite3.Error` rolls back and raises `RepositoryError` (nothing committed)
- [ ] `list_all` returns newest-first; `requirements` round-trips through `json.dumps`/`loads`
- [ ] `FakeJobRepository` (in-memory `dict`-backed) added as an importable test helper in `tests/fakes.py`, so T4's injection uses a faithful double, not an ad-hoc one
- [ ] **Port contract test** (`pytest.mark.parametrize` over `SqliteJobRepository(:memory:)` **and** `FakeJobRepository`) asserts identical behavior on the same suite: add→get roundtrip returns an equal `Job`; get unknown → `None`; `list_all` newest-first; empty → `[]`; requirements survive roundtrip. Both implementations MUST pass the same assertions — the Fake cannot diverge from the real
- [ ] Sqlite-only integration tests additionally cover: two adds → two distinct rows; forced failure → `RepositoryError` **and** row count unchanged (atomicity)
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~11 tests pass (contract suite ×2 impls + sqlite-only cases; no silent deletions)

**Tests**: integration
**Gate**: full

**Commit**: `feat(repository): add JobRepository port and sqlite adapter`

---

### T4: Add jobs endpoints behind the repository port

**What**: `routes/jobs.py` with `POST /jobs`, `GET /jobs/{id}`, `GET /jobs`, the `get_repository(request)` dependency (reads `request.app.state.repo`), and in-route `RepositoryError → 500`.
**Where**: `src/jobpilot/routes/jobs.py`
**Depends on**: T3
**Reuses**: `JobCreate`/`Job` (T1/T2), `JobRepository`/`RepositoryError` (T3), `FakeJobRepository` from `tests/fakes.py` (T3, contract-tested), FastAPI `APIRouter`
**Requirement**: PJS-01, PJS-06, PJS-07, PJS-08, PJS-09, PJS-11, PJS-12, PJS-14, PJS-17, PJS-18, PJS-19

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `POST /jobs` → `201` with the canonical `Job`; `GET /jobs/{id}` → `200`/`404`; `GET /jobs` → `200` list
- [ ] `get_repository` resolves `request.app.state.repo`; route catches `RepositoryError` → `500` and returns a **generic** body (e.g. `{"detail": "internal error"}`) built from a constant, never from `str(exc)`
- [ ] Tests build an app that includes the router and set `app.state.repo` to `FakeJobRepository` (happy path) or a failing stub via override, and cover: 201 happy + read-back; missing/blank title → 422 with `detail[].loc` naming the field; empty/non-JSON body → 422; malformed link → 201 with `link:null`; >512 → 422; caller-supplied `id`/`source` ignored; unknown id → 404; list newest-first
- [ ] Repo-failure test asserts **both**: status is `500` with nothing persisted, **and** the response body does not leak internals — no stacktrace/`Traceback`, no SQL, no exception message; the serialized body equals the generic constant
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~13 tests pass (no silent deletions)

**Tests**: integration
**Gate**: full

**Commit**: `feat(api): add jobs endpoints behind the repository port`

---

### T5: Wire the sqlite repository and jobs router into the app

**What**: Extend `create_app()` to open the sqlite connection (`check_same_thread=False`, path from `JOBPILOT_DB` env / `create_app(db_path=...)` param, default `jobpilot.db`), build `SqliteJobRepository` on `app.state.repo`, and `include_router` — plus gitignore the db file.
**Where**: `src/jobpilot/app.py` (modify)
**Depends on**: T4
**Reuses**: `create_app()` factory (`app.py:13`), `SqliteJobRepository` (T3), jobs router (T4)
**Requirement**: PJS-01, PJS-07, PJS-12, PJS-14, PJS-15, PJS-16

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `create_app(db_path=":memory:")` yields a fully wired app; default path is `jobpilot.db`; `*.db` is gitignored
- [ ] End-to-end tests via `TestClient(create_app(db_path=":memory:"))` cover the real stack: paste → 201 → `GET /jobs/{id}` returns identical values (persistence proof, not echo); duplicate paste → two rows; list newest-first; empty list; Unicode preserved through storage; a dependency-overridden failing repo → 500 with row count unchanged
- [ ] `/health` still returns 200 (no regression)
- [ ] Gate check passes: `python -m pytest -q`
- [ ] Test count: ~8 tests pass (no silent deletions)

**Tests**: integration
**Gate**: full

**Commit**: `feat(app): wire sqlite repository and jobs router into the app`

---

### T6: Reject oversized request bodies before parsing

**What**: An app-level guard (middleware) that rejects request bodies over 50 KB with `422`, reading at most 50 KB + 1 rather than trusting `Content-Length`.
**Where**: `src/jobpilot/app.py` (modify)
**Depends on**: T5
**Reuses**: `create_app()` wiring (T5), Starlette middleware
**Requirement**: PJS-10

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Bodies > 50 KB are rejected with `422` before route/validation runs; nothing is persisted
- [ ] The guard does not trust `Content-Length` alone (caps the actual read)
- [ ] Tests cover: >50 KB body → 422; >50 KB body with a **lying small `Content-Length`** → still 422; a normal-size paste still → 201; row count unchanged after each rejection
- [ ] Gate check passes: `python -m pytest` (Build - coverage gate ≥ 80% green with failing paths exercised)
- [ ] Test count: ~4 tests pass (no silent deletions)

**Tests**: integration
**Gate**: build

**Commit**: `feat(app): reject oversized request bodies before parsing`

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3

T1 → T2 → T3 → T4 → T5 → T6
```

Execution is strictly sequential. 6 tasks ≤ ~8 → single batch, inline execution, no sub-agents. A fresh Verifier still runs automatically after T6.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: JobCreate input model | 1 model + validators, 1 file | ✅ Granular |
| T2: Job model + factory | 1 model + factory, same file | ✅ Granular |
| T3: Repository port + adapter | 1 file (port + one adapter, cohesive) | ✅ Granular |
| T4: jobs endpoints | 1 router file (3 endpoints, one resource) | ✅ Granular |
| T5: app wiring | 1 file (`app.py`) | ✅ Granular |
| T6: body-size guard | 1 file (`app.py`) | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | (start of Phase 1) | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T2 | T2 → T3 (Phase 2 start) | ✅ Match |
| T4 | T3 | T3 → T4 (Phase 3 start) | ✅ Match |
| T5 | T4 | T4 → T5 | ✅ Match |
| T6 | T5 | T5 → T6 | ✅ Match |

All dependencies point backward or within-phase. No forward-phase dependency.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | Domain models | unit | unit | ✅ OK |
| T2 | Domain models | unit | unit | ✅ OK |
| T3 | Repository | integration | integration | ✅ OK |
| T4 | API routes | integration (e2e) | integration | ✅ OK |
| T5 | API app wiring | integration (e2e) | integration | ✅ OK |
| T6 | API app wiring | integration (e2e) | integration | ✅ OK |

No task defers its tests. Every code layer with a required test type writes those tests in the same task.

---

## Requirement Coverage (all 19 mapped to ≥1 task)

PJS-01→T4,T5 · PJS-02→T2,T4 · PJS-03→T1 · PJS-04→T1 · PJS-05→T1,T2 · PJS-06→T3,T4 · PJS-07→T4,T5 · PJS-08→T1,T4 · PJS-09→T4 · PJS-10→T6 · PJS-11→T1,T4 · PJS-12→T3,T4,T5 · PJS-13→T2,T3 · PJS-14→T3,T4,T5 · PJS-15→T2,T5 · PJS-16→T2,T3,T5 · PJS-17→T4 · PJS-18→T1,T4 · PJS-19→T1,T4
