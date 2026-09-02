# Generator (M4) Specification

## Problem Statement

JobPilot can author a canonical `Profile` (M2), store a `Job` (M1), and judge one
against the other with the `Matcher` (M3). But the user still has to write every
application by hand. M4 adds the **Generator**: given the stored `Profile`
(`raw_cv` is the **source of truth**) and a stored `Job`, it produces a **tailored
cover-letter DRAFT** for the human to review, edit, and decide on. This is the
**second LLM component**, and it is the honesty/anti-fabrication centerpiece of
the project: the tool is literally named after *not eating the CV*. The letter
must be grounded **only** in what the Profile actually states (never inventing a
skill, employer, date, or qualification), the M3 gaps must be framed **honestly**
(areas to grow, never claimed as possessed), the human always reviews before
anything is sent, any failure must fail **closed** (never a hallucinated document
passed off as real), and — because an LLM's honesty cannot be a hard runtime
guarantee — fabrication must be **measured** by an offline eval harness, exactly
as M3 measured its scoring. Getting the grounding *right* is the point; a tailored
CV, persistence, and autonomy are deliberately later.

## Goals

- [ ] Define the canonical `GenerateResult` contract once (a closed `status` enum, a `draft` that is a string on success and `null` on failure, and a `reason`), so downstream (M5 Queue) reads a stable shape.
- [ ] Expose `POST /jobs/{job_id}/generate`: read the Job + the singleton Profile, run the **Matcher internally** for a server-authoritative `MatchResult`, then generate a cover-letter draft behind a port — synchronous, ephemeral, side-effect-free.
- [ ] Make fabrication impossible to hide: the letter is grounded **only** in the Profile (`raw_cv` + structured fields) and the Job; the M3 gaps are framed as areas to grow, never as possessed — enforced by the prompt and **measured** by the eval harness.
- [ ] Make fail-open impossible by construction: an absent Profile, a match that comes back `cannot_assess`, or an LLM error/timeout/malformed output yields `status = cannot_generate` + `draft = null` — **never a hollow or placeholder letter** — proven on the failing path.
- [ ] Ship a deterministic seam (the Generator behind a port) so every fail-closed path is unit-tested against a fake, in the coverage gate.
- [ ] Ship a minimal-but-real offline eval harness (human-labeled corpus + metrics) so fabrication rate, gap-honesty, and language-appropriateness are *measured*, not asserted.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| **Tailored / rewritten CV** | Deferred to P2/P3 as a separate, tighter-constrained slice: it must **select and reorder existing `raw_cv` content only, never freely rewrite claims** — rephrasing a bullet is the exact "eat the CV" fabrication risk and needs a hard grounding rule, not an MVP rush (AD-025). P1 ships the cover letter, the cleanest fabrication probe. |
| **Structured self-report (draft + evidence-tagged claims)** | Deferred to P2 as an inspectability upgrade (AD-028). Its citations are themselves LLM-generated, so they must be *measured/verified*, not trusted — that deserves its own focused slice. |
| **Optional `language` override param** | Deferred to P2 as a **data-driven escape hatch** (AD-030). Only added if the eval shows the model mis-guesses language often on ambiguous cases (e.g. an English posting from a Brazilian company wanting a Portuguese application). An explicit param is human input, not a heuristic. |
| **Persisting the draft / draft lifecycle (save, version, "which draft did I send")** | Deferred to M5, the queue that is the real consumer (AD-027). Storing now pulls M5's lifecycle in early and reintroduces a staleness fail-open (Profile changes, stored draft does not) with no consumer — YAGNI. |
| **Reusing an already-computed `MatchResult` (caching)** | The Generator recomputes the match internally (AD-026). Reuse is an M5 optimization; caching now reintroduces the staleness fail-open AD-017 avoided. |
| **LLM provider / model choice** | A Design decision (via the `claude-api` skill, default the latest Claude model), reusing the M3 `AnthropicMatcher` adapter pattern. Specify defines behavior, not the vendor. |
| **Retry / backoff on LLM failure** | MVP fails closed on the first failure; retry adds nondeterminism and masks a flaky provider (a soft fail-open), mirroring AD-021. Tuning deferred to Design. |
| **Runtime fabrication grader / entity-lint gate** | Rejected as the primary mechanism: an LLM grading itself is circular, and a deterministic NER/paraphrase lint is brittle — a flaky gate is a fail-open gate (AD-019/AD-028). Fabrication is **measured offline**, not runtime-gated. |
| **Auto-apply, sending, submitting, or any queue mutation from a draft** | The core product boundary — the submit is always the human's click (briefing §1). |
| **Batch / scheduled generation (draft many jobs unattended)** | M6 (autonomy); M4 drafts one job per explicit request. |
| **UI for viewing / triggering generation** | M5 (Report/UI). M4 is API-only, exercised via Swagger/Bruno and tests. |
| **Editing the `Job` or the `Profile`** | Owned by M1 / M2 respectively. |
| **Auth, rate limiting, multi-user** | Personal single-user local tool (briefing §6). |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| P1 artifact is the **cover letter only** | Tailored CV → P2/P3 under a "select & reorder `raw_cv`, never rewrite" rule | Smallest honest vertical slice; the fabrication probe is cleanest against new prose; reuses the M3 seam almost wholesale (AD-025) | y |
| The Generator **recomputes the `MatchResult` internally** | `POST /jobs/{job_id}/generate` runs the Matcher server-side, then generates | Gaps are server-authoritative — the caller cannot forge/stale them, so "handle gaps honestly" is a guarantee, not a hope (AD-026) | y |
| Draft is **ephemeral + side-effect-free** | Returned in the response body; nothing stored | Preserves the AD-020 zero-writes invariant; the draft lifecycle is M5's, and persisting now reintroduces a staleness fail-open (AD-027) | y |
| No-fabrication is **measured offline**, not runtime-guaranteed | Response is `{status, draft, reason}` (prose draft); the harness measures fabrication rate + gap-honesty | An LLM's grounding can't be a hard runtime guarantee; the harness is the QE substitute — mirrors AD-018/AD-019 (AD-028) | y |
| Fail closed **only** when there is no trustworthy basis | `cannot_assess` from the internal match, **or** a generation-LLM failure/malformed output → `cannot_generate` | A **weak** fit still has real, server-authoritative gaps to frame honestly; refusing on weak would over-block and override the human (AD-029, echoing the AD-024 "don't reject jobs" stance) | y |
| `draft` is **`null` iff `status = cannot_generate`** | Success → `{status: generated, draft: "<letter>"}`; failure → `{status: cannot_generate, draft: null, reason}` | Same "null iff" discipline as M3's `score`; a failed run is structurally distinct from a real letter — never a hollow document (AD-029) | y |
| Unknown `job_id` vs absent Profile are **deliberately asymmetric** | Unknown `job_id` → `404`; absent Profile → `200 cannot_generate` | The addressed resource (the job) genuinely doesn't exist → `404`. An absent Profile is "no basis to draft", not "not found" → `cannot_generate` (AD-029, mirrors AD-017) | y |
| Letter **language matches the Job posting** | Prompt-instructed; **no language-detection code**; measured by the eval harness | Delegating the NL judgment to the model and *measuring* it keeps our code heuristic-free (consistent with AD-002, AD-030); a detection heuristic would be a fail-open magnet | y |
| Generation-LLM **failure policy = single attempt, bounded timeout, no retry, log server-side** | Any error/timeout → `cannot_generate`; real cause logged, client sees a generic reason | Retry imports nondeterminism and masks a flaky provider; mirrors AD-021. Exact timeout → Design | y |
| The generate request has **no body** in P1 | `job_id` in the path; the Profile is the M2 singleton | Nothing for the caller to inject; every `GenerateResult` field is server/pipeline-owned (mass-assignment discipline trivially satisfied) | y |
| `draft` is **bounded** (trimmed to a cover-letter-sized cap) | `≤ DRAFT_MAX` chars; over-length is truncated, not failed closed | A cover letter is short prose, not a safety-bearing field; truncating harmless prose mirrors M3's rationale bounding. Exact cap → Design | n |
| A **thin Job** (title/company only) that still yields a valid match verdict **does generate** | Not a `cannot_generate` merely because the Job is sparse | Sparseness is a low-information input, not a broken run; forcing `cannot_generate` there would over-block. The harness measures that a thin job doesn't get padded with fabrication | n |
| LLM output shape is a **narrow contract** (the letter text) | The adapter parses exactly the draft; empty/whitespace/missing → malformed → `cannot_generate` | A narrow, validated contract is what makes "malformed → fail closed" enforceable | n |

**Open questions:** none blocking — the four `n` items are safe defaults confirmable at Design (the exact `DRAFT_MAX`, the thin-job behavior, and the narrow output contract). Provider/model, the exact timeout, and the P2 escape hatches are Design/roadmap concerns.

---

## User Stories

### P1: Generate a tailored cover-letter draft ⭐ MVP

**User Story**: As the JobPilot user, I want to ask the Generator to draft a cover letter for a stored job using my stored profile, so that I have an honest, tailored starting point I can review and edit instead of writing from scratch.

**Why P1**: This is the M4 vertical slice — the reason the Profile, Job, and Matcher exist is to produce application material.

**Acceptance Criteria** (each line is one EARS pattern):

1. WHEN a `POST /jobs/{job_id}/generate` request names an existing job and a profile has been authored THEN the system SHALL run the Matcher internally to obtain a server-authoritative `MatchResult`, then obtain a cover-letter draft from the LLM (behind the port) grounded in the Profile + Job + that `MatchResult`, and return `200` with `GenerateResult` `{status: "generated", draft, reason}`.  <!-- event-driven -->
2. The system SHALL define `GenerateResult` with a closed `status` enum (`generated` | `cannot_generate`), a `draft` (string when `generated`, `null` when `cannot_generate`), and a `reason` (string) — where `draft` is non-null **iff** `status = generated`.  <!-- ubiquitous -->
3. WHEN a `MatchResult` with verdict `strong`, `possible`, **or `weak`** is produced THEN the system SHALL proceed to generate the draft — a weak fit still yields an honest, gap-aware letter, and the decision to apply is the human's, not the tool's.  <!-- event-driven; don't over-block on a weak fit -->
4. WHEN a draft is produced THEN it SHALL be present, non-empty, and ≤ `DRAFT_MAX` characters after trimming; an over-length draft SHALL be truncated (the draft is advisory prose, not a safety-bearing field).  <!-- event-driven -->
5. WHEN a caller sends a request body THEN the system SHALL ignore it — all `GenerateResult` fields are server/pipeline-owned and no field is settable by the caller.  <!-- boundary -->

**Independent Test**: with a profile authored and a job stored, `POST /jobs/{job_id}/generate` (fake Matcher returning `possible`, fake Generator returning a canned letter) returns `200 {status:"generated"}` with a non-empty `draft` ≤ `DRAFT_MAX`; a weak fake verdict still returns `generated`.

---

### P1: Grounded and honest — never fabricate ⭐ MVP

**User Story**: As the JobPilot user, I want the letter to only ever claim things my profile actually states, and to treat my gaps honestly, so that I never send an application that lies about my experience.

**Why P1**: This is *the* anti-fabrication guard — the reason M4 exists in this shape ("don't eat the CV"). It is the milestone's portfolio thesis made measurable.

**Acceptance Criteria**:

1. The generated draft SHALL be grounded **only** in the Profile (`raw_cv` + structured fields) and the Job, and SHALL NOT introduce skills, experience, employers, dates, titles, or qualifications the Profile does not state. This grounding is the model's *intended* behavior, enforced by the prompt and **measured** by the eval harness (GEN-22); it is NOT a runtime check (an LLM's honesty cannot be a hard runtime guarantee — consistent with AD-018/AD-028).  <!-- ubiquitous; grounding is measured, not guaranteed -->
2. WHEN the `MatchResult` carries gaps THEN the draft SHALL frame each gap **honestly** — as an area to grow, learn, or address — and SHALL NOT claim a gap as an already-possessed skill or experience. This is prompt-enforced and **measured** by the harness (GEN-23), not a runtime check.  <!-- event-driven -->
3. WHEN a draft is generated THEN it SHALL be written in the **language of the Job posting**. Language selection is delegated to the model via the prompt (there is **no language-detection code** — a detection heuristic would be a fail-open magnet, AD-002) and is **measured** by the harness (GEN-24).  <!-- event-driven -->

**Independent Test**: the harness (P2) drives labeled cases; at the unit layer, the prompt/render is asserted to embed the verbatim `raw_cv`, the Job, and the gap list, and to instruct grounding + gap-honesty + job-language — so the model is *given* only grounded inputs and the honesty instruction. (Whether the model obeys is measured in P2, not asserted at the unit layer.)

---

### P1: Fail closed on every uncertainty ⭐ MVP

**User Story**: As the JobPilot user, I want any situation where the Generator cannot honestly draft — no profile, the match coming back uncertain, or the LLM erroring or returning garbage — to come back as an explicit `cannot_generate` with no draft, so that a broken run is never disguised as a real letter.

**Why P1**: This is the fail-open guard. A hollow or hallucinated document passed off as a real letter is the worst outcome M4 could produce.

**Acceptance Criteria**:

1. IF a `POST /jobs/{job_id}/generate` request names an existing job but **no profile has been authored** (the M2 `404` empty state) THEN the system SHALL return `200` with `status = cannot_generate`, `draft = null`, and a `reason` stating the profile is absent — NOT a `404`, and NOT a letter.  <!-- unwanted-behavior; absent basis, not "not found" -->
2. IF the **internal match returns `cannot_assess`** (its LLM erroring, timing out, or returning malformed/out-of-range output) THEN the system SHALL return `200` with `status = cannot_generate`, `draft = null`, and a `reason` stating the match failed — no letter is drafted without a trustworthy gap analysis to ground it.  <!-- unwanted-behavior; no trustworthy basis -->
3. IF the **generation LLM call errors or exceeds the timeout** THEN the system SHALL return `200` with `status = cannot_generate`, `draft = null`, and a `reason`, SHALL make **no retry**, AND SHALL log the real cause server-side (with traceback) while the client sees only a generic reason.  <!-- unwanted-behavior; single-attempt, diagnosable, no leak -->
4. IF the generation LLM returns **malformed output** — empty, whitespace-only, missing, or the wrong type — THEN the system SHALL treat it as a failure and return `200 cannot_generate` with `draft = null`, and SHALL NEVER emit a hollow or placeholder letter.  <!-- unwanted-behavior; never a hollow document -->
5. IF the generation LLM **stop reason indicates a refusal or an incomplete/truncated completion** (e.g. `refusal`, or a `max_tokens`/length stop before the model finished) THEN the system SHALL treat the response as a failure and return `200 cannot_generate` with `draft = null` — a polite decline or a letter cut off mid-sentence is non-empty text but is NOT a trustworthy draft, so it SHALL NOT be returned as `generated` (mirrors M3's `AnthropicMatcher` stop-reason check).  <!-- unwanted-behavior; non-empty-but-untrustworthy text is still a fail -->
6. IF the `job_id` does **not** identify a stored job THEN the system SHALL return `404` (the addressed resource does not exist) — distinct from `cannot_generate`.  <!-- unwanted-behavior; asymmetry -->
7. The system SHALL NEVER return `status = generated` or a non-null `draft` when any of the above uncertainty conditions holds — `draft` is `null` **iff** `status = cannot_generate`.  <!-- ubiquitous; the anti-fail-open invariant -->

**Independent Test**: on a fresh store (no profile) a generate returns `200 cannot_generate`/`draft:null`; with a profile present but the fake Matcher returning `cannot_assess` (then: the fake Generator raising; then: timing out; then: returning an empty draft; then: returning non-empty text with a `refusal`/`max_tokens` stop reason), each returns `200 cannot_generate`/`draft:null` and never a letter; an unknown `job_id` returns `404`; a caplog assertion confirms the generation-failure cause is logged.

---

### P1: Advisory only — the Generator never acts ⭐ MVP

**User Story**: As the JobPilot user, I want the Generator to only *draft* and to change nothing and send nothing, so that the decision to apply — and the click that sends — is always mine.

**Why P1**: Human-in-the-loop is the product's central risk decision (briefing §1); it must be a hard invariant, not a convention.

**Acceptance Criteria**:

1. WHEN a draft is requested THEN the system SHALL perform **no state-changing or irreversible action**: it SHALL write to no repository, mutate no stored state, and trigger no outbound submit/apply/send.  <!-- ubiquitous; side-effect-free invariant -->
2. WHEN a `GenerateResult` is returned THEN it SHALL be advisory only — the system SHALL NOT auto-send, auto-submit, mark, or enqueue anything based on it; the draft is a starting point for the human.  <!-- event-driven -->

**Independent Test**: inject spy `JobRepository`/`ProfileRepository` (and any other stateful collaborator); run a generate; assert **zero writes** on every spy and that no outbound action is invoked.

---

### P1: Deterministic seam for the LLM ⭐ MVP

**User Story**: As the JobPilot QE, I want the generation LLM to sit behind a port so I can inject a fake in unit tests, so that all the fail-open and contract paths are deterministic and counted in the coverage gate.

**Why P1**: Without the seam, none of the fail-closed criteria above are testable without calling a real, non-deterministic model — the milestone would have no deterministic gate.

**Acceptance Criteria**:

1. The Generator SHALL obtain the draft through a port (interface), mirroring the M1/M2/M3 seam, so tests inject a fake without any network call; and the Matcher it calls internally SHALL likewise be the injected M3 port.  <!-- ubiquitous -->
2. WHEN a unit test injects fakes returning canned responses (a valid draft, an empty/whitespace draft, a raised error, a simulated timeout; and a Matcher returning each verdict or `cannot_assess`) THEN the system SHALL exercise the corresponding path deterministically, with no real LLM call.  <!-- event-driven -->
3. The system SHALL route **every** uncertainty (absent Profile, match `cannot_assess`, generation error/timeout, malformed output, and a refusal/incomplete stop reason) through a **single central fail-closed mapper** to `cannot_generate`, so all fail-open paths pass through one mutation-testable function (mirroring M3's `interpret`).  <!-- ubiquitous; one funnel for fail-closed -->
4. IF a Job/Profile repository read raises THEN the system SHALL return a generic `500` (no SQL/stack leak) and log the real cause server-side, mirroring M1/M2 — a storage fault SHALL NOT masquerade as `cannot_generate`.  <!-- unwanted-behavior; storage fault ≠ advisory outcome -->

**Independent Test**: the full M4 unit suite runs offline (no network, no API key) via injected fakes, covering the happy path and each fail-closed branch; coverage gate stays green with failing paths exercised.

---

### P2: Offline eval harness measures fabrication and honesty

**User Story**: As the JobPilot QE, I want a small, human-labeled eval harness that runs real cases against the actual model and reports fabrication rate, gap-honesty, and language-appropriateness, so that I can *measure* the Generator's honesty despite non-deterministic prose — the portfolio centerpiece.

**Why P2**: The deterministic layer proves the plumbing; this proves the *honesty*. It's not needed for the endpoint to function, but it is what makes M4 portfolio-worthy. It runs offline, so it never gates commits.

**Acceptance Criteria**:

1. The eval harness SHALL run a **human-labeled** corpus (labels authored by the user, never AI-labeled) of cases against the real LLM, and SHALL NOT run as a blocking CI gate (a real-LLM call in the commit gate is flaky, and a flaky gate is a fail-open gate — AD-019).  <!-- ubiquitous -->
2. WHEN a **fabrication-probe** case is evaluated — a Job/Profile pair with a labeled "forbidden fact" (a skill, employer, degree, or date **absent** from the Profile) — THEN the harness SHALL measure whether the generated letter asserts that fact, reported as a **fabrication rate** (directional, not a hard per-run assertion).  <!-- event-driven -->
3. WHEN a **gap-honesty** case is evaluated — a Job/Profile pair with a labeled gap — THEN the harness SHALL measure whether the letter claims the gap as possessed vs. frames it as an area to grow.  <!-- event-driven -->
4. WHEN a case is evaluated THEN the harness SHALL measure **language-appropriateness** — whether the letter is written in the Job posting's language.  <!-- event-driven -->
5. The corpus SHALL include a **thin-job probe** — a Job with only `title`/`company` — and the harness SHALL measure that the letter does NOT pad the gap with fabricated specifics (overconfidence on sparse input is measured, not assumed away).  <!-- event-driven -->
6. The harness's metric functions SHALL be **pure and LLM-free**, unit-tested and in the coverage gate; and the harness output/writeup SHALL state plainly that the corpus is small and the statistics are directional, not robust.  <!-- ubiquitous; honesty about the measurement -->

**Independent Test**: `python -m ... eval` (or equivalent) runs the labeled corpus against the real model and prints fabrication rate, gap-honesty, and language-appropriateness; the command is documented as offline and non-gating; the corpus file is human-authored; `metrics.py` has pure unit tests that run in the gate.

---

## Error / Response Contract

- **Success** (`200`): a `GenerateResult` body — `status = "generated"`, `draft` (non-empty string ≤ `DRAFT_MAX`), `reason` (short string). `draft` is non-null **iff** `status = generated`.
- **Fail closed** (`200`): `status = "cannot_generate"`, `draft = null`, `reason` states the cause (`"profile absent"` | `"match failed"` | `"generation failed"`). Absent Profile, a `cannot_assess` match, and an LLM error/timeout/malformed output all land here — they are valid, expected outcomes of an advisory endpoint, not request failures. **Never a hollow or placeholder letter.**
- **Unknown job** (`404`): the `job_id` does not identify a stored job. Uses the FastAPI default envelope (consistent with M1/M2/M3). This is the *only* not-found case — an absent Profile is a `200 cannot_generate`, never a `404`.
- **No `5xx` masks a fail-open**: an LLM error (match or generation) is caught and mapped to `cannot_generate` (with a server-side log), not surfaced as a `500`. A genuine internal fault unrelated to the LLM (e.g. a repository read raising) may still surface as `500` with a generic body + server-side log, mirroring M1/M2/M3.

---

## Edge Cases

- WHEN the internal match returns a **weak** verdict THEN the system SHALL still generate a draft (weak is a valid basis with real gaps), NOT `cannot_generate`.  <!-- boundary; don't over-block -->
- WHEN the Job has an empty `description`/`requirements` (M1 allows both) but the internal match still returns a verdict (not `cannot_assess`) THEN the system SHALL generate on the available fields and SHALL NOT fabricate specifics to fill the gap (measured by the thin-job probe, GEN-25).  <!-- boundary -->
- WHEN the generation model returns a draft longer than `DRAFT_MAX` THEN the system SHALL truncate it (advisory prose), not fail closed.  <!-- boundary -->
- WHEN the generation model returns an **empty or whitespace-only** draft THEN the system SHALL treat it as malformed and fail closed to `cannot_generate` — a hollow document is worse than an honest failure.  <!-- unwanted-behavior -->
- WHEN the generation model returns **non-empty text but with a `refusal` or `max_tokens`/length stop reason** (a polite decline, or a letter truncated mid-sentence) THEN the system SHALL fail closed to `cannot_generate` — non-empty is not the same as complete-and-trustworthy; a long artifact like a cover letter is a realistic `max_tokens` case (GEN-27).  <!-- unwanted-behavior; the subtle non-empty fail-open -->
- WHEN the generation model returns a well-formed, complete draft with a normal stop reason THEN the system SHALL return it (the stop-reason check gates on failure signals, not on the happy path).  <!-- boundary; don't over-block on a normal completion -->
- WHEN two drafts are requested for the same job in succession THEN each SHALL independently re-run the match + generation (ephemeral, no caching) and neither SHALL write state.  <!-- boundary; reinforces ephemeral + side-effect-free -->
- WHEN the Profile exists but the internal match's generation of gaps is trustworthy yet the Job posting's language is ambiguous THEN the model chooses the language (no detection code) and the harness measures appropriateness; a systematic mis-guess is the trigger to add the P2 `language` override (AD-030), not a runtime fix.  <!-- boundary; data-driven escape hatch -->

---

## Requirement Traceability

Each requirement gets a unique ID for tracking across design, tasks, and validation.

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| GEN-01 | P1: Generate (200 with GenerateResult) | - | Pending |
| GEN-02 | P1: Generate (recompute match internally, then generate) | - | Pending |
| GEN-03 | P1: Generate (GenerateResult contract; draft non-null iff generated) | - | Pending |
| GEN-04 | P1: Generate (generate on strong/possible/weak) | - | Pending |
| GEN-05 | P1: Generate (draft bounded ≤ DRAFT_MAX, truncated) | - | Pending |
| GEN-06 | P1: Generate (request body ignored / no mass-assign) | - | Pending |
| GEN-07 | P1: Grounded (only Profile raw_cv+fields + Job; no invented facts — measured) | - | Pending |
| GEN-08 | P1: Grounded (gaps framed as areas to grow, never possessed — measured) | - | Pending |
| GEN-09 | P1: Grounded (draft language matches Job posting — prompt-instructed, measured) | - | Pending |
| GEN-10 | P1: Fail closed (absent Profile → cannot_generate, not 404, no letter) | - | Pending |
| GEN-11 | P1: Fail closed (match cannot_assess → cannot_generate) | - | Pending |
| GEN-12 | P1: Fail closed (generation LLM error/timeout → cannot_generate, no retry, logged) | - | Pending |
| GEN-13 | P1: Fail closed (malformed/empty draft → cannot_generate, never hollow) | - | Pending |
| GEN-14 | P1: Fail closed (unknown job_id → 404) | - | Pending |
| GEN-15 | P1: Fail closed (never a non-null draft under uncertainty; draft null iff cannot_generate — invariant) | - | Pending |
| GEN-16 | P1: Advisory (side-effect-free / zero-writes) | - | Pending |
| GEN-17 | P1: Advisory (no auto-send/submit/mark/enqueue) | - | Pending |
| GEN-18 | P1: Seam (Generator + Matcher behind ports; fakes, offline) | - | Pending |
| GEN-19 | P1: Seam (fakes drive every path deterministically) | - | Pending |
| GEN-20 | P1: Seam (single central fail-closed mapper → cannot_generate) | - | Pending |
| GEN-21 | P1: Seam (RepositoryError → generic 500 + log, not cannot_generate) | - | Pending |
| GEN-22 | P2: Eval (fabrication-rate metric on forbidden-fact probes) | - | Pending |
| GEN-23 | P2: Eval (gap-honesty metric) | - | Pending |
| GEN-24 | P2: Eval (language-appropriateness metric) | - | Pending |
| GEN-25 | P2: Eval (thin-job probe → no fabricated padding) | - | Pending |
| GEN-26 | P2: Eval (human-labeled corpus, non-gating; pure metrics unit-tested; small-corpus caveat) | - | Pending |
| GEN-27 | P1: Fail closed (refusal or incomplete/max_tokens stop reason → cannot_generate; non-empty ≠ trustworthy) | - | Pending |

**ID format:** `GEN-[NUMBER]`.

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 27 total, 0 mapped to tasks yet (Tasks phase pending). GEN-01..21 + GEN-27 are P1; GEN-22..26 are P2 (eval harness). (GEN-27 is a P1 fail-closed requirement listed after the P2 block, mirroring M3's MATCH-20 placement.)

---

## Success Criteria

How we know the feature is successful:

- [ ] `POST /jobs/{job_id}/generate` with a stored job + authored profile returns `200 {status:"generated"}` with a non-empty `draft` ≤ `DRAFT_MAX`, grounded in the Profile + Job + an internally-computed `MatchResult`.
- [ ] A **weak** match still generates an honest, gap-aware letter — the tool does not override the human on a soft signal.
- [ ] Every uncertainty path — absent profile, match `cannot_assess`, generation LLM error/timeout, malformed/empty draft, **and a refusal or incomplete (`max_tokens`) stop reason** — returns `200 cannot_generate` with `draft = null` and a `reason`, and **never a hollow, truncated, or placeholder letter**; verified on the failing path, with the generation-failure cause logged server-side.
- [ ] Unknown `job_id` returns `404`; absent profile does **not** (it returns `cannot_generate`) — the asymmetry is verified.
- [ ] A generate writes nothing: a spy-repository test asserts zero writes and no outbound send/submit — advisory-only is a proven invariant, not a convention.
- [ ] The full unit suite runs offline against faked Matcher + Generator (no network, no API key), covering the happy path and each fail-closed branch; coverage gate (`--cov-fail-under=80`) stays green with failing paths exercised.
- [ ] The offline eval harness runs a human-labeled corpus against the real model and prints fabrication rate, gap-honesty, and language-appropriateness; it is documented as non-gating, its `metrics.py` has pure unit tests in the gate, and its writeup states the small-corpus / directional caveat.
- [ ] No provider/model choice was made in Specify — it is carried to Design (via `claude-api`, reusing the M3 `AnthropicMatcher` adapter pattern).
