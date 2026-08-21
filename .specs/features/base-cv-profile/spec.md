# Base CV / Structured Profile (M2) Specification

## Problem Statement

JobPilot has a canonical `Job` (M1) but nothing to match it *against*. M2 adds the
other half of the matching contract: a persisted, structured **candidate profile**
(skills, seniority, salary expectation, location). The hard part is not storage —
it is refusing to fabricate a profile from a document. The candidate authors the
profile as structured data; the system validates and persists it. "Reading the CV
and extracting a profile" by heuristic is the classic *fail-open* magnet (a
silently-wrong profile poisons every downstream `MatchResult`) and is deferred to
M3, where the LLM and an eval harness exist to do it honestly. M2 also stores the
raw CV text verbatim (never parsed) as raw material for the M4 Generator.

## Goals

- [ ] Define the canonical `Profile` shape once, so the Matcher (M3) and Generator (M4) read a stable contract.
- [ ] Expose a single-profile HTTP surface (`PUT /profile` to author/replace, `GET /profile` to read back) persisted to SQLite.
- [ ] Every invalid profile (no skills, no seniority, bad seniority value, malformed salary range, oversized) returns an explicit error and persists nothing — proven on the failing path.
- [ ] The empty state (no profile authored yet) is explicit: `GET /profile` returns `404`, never a `200` with a hollow profile.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Extracting skills/seniority/salary from a CV file (HTML/PDF/DOCX) | Heuristic extraction is the fail-open magnet M2 exists to avoid; real extraction needs the LLM + an eval harness (M3). Contradicts AD-002. |
| Structured work history, education, certifications | These are Generator (M4) inputs; they produce far better output via the LLM than via a rigid hand-authored model. M2 keeps the raw CV text for that. |
| Multiple / named profiles (e.g. "QA" vs "SDET" variants) | Single-user personal tool (briefing §6); one canonical profile keeps the empty-state contract unambiguous. Variants deferred if ever needed. |
| Deletion / history / versioning of the profile | Data lifecycle handled later; M2 `PUT` is upsert-replace only. |
| Auth, rate limiting, multi-user | Personal single-user local tool (briefing §6). |
| Salary currency conversion or "is this offer good?" logic | Comparison against a job lives in the Matcher (M3); M2 only stores the expectation. |
| Interpreting free-text seniority ("sr.", "mid-level") | Interpretation without the LLM is heuristic; seniority is a closed enum instead. |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Profile is **authored as structured data**, not extracted from a document | Caller sends structured JSON; M2 validates + persists | Mirrors M1's `PastedJobSource`; no heuristic parsing until the LLM (M3); anti-fail-open (AD-002) | y |
| **One** canonical profile, not many | Single row; `PUT`/`GET /profile` (no id) | Single-user tool (briefing §6); keeps the empty-state contract unambiguous | y |
| Empty state is `404`, not `200` with a hollow profile | `GET /profile` → `404` until one is authored | Absence ≠ empty; a `200` hollow profile lets the M3 Matcher think it has a basis to score → fail-open | y |
| Minimum valid profile = **≥1 non-blank skill AND a seniority** | Both required; everything else optional | A profile with no skills or no level is a draft, not a matchable profile; salary/location absence is an honest state | y |
| `seniority` is a **closed enum** | `junior` \| `pleno` \| `pleno-senior` \| `senior`; other value → 422 | The Matcher compares levels deterministically; free-text forces heuristic interpretation (fail-open) | y |
| `salary_expectation` is a **list of ranges keyed by (currency, contract)** | Each entry: `currency`, `contract`, `floor`, `target`, `ceiling`; absent combos = indeterminate | "Not defined for PJ/USD" is a first-class state; a single number lets the Matcher read `null`/`0` as "any salary ok" (fail-open) | y |
| `salary_expectation` is **optional** (may be absent entirely) | Absent → Matcher treats every currency/contract as indeterminate | Salary is not part of "matchable"; forcing it would fabricate a floor | y |
| Raw CV text stored **verbatim, never parsed** in M2 | Optional `raw_cv` string, capped, stored as-is | Matches how `Job.description` is kept raw; feeds the M4 Generator without pretending to extract | y |
| `PUT /profile` is **upsert-replace** | First author → `201`; subsequent → `200`; full replace (not merge) | Single profile; partial-merge semantics would silently keep stale fields | n |
| `skills` are trimmed, blanks dropped, de-duplicated (case-insensitive), order preserved | Server-side normalization before persist | Deterministic storage; a list `["k6","","k6"]` is one skill, not three | n |
| Per-item caps: skill ≤ 128 chars; free-text fields ≤ 512 chars; `raw_cv` ≤ 50 KB | Reject over-cap with 422 | Concrete testable bounds; mirrors M1's per-field cap so the body limit can't smuggle a huge field | n |
| Max request body size is 50 KB (reuses M1's `BodySizeLimitMiddleware`) | Reject above the bound with 422 | Same abuse bound as M1; one middleware for the app | n |
| `years_experience` optional, integer `0..60` | Absent allowed; out-of-range → 422 | Supports the "8+ years / Staff = no match" dealbreaker without inventing a value | n |
| `created_at` / `updated_at` are server-owned (UTC ISO-8601) | Caller cannot set them | Deterministic provenance; `updated_at` changes on every replace | n |
| Validation errors use the FastAPI/Pydantic default 422 envelope | `{"detail":[{"type","loc","msg","input"}]}`; tests assert on `loc`+`type`, not `msg` | Same contract as M1 (AD-005); uniform, matches schemathesis (Fase 2) | y |

**Open questions:** none blocking — items marked `n` are safe defaults inherited from M1 conventions, confirmable at Design.

---

## User Stories

### P1: Author the base profile ⭐ MVP

**User Story**: As the JobPilot user, I want to submit my structured profile (skills, seniority, and optionally salary/location/raw CV) and get it persisted, so that the Matcher (M3) has a stable basis to score jobs against.

**Why P1**: Without a persisted profile there is nothing to match a `Job` against; this is the M2 vertical slice.

**Acceptance Criteria** (each line is one EARS pattern):

1. WHEN a `PUT /profile` request has ≥1 non-blank `skill` and a valid `seniority` and no profile exists yet THEN the system SHALL persist the canonical `Profile` and return `201` with the stored profile including server-set `created_at` and `updated_at`.  <!-- event-driven -->
2. WHEN a `PUT /profile` request is valid and a profile already exists THEN the system SHALL fully replace it and return `200` with the stored profile and a new `updated_at`.  <!-- event-driven; upsert-replace, not merge -->
3. The system SHALL trim each skill, drop blank skills, and de-duplicate skills case-insensitively while preserving first-seen order before persisting.  <!-- ubiquitous -->
4. WHERE `salary_expectation`, `location`, `years_experience`, or `raw_cv` is absent the system SHALL persist the profile without them and SHALL NOT fabricate a default value.  <!-- optional-feature -->
5. WHERE `raw_cv` is present the system SHALL store it verbatim (byte-for-byte after trim) and SHALL NOT parse or extract from it.  <!-- optional-feature -->
6. WHEN a caller supplies `created_at` or `updated_at` THEN the system SHALL ignore them and use server-generated values.  <!-- boundary -->

**Independent Test**: `PUT /profile` with `{skills:["k6"], seniority:"pleno-senior"}` returns `201`; a second valid `PUT` returns `200` with a changed `updated_at`; the row in SQLite reflects the latest payload only.

---

### P1: Read the profile back ⭐ MVP

**User Story**: As the JobPilot user, I want to fetch the persisted profile, so that I can prove it was stored and the Matcher can load it.

**Why P1**: Retrieval distinguishes "persisted" from "echoed" and makes M2 testable end-to-end via Swagger.

**Acceptance Criteria**:

1. WHEN a `GET /profile` request is made and a profile exists THEN the system SHALL return `200` with the full canonical `Profile`.  <!-- event-driven -->
2. IF a `GET /profile` request is made and no profile has been authored THEN the system SHALL return `404` and no profile body.  <!-- unwanted-behavior; empty state fails closed, never a hollow 200 -->

**Independent Test**: On a fresh store, `GET /profile` returns `404`; after a valid `PUT`, `GET /profile` returns `200` with identical field values.

---

### P1: Reject invalid profiles explicitly ⭐ MVP

**User Story**: As the JobPilot user, I want a profile with no skills, no seniority, a bad seniority value, or a malformed salary range rejected with a clear error, so that no hollow or nonsensical profile ever reaches the Matcher.

**Why P1**: This is the fail-open guard — the reason M2 exists in this shape.

**Acceptance Criteria**:

1. IF a `PUT /profile` request has an empty `skills` list, or every skill is blank after trimming, THEN the system SHALL reject with `422`, name `skills` per the Error Response Contract, and SHALL NOT persist or modify any profile.  <!-- unwanted-behavior -->
2. IF a `PUT /profile` request is missing `seniority` or `seniority` is not one of the allowed enum values THEN the system SHALL reject with `422`, name `seniority`, and SHALL NOT persist or modify any profile.  <!-- unwanted-behavior -->
3. IF a `salary_expectation` entry has `floor`/`target`/`ceiling` not satisfying `floor ≤ target ≤ ceiling`, or any value ≤ 0, THEN the system SHALL reject with `422` naming the entry and SHALL NOT persist.  <!-- unwanted-behavior -->
4. IF `salary_expectation` contains two entries with the same `(currency, contract)` pair THEN the system SHALL reject with `422` (ambiguous expectation) and SHALL NOT persist.  <!-- unwanted-behavior -->
5. IF the request body is empty/whitespace-only, is not JSON, or exceeds 50 KB THEN the system SHALL reject with `422` and SHALL NOT persist or modify any profile.  <!-- unwanted-behavior -->
6. IF any skill exceeds 128 chars, a free-text field exceeds 512 chars, or `raw_cv` exceeds 50 KB (after trim) THEN the system SHALL reject with `422` naming the field and SHALL NOT persist.  <!-- unwanted-behavior; per-field caps -->
7. IF `years_experience` is present and is not an integer in `0..60` THEN the system SHALL reject with `422` naming the field and SHALL NOT persist.  <!-- unwanted-behavior -->

**Independent Test**: Each invalid payload returns `422` with the contract body shape; a follow-up `GET /profile` is unchanged (still `404` on a fresh store, or still the prior profile on an existing one — a rejected replace never mutates state).

---

## Error Response Contract

All `422` validation rejections use the **FastAPI/Pydantic default envelope** — no
custom shape — identical to M1 (AD-005). The failing field is carried in `loc`; a
test asserts on `loc` + `type`, not on the human `msg` text. `type` is `missing`
(absent required field), `value_error` (blank / bad enum / bad range / over-cap),
or the Pydantic literal/int types for enum/`years_experience`. Body-too-large and
non-JSON rejections also surface as `422` with a `detail` list.

Literal example — `seniority` present but not an allowed value:

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "seniority"],
      "msg": "Input should be 'junior', 'pleno', 'pleno-senior' or 'senior'",
      "input": "SDET III"
    }
  ]
}
```

Contract asserted by tests: status is `422`; `detail` is a non-empty list; the
offending entry's `loc` ends with the failing field name; `type` matches the class
above.

---

## Edge Cases

- WHEN a valid replace (`PUT`) is followed by an *invalid* `PUT` THEN the system SHALL keep the previously stored profile unchanged (a rejected replace is not a partial write).  <!-- unwanted-behavior / partial-failure -->
- IF a persistence write fails (SQLite error) THEN the system SHALL return `500`, SHALL NOT report success, and SHALL leave the prior profile (or the empty state) unchanged.  <!-- partial-failure. Test seam: persistence behind a `ProfileRepository` port; inject a stub whose upsert raises, assert 500 + GET unchanged. Mirrors AD-006. -->
- WHEN a persistence write fails THEN the `500` response SHALL use a generic body (e.g. `{"detail": "internal error"}`) that leaks no SQL, stack trace, or other internal detail, AND the system SHALL log the real cause with its traceback server-side (`logger.exception`).  <!-- unwanted-behavior / info-leak + diagnosability. Mirrors M1 final (commit e897aa0): INTERNAL_ERROR_BODY + logger.exception. Client gets the generic body; the incident stays diagnosable in the server log. -->
- WHEN `skills` or `raw_cv` contain Unicode or emoji THEN the system SHALL persist and return them byte-for-byte unchanged (after trim).  <!-- boundary -->
- WHEN `skills` contains duplicates differing only by case/whitespace (`" k6 "`, `"K6"`) THEN the system SHALL store a single normalized entry.  <!-- boundary -->
- WHEN `salary_expectation` is an empty list `[]` THEN the system SHALL treat it as "no expectation stated" (persist as absent), not an error.  <!-- boundary -->
- IF the request `Content-Type` is not JSON THEN the system SHALL reject with `422` and SHALL NOT persist.  <!-- unwanted-behavior -->

---

## Requirement Traceability

Each requirement gets a unique ID for tracking across design, tasks, and validation.

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| BCP-01 | P1: Author (create → 201) | Execute | Verified |
| BCP-02 | P1: Author (replace → 200) | Execute | Verified |
| BCP-03 | P1: Author (skill normalization) | Execute | Verified |
| BCP-04 | P1: Author (optional fields not fabricated) | Execute | Verified |
| BCP-05 | P1: Author (raw_cv verbatim, unparsed) | Execute | Verified |
| BCP-06 | P1: Author (server-owned fields ignored) | Execute | Verified |
| BCP-07 | P1: Read back (200 with profile) | Execute | Verified |
| BCP-08 | P1: Read back (404 empty state) | Execute | Verified |
| BCP-09 | P1: Reject (no/blank skills) | Execute | Verified |
| BCP-10 | P1: Reject (missing/invalid seniority) | Execute | Verified |
| BCP-11 | P1: Reject (bad salary range) | Execute | Verified |
| BCP-12 | P1: Reject (duplicate currency/contract) | Execute | Verified |
| BCP-13 | P1: Reject (empty/non-JSON/oversized body) | Execute | Verified |
| BCP-14 | P1: Reject (per-field over-cap) | Execute | Verified |
| BCP-15 | P1: Reject (years_experience out of range) | Execute | Verified |
| BCP-16 | Edge: rejected replace keeps prior profile | Execute | Verified |
| BCP-17 | Edge: atomic write failure → 500, unchanged | Execute | Verified |
| BCP-18 | Edge: Unicode/emoji preserved | Execute | Verified |
| BCP-19 | Edge: case/whitespace skill dedup | Execute | Verified |
| BCP-20 | Edge: empty salary list = absent, not error | Execute | Verified |
| BCP-21 | Edge: non-JSON content-type → 422 | Execute | Verified |
| BCP-22 | Edge: 500 generic body (no leak) + server-side log of cause | Execute | Verified |

**ID format:** `BCP-[NUMBER]` (Base CV Profile).

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 22 total, all mapped to tasks T1–T5, all Verified (Execute + sensor PASS).

---

## Success Criteria

How we know the feature is successful:

- [ ] A `PUT /profile` with skills + seniority becomes a persisted `Profile` retrievable by `GET /profile`, with server-set `created_at`/`updated_at`.
- [ ] `GET /profile` returns `404` on a fresh store — the empty state fails closed, verified on the failing path.
- [ ] Every invalid-profile class (no skills, bad seniority, bad salary range, duplicate salary key, oversized, over-cap, out-of-range experience) returns `422` and leaves state unchanged — verified on the failing path, not only the happy path.
- [ ] A rejected replace never mutates the previously stored profile.
- [ ] A persistence failure returns `500` with a generic body (no SQL/stack-trace leak) while the real cause is logged server-side — verified with an injected failing repository and a caplog assertion, mirroring M1.
- [ ] `raw_cv` is stored and returned verbatim; nothing is extracted from it.
- [ ] Coverage gate (`--cov-fail-under=80`) stays green with the failing paths exercised.
</content>
</invoke>
