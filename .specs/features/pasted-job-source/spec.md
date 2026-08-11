# PastedJobSource + canonical Job (M1) Specification

## Problem Statement

JobPilot needs its first end-to-end slice: a person pastes a job posting and it
becomes a persisted, canonical `Job`. Every later component (Matcher, Generator,
Queue) reads that canonical shape, so M1 fixes the contract. The hard part is not
storage — it is refusing to fabricate a `Job` from bad input. A garbage or
title-less paste must fail explicitly, never persist a plausible-looking
half-Job (the classic *fail-open*).

## Goals

- [ ] Define the canonical `Job` shape once, so downstream milestones never reshape it.
- [ ] Expose `PastedJobSource` as an HTTP endpoint that persists a `Job` to SQLite and reads it back.
- [ ] Every invalid paste (empty, blank required field, oversized, malformed link) returns an explicit error and persists nothing — proven on the failing path.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Fetching/crawling a pasted URL | Outbound HTTP is `ScraperJobSource` territory (M7+, opt-in); pulls ToS + network-failure risk into the MVP. |
| Intelligent extraction of title/company/requirements from a blob | No LLM until M3; heuristic parsing is the fail-open magnet this spec exists to avoid. |
| Deduplication / idempotency of repeated pastes | Dedup is an `ApplicationQueue` (M5) concern; M1 allows duplicates. |
| `status` lifecycle (`new`/`ready`/`sent`/`discarded`) | Status belongs to the queued *application* (M5), not the canonical `Job`. |
| Deletion / TTL / archival of Jobs | Data lifecycle handled with the queue (M5). |
| Authentication, rate limiting, multi-user | Personal single-user local tool (briefing §6). |
| Structured logging / `/metrics` | Observability is Fase 2; M1 emits explicit error bodies only. |
| `FeedJobSource` / `ScraperJobSource` adapters | Later milestones; M1 delivers the `JobSource` port + one adapter. |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Spec + gate artifacts live in `.specs/features/pasted-job-source/`, not `specs/active/` | Use `.specs/`; no `specs/active/` pointer (new repo, no prior convention) | The skill's deterministic gates (`validate_spec.py`, `validate_state.py`) only resolve `.specs/`; gate integrity is the anti-fail-open mechanism and outranks the browse-path preference | y |
| Input model is **hybrid** | Required `title`, `company`; optional `description`, `requirements`, `link` | Explicit validation on what defines a valid Job; raw text kept for the M3 matcher; no intelligent parsing pretended | y |
| A valid Job requires only `title` + `company` (description optional) | Persist Job even with empty description | Required set kept minimal and deterministic; a thin Job is valid input, not an error | y |
| `requirements` is an optional caller-supplied list, default empty | No auto-extraction in M1 | Extracting requirements from a blob is exactly the heuristic being avoided until the LLM (M3) exists | y |
| Pasted `link` is stored verbatim, never fetched | No outbound HTTP in M1 | Fetching = crawling = out of scope; keeps M1 free of external-dependency failure | y |
| No minimum-length rule on any field | Only "blank after trim" rejects; a 1-char non-blank title passes | "Blank" is a deterministic fail-open boundary; an arbitrary min length is just another heuristic | y |
| Duplicate pastes create distinct Jobs | Each paste = new row with its own id | Dedup deferred to M5 | y |
| `Job.id` is a server-generated UUID4 string | Not an autoincrement integer | Stable, non-enumerable, survives into the queue milestones | n |
| `Job.source` is the constant `"pasted"` | Set server-side, ignored if supplied by caller | The `JobSource` discriminator for this adapter | n |
| `Job.created_at` is a server-set UTC timestamp (ISO-8601) | Caller cannot set it | Deterministic provenance | n |
| Max request body size is 50 KB | Reject above the bound | Prevents runaway storage / abuse; concrete testable limit | n |
| A malformed `link` is stored as `null` with a warning, not rejected | Lenient — only `title`/`company` cause a 422 | `link` is optional and never fetched in M1; failing the whole request on an unused field is over-blocking | y |
| `title` and `company` are capped at 512 chars each (after trim) | Reject over-cap with 422 | Per-field cap so the 50 KB total-body bound can't smuggle a 40 KB title | y |
| Validation errors use the FastAPI/Pydantic default 422 envelope | `{"detail": [{"type","loc","msg","input"}]}`; tests assert on `loc`+`type`, not `msg` text | Native `RequestValidationError` shape, uniform across endpoints, matches schemathesis (Fase 2) | y |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Paste a job and persist a canonical Job ⭐ MVP

**User Story**: As the JobPilot user, I want to paste a job posting's fields and get a persisted canonical `Job`, so that later milestones have a stable record to match and generate against.

**Why P1**: This is the M1 vertical slice — without it there is no `Job` to build on.

**Acceptance Criteria** (each line is one EARS pattern):

1. WHEN a `POST /jobs` request has non-blank `title` and `company` THEN the system SHALL persist a canonical `Job` and return `201` with the Job including a server-generated `id`, `source="pasted"`, and `created_at`.  <!-- event-driven -->
2. The system SHALL set `Job.source` to `"pasted"` on every Job created via this adapter, ignoring any caller-supplied source.  <!-- ubiquitous -->
3. The system SHALL trim leading and trailing whitespace from `title`, `company`, and `description` before persisting.  <!-- ubiquitous -->
4. WHERE a `link` is present and well-formed the system SHALL store it verbatim and SHALL NOT perform any outbound HTTP request.  <!-- optional-feature -->
5. WHEN a `link` is present but malformed THEN the system SHALL store `link` as `null`, record a warning, and SHALL NOT reject the request.  <!-- event-driven; lenient — link is optional and never fetched in M1 -->
6. WHERE `description` or `requirements` is absent the system SHALL persist the Job with `description` empty and `requirements` an empty list.  <!-- optional-feature -->

**Independent Test**: `POST /jobs` with `{title, company, description}` returns `201` and a Job id; the Job is in SQLite with `source="pasted"` and a `created_at`.

---

### P1: Read a persisted Job back ⭐ MVP

**User Story**: As the JobPilot user, I want to fetch a Job by id, so that I can prove it was actually persisted and not merely echoed.

**Why P1**: Retrieval is the only way to distinguish "persisted" from "echoed"; it makes M1 testable end-to-end via Swagger.

**Acceptance Criteria**:

1. WHEN a `GET /jobs/{id}` request names an existing Job THEN the system SHALL return `200` with the full canonical Job.  <!-- event-driven -->
2. IF a `GET /jobs/{id}` request names an unknown id THEN the system SHALL return `404` and no Job body.  <!-- unwanted-behavior -->

**Independent Test**: Create a Job, then `GET /jobs/{that-id}` returns `200` with identical field values; a random id returns `404`.

---

### P1: Reject invalid pastes explicitly ⭐ MVP

**User Story**: As the JobPilot user, I want bad input rejected with a clear error, so that no half-filled Job ever enters the pipeline.

**Why P1**: This is the fail-open guard — the reason M1 exists in this shape.

**Acceptance Criteria**:

1. IF a `POST /jobs` request is missing `title` or `company`, or either is blank after trimming, THEN the system SHALL reject with `422`, name the failing field in the error body per the Error Response Contract, and SHALL NOT persist any Job.  <!-- unwanted-behavior -->
2. IF a `POST /jobs` request body is empty or whitespace-only THEN the system SHALL reject with `422` and SHALL NOT persist any Job.  <!-- unwanted-behavior -->
3. IF a `POST /jobs` request payload exceeds 50 KB THEN the system SHALL reject with `422` and SHALL NOT persist any Job.  <!-- unwanted-behavior -->
4. IF `title` or `company` exceeds 512 characters (after trimming) THEN the system SHALL reject with `422`, name the failing field, and SHALL NOT persist any Job.  <!-- unwanted-behavior; per-field cap so the 50 KB total bound can't smuggle a 40 KB title -->

**Independent Test**: Each invalid payload returns `422` with the contract body shape; a follow-up `GET /jobs` shows the store row count unchanged.

---

### P2: List persisted Jobs

**User Story**: As the JobPilot user, I want to list all persisted Jobs, so that I can see what the source has ingested so far.

**Why P2**: Useful for inspection and the future Report/UI, but not required to prove the M1 slice.

**Acceptance Criteria**:

1. WHEN a `GET /jobs` request is made THEN the system SHALL return `200` with the list of persisted Jobs ordered most-recent-first.  <!-- event-driven -->
2. WHILE no Jobs are persisted the system SHALL return `200` with an empty list, not an error.  <!-- state-driven -->

**Independent Test**: With N Jobs persisted, `GET /jobs` returns N items newest-first; with none, returns `[]`.

---

## Error Response Contract

All `422` validation rejections use the **FastAPI/Pydantic default envelope** —
no custom shape. Chosen over a custom `{"field", "message"}` because it is what
`RequestValidationError` emits natively, keeps every endpoint uniform, and is
the exact shape `schemathesis` asserts against in Fase 2. The failing field is
carried in `loc`; a test asserts on `loc` + `type`, not on the human `msg` text
(which is not part of the contract and may change across Pydantic versions).

Literal example — `POST /jobs` with `title` missing:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "title"],
      "msg": "Field required",
      "input": {"company": "Acme"}
    }
  ]
}
```

Literal example — `title` present but blank after trimming (custom validator):

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "title"],
      "msg": "Value error, must not be blank",
      "input": "   "
    }
  ]
}
```

Contract asserted by tests: status is `422`; `detail` is a non-empty list;
the offending entry's `loc` ends with the failing field name; `type` is
`missing` (absent field) or `value_error` (blank / over-cap). Body-too-large
and non-JSON rejections also surface as `422` with a `detail` list.

---

## Edge Cases

- IF a persistence write fails (SQLite error) THEN the system SHALL return `500`, SHALL NOT report success, and SHALL leave no partially-written Job (atomic write).  <!-- unwanted-behavior / partial-failure. Test seam: persistence sits behind a `JobRepository` port; the failing-path test injects a stub/mock repository whose `add()` raises, asserts the `500`, and asserts `GET /jobs` row count is unchanged. Design phase specifies the port. -->
- WHEN `title`/`company`/`description` contain Unicode or emoji THEN the system SHALL persist and return them byte-for-byte unchanged (after trim).  <!-- boundary -->
- WHEN the same posting is pasted twice THEN the system SHALL persist two distinct Jobs with different ids.  <!-- boundary; dedup out of scope -->
- IF the request `Content-Type` is not JSON THEN the system SHALL reject with `422` and SHALL NOT persist any Job.  <!-- unwanted-behavior -->
- WHEN a caller supplies `id`, `source`, or `created_at` THEN the system SHALL ignore them and use server-generated values.  <!-- boundary -->

---

## Requirement Traceability

Each requirement gets a unique ID for tracking across design, tasks, and validation.

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| PJS-01 | P1: Persist | Tasks | Implementing |
| PJS-02 | P1: Persist | Tasks | Implementing |
| PJS-03 | P1: Persist | Tasks | Implementing |
| PJS-04 | P1: Persist | Tasks | Implementing |
| PJS-05 | P1: Persist | Tasks | Implementing |
| PJS-06 | P1: Read back | Tasks | Implementing |
| PJS-07 | P1: Read back | Tasks | Implementing |
| PJS-08 | P1: Reject | Tasks | Implementing |
| PJS-09 | P1: Reject | Tasks | Implementing |
| PJS-10 | P1: Reject | Tasks | Implementing |
| PJS-11 | P1: Persist (malformed link → null + warning, lenient) | Tasks | Implementing |
| PJS-12 | P2: List | Tasks | Implementing |
| PJS-13 | P2: List | Tasks | Implementing |
| PJS-14 | Edge: atomic write failure | Tasks | Implementing |
| PJS-15 | Edge: Unicode preserved | Tasks | Implementing |
| PJS-16 | Edge: duplicate pastes distinct | Tasks | Implementing |
| PJS-17 | Edge: non-JSON content-type | Tasks | Implementing |
| PJS-18 | Edge: server-owned fields ignored | Tasks | Implementing |
| PJS-19 | P1: Reject (title/company > 512 chars) | Tasks | Implementing |

**ID format:** `PJS-[NUMBER]` (PastedJobSource).

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 19 total, 0 mapped to tasks yet, 19 pending.

---

## Success Criteria

How we know the feature is successful:

- [ ] A pasted `{title, company, description}` becomes a persisted Job retrievable by id, with `source="pasted"` and a `created_at`.
- [ ] Every invalid-paste class (empty, blank required, oversized, malformed link, non-JSON) returns the specified error code and leaves the store row count unchanged — verified on the failing path, not only the happy path.
- [ ] No outbound HTTP request is made when a `link` is supplied.
- [ ] Coverage gate (`--cov-fail-under=80`) stays green with the failing paths exercised.
