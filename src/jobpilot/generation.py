"""The generator: a second LLM behind a swappable port, plus the fail-closed
orchestration.

The port (`Generator`) hides a non-deterministic LLM that drafts a cover letter,
so the whole decision path is unit-testable offline via a fake. `generate_letter`
is the orchestration: it recomputes the match internally (reusing the M3
`match_job`, LLM call #1) for server-authoritative gaps, and only then calls the
generator (LLM call #2). Every uncertainty — absent profile, an untrustworthy
match, or a generation failure — funnels through `GenerateResult.cannot_generate`,
so a broken run is never disguised as a real letter (GEN-10..13/20). `build_result`
is the single success-side mapper: it trims, caps at `DRAFT_MAX`, and rejects a
hollow draft.

The prompt (`SYSTEM_PROMPT` + `render`) and the `AnthropicGenerator` adapter are
appended in later tasks (T3, T4).
"""

import logging
from typing import Protocol

import anthropic

from jobpilot.matching import Matcher, match_job
from jobpilot.models import (
    DRAFT_MAX,
    GENERATED_REASON,
    GenerateResult,
    Job,
    MatchResult,
    Profile,
)

logger = logging.getLogger("jobpilot")


class GeneratorError(Exception):
    """Raised by an adapter when it cannot produce a trustworthy draft (API
    error, timeout, refusal, ``max_tokens`` truncation, or empty/unparseable
    output). The single exception type the service catches."""


SYSTEM_PROMPT = """\
You write a tailored cover letter for a candidate applying to a specific job. You \
are advisory only: your draft helps a human who reviews and edits it before \
anything is ever sent. You produce a DRAFT, never a final or submitted document.

Grounding rule (strict, this is the whole point):
- Use ONLY the facts in the Candidate Profile and the Job below. The Profile is \
BOTH the structured fields AND the candidate's raw CV text; a skill or experience \
stated only in the CV prose still counts.
- NEVER invent skills, employers, job titles, dates, degrees, certifications, \
achievements, or qualifications the Profile does not state. Do not upgrade or \
embellish a stated fact. "Familiar with X" must not become "expert in X".
- If the Job asks for something the Profile does not evidence, do NOT claim it. \
You may honestly express motivation to grow into it, or connect a genuinely \
related strength the Profile does state, but never assert the candidate already \
has it.

Handling gaps honestly:
- You are given a list of gaps: the Job's requirements the Profile shows no \
evidence for. Address them honestly, as areas the candidate is motivated to \
develop, or by leaning on adjacent stated strengths. NEVER present a gap as an \
already-possessed skill.
- This gap list is internal guidance for you alone. NEVER mention it, quote it, \
or reference any analysis, score, match, evaluation, or "gaps" in the letter. Do \
not write things like "per the analysis" or "despite some gaps". The letter must \
read as a natural, self-contained cover letter.

Language:
- Write the letter in the language of the Job posting. If the posting's language \
is unclear, use the language of the candidate's CV.

Style and output:
- Write in natural, human language. This letter goes straight to a recruiter, so \
anything that reads as machine-written works against the candidate. Do NOT use em \
dashes; use commas or periods instead. Do NOT use filler transitions such as \
"moreover", "furthermore", or "in conclusion". Do NOT open with clichés such as \
"I am writing to express my interest". Prefer plain, specific phrasing over \
purple prose.
- Do not mention salary, compensation, or pay expectations; those are handled \
elsewhere in the application.
- A concise, professional cover letter: a short opening, one or two body \
paragraphs connecting the candidate's real experience to the role, and a brief \
close. Where the Profile genuinely lacks a detail, such as the hiring manager's \
name, write naturally around it rather than inventing it.
- Output ONLY the letter text. No preamble, no explanation, no markdown headers, \
no notes to the reader.
"""


def _lines_or_none(items: list[str]) -> str:
    if not items:
        return "(none)"
    return "\n".join(f"- {item}" for item in items)


def render(job: Job, profile: Profile, match: MatchResult) -> str:
    """Render the Job + Profile + gaps into the user-message content.

    Reuses the M3 field-rendering approach (verbatim ``raw_cv``, ``(not stated)``
    for absent optionals) with one deliberate divergence: it OMITS
    ``salary_expectation`` entirely (AD-032). A cover letter must never cite pay,
    and not feeding the figure to the model is a stronger guarantee than
    instructing against it. ``base_location`` stays as neutral context only.
    The gaps are appended under an explicit internal-guidance header so the model
    is told not to disclose the machinery (GEN-08).
    """
    location = "(not stated)"
    if profile.location is not None:
        loc = profile.location
        parts = [loc.remote_preference]
        if loc.base_location:
            parts.append(f"based in {loc.base_location}")
        if loc.open_to_international:
            parts.append("open to international")
        location = ", ".join(parts)

    years = (
        str(profile.years_experience)
        if profile.years_experience is not None
        else "(not stated)"
    )

    return f"""\
=== JOB ===
Title: {job.title}
Company: {job.company}
Description: {job.description or "(none provided)"}
Requirements:
{_lines_or_none(job.requirements)}

=== CANDIDATE PROFILE ===
Skills: {", ".join(profile.skills)}
Seniority: {profile.seniority}
Years of experience: {years}
Location: {location}
CV (verbatim): {profile.raw_cv or "(not stated)"}

=== GAPS (internal guidance, do NOT mention in the letter) ===
{_lines_or_none(match.gaps)}
"""


class Generator(Protocol):
    """The generation LLM port. Adapters return the raw draft text or raise
    ``GeneratorError``; mapping to a ``GenerateResult`` is the service's job."""

    def generate(self, job: Job, profile: Profile, match: MatchResult) -> str: ...


def build_result(raw_draft: str) -> GenerateResult:
    """The single success-side mapper: raw draft -> validated GenerateResult.

    An empty or whitespace-only draft is a failure — a hollow document is worse
    than an honest failure (GEN-13). An over-length draft is advisory prose, so
    it is truncated to ``DRAFT_MAX`` rather than failed closed (GEN-05).
    """
    draft = raw_draft.strip()
    if not draft:
        return GenerateResult.cannot_generate("generation failed")
    return GenerateResult(
        status="generated", draft=draft[:DRAFT_MAX], reason=GENERATED_REASON
    )


class AnthropicGenerator:
    """A `Generator` over the Anthropic SDK: one bounded, single-attempt call.

    The client is built lazily on first use (`max_retries=0` disables the SDK's
    auto-retry, and a bounded `timeout` caps the call), so importing this module,
    creating the app, and running the unit suite need no API key. The draft is a
    single prose cover letter, so this uses a plain `messages.create` and reads
    the text block (AD-032) rather than structured `messages.parse`. Every
    provider failure -- API error, timeout, a refusal or `max_tokens` stop
    reason, or a missing/empty text block -- is wrapped as `GeneratorError` so the
    service can fail closed, never returning a hollow or truncated letter
    (GEN-12/13/27).
    """

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-8",
        timeout: float = 60.0,
        effort: str = "medium",
        max_tokens: int = 2048,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client

    def generate(self, job: Job, profile: Profile, match: MatchResult) -> str:
        client = self._client
        if client is None:
            client = anthropic.Anthropic(max_retries=0, timeout=self.timeout)
            self._client = client
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": render(job, profile, match)}],
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
            )
            stop_reason = response.stop_reason
            text = next(
                (b.text for b in response.content if getattr(b, "type", None) == "text"),
                None,
            )
        except anthropic.AnthropicError as exc:
            # AnthropicError is the SDK's root (covers APIError, APITimeoutError,
            # APIConnectionError, ...). Fail closed.
            raise GeneratorError("the generation call failed") from exc
        except Exception as exc:  # noqa: BLE001
            # Adapter boundary: any other fault (an undeclared SDK error, an
            # unexpected response shape) must fail closed too, never escape as an
            # unhandled 500.
            raise GeneratorError("unexpected generation failure") from exc
        if stop_reason in {"refusal", "max_tokens"}:
            # Non-empty-but-untrustworthy text: a polite decline or a letter cut
            # off mid-sentence is not a trustworthy draft (GEN-27).
            raise GeneratorError(f"unusable stop reason: {stop_reason}")
        if text is None or not text.strip():
            raise GeneratorError("the model returned no letter text")
        return text


def generate_letter(
    job: Job,
    profile: Profile | None,
    matcher: Matcher,
    generator: Generator,
) -> GenerateResult:
    """Orchestrate a generation with no side effects.

    An absent profile short-circuits to ``cannot_generate`` *without* any LLM
    call (GEN-10). The match is recomputed internally for server-authoritative
    gaps (AD-026); a ``cannot_assess`` match short-circuits *without* the
    generation call — no letter without a trustworthy gap analysis (GEN-11).
    Otherwise the generator is called once; any ``GeneratorError`` is logged with
    its traceback and mapped to ``cannot_generate`` (GEN-12). Generate on
    ``strong``/``possible``/``weak`` — a weak fit still has real gaps to frame
    honestly (GEN-04). Pure w.r.t. storage: calls no writes (GEN-16/17).
    """
    if profile is None:
        return GenerateResult.cannot_generate("profile absent")
    match = match_job(job, profile, matcher)
    if match.verdict == "cannot_assess":
        return GenerateResult.cannot_generate("match failed")
    try:
        raw = generator.generate(job, profile, match)
    except GeneratorError:
        logger.exception("generation failed")
        return GenerateResult.cannot_generate("generation failed")
    return build_result(raw)
