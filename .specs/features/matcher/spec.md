# Matcher (M3) Specification

## Problem Statement

JobPilot has a canonical `Job` (M1) and a canonical `Profile` (M2) but no way to
judge one against the other. M3 adds the **Matcher**: given the stored `Profile`
and a stored `Job`, it produces a `MatchResult` — a bounded score, a derived
verdict, a list of gaps, and a short rationale. This is the **first component
that uses an LLM**, so the milestone is really about *doing AI safely*: the model
advises, the human decides; uncertainty must fail closed (never a silent high
score); the judgment must be grounded only in the stored Profile and Job (no
fabricated skills); and the non-deterministic output must still be testable, via
a deterministic seam for unit tests and an offline eval harness for the real
model. Getting scoring *right* is the point; caching, ranking, and autonomy are
deliberately later.

## Goals

- [ ] Define the canonical `MatchResult` contract once (bounded score, closed verdict enum, gaps, rationale), so downstream (M4 Generator, M5 Queue) reads a stable shape.
- [ ] Expose `POST /jobs/{job_id}/match`: read the Job + the singleton Profile, call the LLM behind a port, and return an **advisory** `MatchResult` — synchronous, ephemeral, side-effect-free.
- [ ] Make fail-open impossible by construction: every uncertainty (absent Profile, LLM error/timeout, malformed output, out-of-range score) yields `verdict = cannot_assess` + `score = null`, never a high/passing score — proven on the failing path.
- [ ] Ship a deterministic seam (LLM behind a port) so the fail-open paths are unit-tested against a fake, in the coverage gate.
- [ ] Ship a minimal-but-real offline eval harness (human-labeled corpus + metrics) so the real model's quality is *measured*, not asserted.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Persisting the `MatchResult` / caching scores | Deferred to M5, where the queue is the real consumer. Storing now introduces a stale-score fail-open (Profile changes, stored score does not) with no consumer to justify it — YAGNI. |
| LLM provider / model choice | A Design decision (via the `claude-api` skill, default the latest Claude model). Specify defines behavior, not the vendor. |
| Retry / backoff on LLM failure | MVP fails closed on the first failure; retry adds nondeterminism and masks a flaky provider (a soft fail-open). Tuning deferred to Design. |
| Batch / scheduled matching (score many jobs unattended) | M6 (autonomy); M3 scores one job per explicit request. |
| Ranking / sorting multiple jobs by score | M5 (queue); needs persistence first. |
| Editing the `Job` or the `Profile` | Owned by M1 / M2 respectively. |
| Auto-apply, sending, marking, or any queue mutation from a score | The core product boundary — the submit is always the human's click (briefing §1). |
| UI for viewing / triggering matches | M5 (Report/UI). M3 is API-only, exercised via Swagger/Bruno and tests. |
| Fine-tuning / training / embeddings pipelines | Out of project scope; the Matcher uses a prompted general model. |
| Auth, rate limiting, multi-user | Personal single-user local tool (briefing §6). |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| `verdict` is a **closed enum** including an explicit uncertainty state | `strong` \| `possible` \| `weak` \| `cannot_assess` | "Couldn't evaluate" must be structurally distinct from "evaluated as weak", or fail-open sneaks back in (AD-015) | y |
| On **any** evaluation failure, `verdict = cannot_assess` **and `score = null`** (not `0`) | Absent Profile, LLM error/timeout, malformed output all route here | A `0` would make "bad fit" and "couldn't evaluate" the same output; `null` keeps them distinct. Downstream must handle null explicitly — intentional (AD-015) | y |
| `score` is an **integer 0–100** | Pydantic-bounded `ge=0, le=100` | Human-readable, matches briefing; avoids float-precision noise in tests | y |
| The **LLM returns score + rationale only**; the verdict is **derived** from score bands | Bands (proposed): `0–39 weak`, `40–74 possible`, `75–100 strong`; cutoffs finalized in Design | Single source of truth = the number, so score and verdict can never contradict; the band map is a pure, LLM-free unit-testable function (AD-016) | y |
| Invalid score **fails closed**, never clamps | Score outside `0..100`, wrong type, or missing/null where a number is required → `cannot_assess` | Clamping `150 → 100` is a silent fail-open; rejection is honest (AD-016) | y |
| Match is **synchronous + ephemeral** | `POST /jobs/{job_id}/match` runs the LLM and returns the `MatchResult` in the body; nothing is stored | Smallest honest slice; sidesteps the staleness fail-open entirely (AD-017) | y |
| Unknown `job_id` vs absent Profile are **deliberately asymmetric** | Unknown `job_id` → `404`; absent Profile → `200` with `cannot_assess` | The addressed resource (the job) genuinely doesn't exist → `404`. An absent Profile is "no basis to judge", not "not found" → `cannot_assess` (AD-017) | y |
| `MatchResult` carries a structured **`gaps: list[str]`** | Job requirements with no evidence in the Profile | Turns "no fabrication" from a hope into a red/green test (probe: missing skill must appear in `gaps` AND verdict ≠ `strong`); feeds an honest M4 cover letter (AD-018) | y |
| `rationale` is **always present and bounded** (≤ 500 chars, trimmed) | Including on `cannot_assess`, where it states the reason (`"profile absent"`, `"LLM timeout"`, `"invalid score"`) | Same field-cap discipline as M1/M2; a reason is always owed, even a failure has one (AD-018) | y |
| No-fabrication is enforced by **prompt + eval harness**, not a runtime guarantee | Prompt instructs "use only the Profile and Job, never invent"; the harness measures fabrication rate against labeled probes | An LLM's grounding can't be a hard runtime guarantee; the eval harness is the QE substitute — we *measure* fabrication, we don't *prove* its absence (AD-018) | y |
| Advisory-only is a **side-effect-free / zero-writes** invariant | A match writes to no repository, mutates no state, triggers no outbound action | Makes "the human decides" a load-bearing, testable guarantee (spy-repo zero-writes test), not an accident of "we didn't add storage yet" (AD-020) | y |
| LLM failure policy = **single attempt, bounded timeout, fail closed** | Any error/timeout → `cannot_assess`; **no retry** in MVP | Retry imports nondeterminism and masks a flaky provider (soft fail-open). Exact timeout value + any future retry/backoff → Design (AD-021) | y |
| On fail-closed from an LLM error/timeout/malformed output, **log the real cause server-side** | `logger.exception` (or equivalent) server-side; client sees only `cannot_assess` | A flaky provider stays diagnosable without being masked (pairs with no-retry) and without leaking internals — mirrors M2's 500 logging (AD-021) | y |
| The match request has **no body** | `job_id` in the path; the Profile is the M2 singleton | Nothing for the caller to inject; every `MatchResult` field is server/pipeline-owned (mass-assignment discipline is trivially satisfied) | y |
| **Two-layer testing** | Layer 1: faked LLM behind the port, deterministic, in the coverage gate. Layer 2: real LLM, offline, metrics-vs-thresholds, **not** a blocking CI check | A real-LLM call in the commit gate is flaky, and a flaky gate is a fail-open gate; keeping Layer 2 offline is itself an anti-fail-open decision (AD-019) | y |
| Eval corpus is **human-labeled**, small, honestly caveated | ~8–12 cases across `strong`/`possible`/`weak` + fabrication probes; labels from the user's judgment, never AI-labeled | Grading the model against its own labels is circular; a tiny corpus gives directional, not robust, stats — the writeup says so plainly (AD-019) | y |
| The LLM output shape is the **narrow contract** score + rationale (+ gaps) | The adapter parses exactly these; extra fields ignored, missing/spurious → malformed → `cannot_assess` | A narrow, validated contract is what makes "malformed → fail closed" enforceable | n |
| Over-length `rationale` from the model is **truncated to 500**, not failed closed | Rationale is explanatory prose, not a safety-bearing field | Truncating prose is harmless; only the *score* is safety-bearing and fails closed. (Contrast intentional.) | n |
| On `cannot_assess`, **`gaps = []`** (empty), consistent with `score = null` | A failed/untrusted run surfaces no partial gaps | Partial gaps from a run we don't trust are a misleading signal; the whole result is suppressed, not just the score (reviewer pin) | y |

**Open questions:** none blocking — the two `n` items are safe defaults confirmable at Design; the band cutoffs and the exact timeout are Design tuning.

---

## User Stories

### P1: Score a Job against the Profile ⭐ MVP

**User Story**: As the JobPilot user, I want to ask the Matcher to score a stored job against my stored profile and get back a bounded score, a verdict, the gaps, and a short rationale, so that I have an *advisory* read on fit before I decide whether to apply.

**Why P1**: This is the M3 vertical slice — the whole reason the Profile and Job exist is to be matched.

**Acceptance Criteria** (each line is one EARS pattern):

1. WHEN a `POST /jobs/{job_id}/match` request names an existing job and a profile has been authored THEN the system SHALL obtain a score and rationale from the LLM (behind the port), derive the verdict from the score bands, and return `200` with a `MatchResult` `{score, verdict, gaps, rationale}`.  <!-- event-driven -->
2. The system SHALL derive `verdict` deterministically from `score` bands (`0–39 → weak`, `40–74 → possible`, `75–100 → strong`) as a pure function, independent of the LLM.  <!-- ubiquitous -->
3. WHEN a `MatchResult` is produced THEN `gaps` SHALL be a `list[str]` — empty when none — whose entries are job requirements the Profile shows no evidence for. Not inventing requirements absent from the Job is the model's *intended* behavior, enforced by the prompt and **measured** by the eval harness (MATCH-17); it is NOT a runtime check (consistent with AD-018 and the gaps edge case).  <!-- event-driven; shape is contract, grounding is measured not guaranteed -->
4. WHEN a `MatchResult` is produced THEN `rationale` SHALL be present and ≤ 500 characters after trimming; an over-length model rationale SHALL be truncated to 500 (rationale is explanatory prose, not safety-bearing).  <!-- event-driven -->
5. WHEN a caller sends a request body THEN the system SHALL ignore it — all `MatchResult` fields are server/pipeline-owned and no field is settable by the caller.  <!-- boundary -->

**Independent Test**: with a profile authored and a job stored, `POST /jobs/{job_id}/match` (fake LLM returning `score=82`) returns `200` with `verdict:"strong"`, an integer `score` in `0..100`, a `gaps` list, and a `rationale` ≤ 500 chars.

---

### P1: Fail closed on every uncertainty ⭐ MVP

**User Story**: As the JobPilot user, I want any situation where the Matcher cannot honestly evaluate — no profile yet, the LLM erroring or timing out, or the model returning garbage — to come back as an explicit `cannot_assess` with no score, so that a broken run is never disguised as a good match.

**Why P1**: This is *the* fail-open guard — the reason M3 exists in this shape. It is the milestone's portfolio thesis made testable.

**Acceptance Criteria**:

1. IF a `POST /jobs/{job_id}/match` request names an existing job but **no profile has been authored** (the M2 `404` empty state) THEN the system SHALL return `200` with `verdict = cannot_assess`, `score = null`, and a `rationale` stating the profile is absent — NOT a `404`.  <!-- unwanted-behavior; absent basis, not "not found" -->
2. IF the LLM call **errors or exceeds the timeout** THEN the system SHALL return `200` with `verdict = cannot_assess`, `score = null`, and a `rationale` stating the failure reason, SHALL make **no retry**, AND SHALL log the real cause server-side (with traceback) while the client sees only `cannot_assess`.  <!-- unwanted-behavior; single-attempt, fail closed, diagnosable, no leak -->
3. IF the LLM returns **malformed output** — unparseable, missing score, wrong type, or a score outside `0..100` — THEN the system SHALL return `200` with `verdict = cannot_assess`, `score = null`, and SHALL NOT clamp an out-of-range score to a valid value.  <!-- unwanted-behavior; never clamp -->
4. IF the `job_id` does **not** identify a stored job THEN the system SHALL return `404` (the addressed resource does not exist) — distinct from `cannot_assess`.  <!-- unwanted-behavior; asymmetry -->
5. The system SHALL NEVER return a `strong`/`possible`/`weak` verdict or a non-null score when any of the above uncertainty conditions holds.  <!-- ubiquitous; the anti-fail-open invariant -->
6. WHEN `verdict = cannot_assess` THEN `gaps` SHALL be `[]` (empty), consistent with `score = null` — a failed or untrusted run SHALL NOT surface partial gaps.  <!-- ubiquitous; an untrusted run yields no partial signal -->

**Independent Test**: on a fresh store (no profile), a match returns `200 cannot_assess`/`score:null`; with a profile present but the fake LLM raising (then: timing out; then: returning `score=150`; then: returning non-JSON), each returns `200 cannot_assess`/`score:null` and never a high score; an unknown `job_id` returns `404`; a caplog assertion confirms the LLM-failure cause is logged.

---

### P1: Advisory only — the Matcher never acts ⭐ MVP

**User Story**: As the JobPilot user, I want the Matcher to only *recommend* and to change nothing, so that the decision to apply is always mine and no score can trigger an irreversible action.

**Why P1**: Human-in-the-loop is the product's central risk decision (briefing §1); it must be a hard invariant, not a convention.

**Acceptance Criteria**:

1. WHEN a match is requested THEN the system SHALL perform **no state-changing or irreversible action**: it SHALL write to no repository, mutate no stored state, and trigger no outbound submit/apply.  <!-- ubiquitous; side-effect-free invariant -->
2. WHEN a `MatchResult` is returned THEN it SHALL be advisory only — the system SHALL NOT auto-apply, mark, enqueue, or otherwise act on the score or verdict.  <!-- event-driven -->

**Independent Test**: inject spy `JobRepository`/`ProfileRepository` (and any other stateful collaborator); run a match; assert **zero writes** on every spy and that no outbound action is invoked.

---

### P1: Deterministic seam for the LLM ⭐ MVP

**User Story**: As the JobPilot QE, I want the LLM to sit behind a port so I can inject a fake in unit tests, so that all the fail-open and contract paths are deterministic and counted in the coverage gate.

**Why P1**: Without the seam, none of the fail-closed criteria above are testable without calling a real, non-deterministic model — the milestone would have no deterministic gate.

**Acceptance Criteria**:

1. The Matcher SHALL obtain the model judgment through a port (interface), mirroring the M1/M2 repository seam, so tests inject a fake without any network call.  <!-- ubiquitous -->
2. WHEN a unit test injects a fake returning a canned response (valid score, out-of-range score, malformed payload, raised error, simulated timeout) THEN the system SHALL exercise the corresponding path deterministically, with no real LLM call.  <!-- event-driven -->

**Independent Test**: the full M3 unit suite runs offline (no network, no API key) via the injected fake, and covers the happy path plus each fail-closed branch; coverage gate stays green.

---

### P2: Offline eval harness measures real-model quality

**User Story**: As the JobPilot QE, I want a small, human-labeled eval harness that runs real cases against the actual model and reports metrics, so that I can *measure* the Matcher's quality despite non-deterministic output — the portfolio centerpiece.

**Why P2**: The deterministic layer proves the plumbing; this proves the *judgment*. It's not needed for the endpoint to function, but it is what makes M3 portfolio-worthy. It runs offline, so it never gates commits.

**Acceptance Criteria**:

1. The eval harness SHALL run a **human-labeled** corpus (labels authored by the user, never AI-labeled) of ~8–12 cases spanning `strong`/`possible`/`weak` plus fabrication probes, against the real LLM.  <!-- ubiquitous -->
2. WHEN the harness runs THEN it SHALL report metrics — precision/recall on the strong-vs-not decision, a fabrication rate, and `cannot_assess` correctness — against **directional** thresholds, and SHALL NOT run as a blocking CI gate.  <!-- event-driven -->
3. WHEN a fabrication-probe case (a job requiring a skill the Profile lacks) is evaluated THEN the missing requirement SHALL appear in `gaps` AND the verdict SHALL NOT be `strong` (measured across the corpus, reported as fabrication rate — directional, not a hard per-run assertion).  <!-- event-driven -->
4. The harness output/writeup SHALL state plainly that the corpus is small and the statistics are directional, not robust.  <!-- ubiquitous; honesty about the measurement -->
5. The corpus SHALL include a **thin-job probe** — a job with only `title`/`company` and empty `description`/`requirements` — and the harness SHALL measure that such a job does NOT receive a `strong` verdict, so overconfidence on sparse input is measured, not assumed away (complements the "thin job = low/uncertain score, not `cannot_assess`" edge case).  <!-- event-driven; measures overconfidence on sparse input -->

**Independent Test**: `python -m ... eval` (or equivalent) runs the labeled corpus against the real model and prints precision/recall, fabrication rate, and `cannot_assess` correctness; the command is documented as offline and non-gating; the corpus file is human-authored.

---

## Error / Response Contract

- **Success** (`200`): a `MatchResult` body — `score` (integer `0..100`, or `null`), `verdict` (`strong`|`possible`|`weak`|`cannot_assess`), `gaps` (list of strings), `rationale` (string ≤ 500). `score` is `null` **iff** `verdict = cannot_assess`, and in that case `gaps` is `[]` — an untrusted/failed run surfaces no partial gaps.
- **Unknown job** (`404`): the `job_id` does not identify a stored job. Uses the FastAPI default envelope (consistent with M1/M2). This is the *only* not-found case — an absent Profile is a `200 cannot_assess`, never a `404`.
- **Uncertainty is not an HTTP error**: absent Profile, LLM failure, and malformed output all return `200` with `cannot_assess`. They are valid, expected outcomes of an advisory endpoint, not request failures — the caller asked a well-formed question and got an honest "I can't judge this."
- **No `5xx` masks a fail-open**: an LLM error is caught and mapped to `cannot_assess` (with a server-side log), not surfaced as a `500`. A genuine internal fault unrelated to the LLM (e.g. the Job repository read itself raising) may still surface as `500` with a generic body + server-side log, mirroring M1/M2.

---

## Edge Cases

- WHEN the model returns a score exactly on a band boundary (`39`, `40`, `74`, `75`) THEN the system SHALL apply the bands as specified (`39→weak`, `40→possible`, `74→possible`, `75→strong`) — boundaries are pinned by unit tests.  <!-- boundary -->
- WHEN the model returns a well-formed score plus extra/unknown fields THEN the system SHALL ignore the extras and produce a valid `MatchResult`.  <!-- boundary -->
- WHEN the model returns `gaps` containing entries not present in the Job's requirements THEN the system SHALL still return the result (gaps are model-generated), and the eval harness — not a runtime check — SHALL measure such fabrication.  <!-- boundary; honest about the runtime limit -->
- WHEN the Job has an empty `description`/`requirements` (M1 allows both) THEN the system SHALL still attempt the match on the available fields (title/company) and SHALL NOT return `cannot_assess` merely because a field is sparse — a thin job is a low/uncertain *score*, not a broken run.  <!-- boundary; don't over-trigger cannot_assess -->
- WHEN the model returns an empty or whitespace-only rationale on a scored result THEN the system SHALL treat the payload as malformed and fail closed to `cannot_assess` (a scored verdict owes a reason).  <!-- unwanted-behavior -->
- IF the LLM returns a score as a numeric string (`"82"`) THEN Design SHALL decide strict-reject vs. safe-coerce; the spec requires only that a value not representable as an integer in `0..100` fails closed.  <!-- boundary; deferred detail, fail-closed floor fixed -->
- WHEN two matches are requested for the same job in succession THEN each SHALL independently re-run the LLM (ephemeral, no caching) and neither SHALL write state.  <!-- boundary; reinforces ephemeral + side-effect-free -->

---

## Requirement Traceability

Each requirement gets a unique ID for tracking across design, tasks, and validation.

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| MATCH-01 | P1: Score (200 with MatchResult) | T5, T6 | ✅ Verified |
| MATCH-02 | P1: Score (verdict derived from bands, pure fn) | T1 | ✅ Verified |
| MATCH-03 | P1: Score (gaps grounded in Job requirements) | T1, T2, T3, T7 | ✅ Verified |
| MATCH-04 | P1: Score (rationale present, ≤500, truncated) | T1, T2 | ✅ Verified |
| MATCH-05 | P1: Score (request body ignored / no mass-assign) | T5 | ✅ Verified |
| MATCH-06 | P1: Fail closed (absent Profile → cannot_assess, not 404) | T2, T5, T6 | ✅ Verified |
| MATCH-07 | P1: Fail closed (LLM error/timeout → cannot_assess, no retry, logged) | T2, T4 | ✅ Verified |
| MATCH-08 | P1: Fail closed (malformed/out-of-range → cannot_assess, no clamp) | T2, T4 | ✅ Verified |
| MATCH-09 | P1: Fail closed (unknown job_id → 404) | T5 | ✅ Verified |
| MATCH-10 | P1: Fail closed (never a high score under uncertainty — invariant) | T1, T2 | ✅ Verified |
| MATCH-11 | P1: Advisory (side-effect-free / zero-writes) | T5, T6 | ✅ Verified |
| MATCH-12 | P1: Advisory (no auto-apply/mark/enqueue) | T5, T6 | ✅ Verified |
| MATCH-13 | P1: Seam (LLM behind a port) | T2, T4 | ✅ Verified |
| MATCH-14 | P1: Seam (fake drives every path deterministically, offline) | T2, T4 | ✅ Verified |
| MATCH-15 | P2: Eval (human-labeled corpus vs. real LLM) | T7 | ✅ Verified |
| MATCH-16 | P2: Eval (metrics vs. directional thresholds, non-gating) | T7 | ✅ Verified |
| MATCH-17 | P2: Eval (fabrication probe → gap listed, verdict ≠ strong) | T7 | ✅ Verified |
| MATCH-18 | P2: Eval (writeup states small-corpus / directional caveat) | T7 | ✅ Verified |
| MATCH-19 | P2: Eval (thin-job probe → not strong; overconfidence measured) | T3, T7 | ✅ Verified |
| MATCH-20 | P1: Fail closed (cannot_assess → gaps = [], no partial signal) | T1, T2 | ✅ Verified |

**ID format:** `MATCH-[NUMBER]`.

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 20 total, 0 mapped to tasks yet (Tasks phase pending). MATCH-01..14 + MATCH-20 are P1; MATCH-15..19 are P2 (eval harness).

---

## Success Criteria

How we know the feature is successful:

- [ ] `POST /jobs/{job_id}/match` with a stored job + authored profile returns `200` with a bounded integer `score`, a band-derived `verdict`, a `gaps` list, and a `rationale` ≤ 500 chars.
- [ ] Every uncertainty path — absent profile, LLM error, LLM timeout, malformed/out-of-range output — returns `200 cannot_assess` with `score = null` **and `gaps = []`**, and **never** a high score; verified on the failing path, with the LLM-failure cause logged server-side.
- [ ] Unknown `job_id` returns `404`; absent profile does **not** (it returns `cannot_assess`) — the asymmetry is verified.
- [ ] A match writes nothing: a spy-repository test asserts zero writes and no outbound action — advisory-only is a proven invariant, not a convention.
- [ ] The full unit suite runs offline against a faked LLM (no network, no API key), covering the happy path and each fail-closed branch; coverage gate (`--cov-fail-under=80`) stays green with failing paths exercised.
- [ ] The offline eval harness runs a human-labeled corpus against the real model and prints precision/recall, fabrication rate, and `cannot_assess` correctness; it is documented as non-gating and its writeup states the small-corpus / directional caveat.
- [ ] No provider/model choice was made in Specify — it is carried to Design (via `claude-api`).
