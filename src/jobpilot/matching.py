"""The matcher: an LLM behind a swappable port, plus the fail-closed mapper.

The port (`Matcher`) hides a non-deterministic LLM so the whole decision path is
unit-testable offline via a fake. `MatcherLLMOutput` is the *loose, untrusted*
shape the model is asked to return; `interpret()` is the single place that turns
that raw judgment (or any failure) into a validated `MatchResult`. Every
fail-open path funnels through here, so "uncertainty -> cannot_assess + null" is
enforced in exactly one function.
"""

import logging
from typing import Protocol

import anthropic
from pydantic import BaseModel, ValidationError

from jobpilot.models import (
    GAP_MAX,
    MAX_GAPS,
    RATIONALE_MAX,
    Job,
    MatchResult,
    Profile,
    verdict_for_score,
)

logger = logging.getLogger("jobpilot")


class MatcherError(Exception):
    """Raised by an adapter when it cannot produce a judgment (API error,
    timeout, refusal, incomplete/unparseable output)."""


class MatcherLLMOutput(BaseModel):
    """The loose wire contract the LLM is asked to return.

    Deliberately *not* range-validated: an out-of-range ``score`` is accepted
    here and rejected by ``interpret()`` so the "never clamp, fail closed" path
    is deterministically testable via the fake (and because structured outputs
    strip numeric bounds from the schema anyway). Unknown fields are ignored.
    """

    score: int
    rationale: str
    gaps: list[str] = []


class Matcher(Protocol):
    """The LLM port. Adapters return a raw judgment or raise ``MatcherError``;
    mapping to a ``MatchResult`` is the service's job, never the adapter's."""

    def evaluate(self, job: Job, profile: Profile) -> MatcherLLMOutput: ...


SYSTEM_PROMPT = """\
You score how well a candidate fits a specific job. You are advisory only: your \
output helps a human decide, and is never acted on automatically.

Grounding rule (strict):
- Use ONLY the facts in the Profile and the Job below. The Profile is BOTH the \
structured fields AND the candidate's raw CV text; a skill or experience stated \
only in the CV prose still counts, so do not flag it as a gap. Never invent \
skills, experience, seniority, or qualifications the Profile does not contain. \
If the Job asks for something the Profile mentions nowhere, that is a gap, not \
an assumption in the candidate's favor.

Output format:
- score: an integer from 0 to 100 for overall fit (higher means a better fit).
- rationale: two or three sentences explaining the score, citing only stated \
facts.
- gaps: the Job's stated requirements for which the Profile shows no evidence. \
Use an empty list when the Profile covers everything the Job asks for. Do not \
list a gap you cannot tie to a Job requirement.

Scoring discipline:
- Weigh CORE requirements far more than nice-to-haves. A candidate who is strong \
on the core of the role should still score well with a few peripheral or \
secondary skills missing. Do not tank the score over a handful of minor gaps.
- Treat long requirement lists with skepticism: postings routinely list entire \
stacks they do not actually use day to day, so missing a few items from a long, \
kitchen-sink list is weak evidence of a poor fit.
- A sparse or thin job posting (little or no description or requirements) does \
NOT justify a strong fit. With little to match against, prefer a low or middling \
score and say why. Never read missing information as a point in the candidate's \
favor.
- Do not reward keyword overlap alone; weigh seniority, core skills, and the \
Job's actual requirements.

Gaps are informational, not a verdict:
- List gaps honestly and completely regardless of the score. They inform the \
human reviewer and the downstream tailoring step; a gap is never itself a reason \
to reject. A candidate can score well and still have listed gaps.
"""


def _lines_or_none(items: list[str]) -> str:
    if not items:
        return "(none listed)"
    return "\n".join(f"- {item}" for item in items)


def render(job: Job, profile: Profile) -> str:
    """Render the Job + Profile into the user-message content for the matcher.

    Embeds only stated facts; absent optional fields are shown as "(not stated)"
    so the model never has to infer whether silence means anything.
    """
    salary = "(not stated)"
    if profile.salary_expectation:
        salary = "; ".join(
            f"{s.currency} {s.contract} {s.floor}-{s.target}-{s.ceiling}"
            for s in profile.salary_expectation
        )

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
Salary expectations: {salary}
Location: {location}
CV (verbatim): {profile.raw_cv or "(not stated)"}
"""


def interpret(raw: MatcherLLMOutput) -> MatchResult:
    """The single fail-closed mapper: raw judgment -> validated MatchResult.

    An out-of-range score or an empty rationale becomes ``cannot_assess`` (never
    clamped, MATCH-08). Gaps are advisory prose, so they are trimmed/capped
    rather than failed closed (MATCH-03); the rationale is truncated (MATCH-04).
    """
    if not 0 <= raw.score <= 100:
        return MatchResult.cannot_assess("model returned an out-of-range score")
    if not raw.rationale.strip():
        return MatchResult.cannot_assess("model returned an empty rationale")
    gaps = [g.strip()[:GAP_MAX] for g in raw.gaps if g.strip()][:MAX_GAPS]
    return MatchResult(
        score=raw.score,
        verdict=verdict_for_score(raw.score),
        gaps=gaps,
        rationale=raw.rationale.strip()[:RATIONALE_MAX],
    )


class AnthropicMatcher:
    """A `Matcher` over the Anthropic SDK: one bounded, single-attempt call.

    The client is built lazily on first use (`max_retries=0` disables the SDK's
    auto-retry, and a bounded `timeout` caps the call), so importing this module,
    creating the app, and running the unit suite need no API key. Every provider
    failure — API error, timeout, refusal, truncation, or unparseable output —
    is wrapped as `MatcherError` so the service can fail closed (MATCH-07/08).
    """

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-8",
        timeout: float = 60.0,
        effort: str = "medium",
        max_tokens: int = 8192,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client

    def evaluate(self, job: Job, profile: Profile) -> MatcherLLMOutput:
        client = self._client
        if client is None:
            client = anthropic.Anthropic(max_retries=0, timeout=self.timeout)
            self._client = client
        try:
            response = client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": render(job, profile)}],
                output_format=MatcherLLMOutput,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
            )
            stop_reason = response.stop_reason
            parsed = response.parsed_output
        except (anthropic.AnthropicError, ValidationError) as exc:
            # AnthropicError is the SDK's root (covers APIError, APITimeoutError,
            # APIConnectionError, ...); ValidationError is a structured-output
            # parse failure. Both fail closed.
            raise MatcherError("the matcher call failed") from exc
        except Exception as exc:  # noqa: BLE001
            # Adapter boundary: this is where a non-deterministic dependency is
            # translated into a domain contract. Any other fault (an undeclared
            # SDK error, an unexpected response shape) must fail closed too, never
            # escape as an unhandled 500.
            raise MatcherError("unexpected matcher failure") from exc
        if stop_reason in {"refusal", "max_tokens"}:
            raise MatcherError(f"unusable stop reason: {stop_reason}")
        if parsed is None:
            raise MatcherError("the model returned no parsed output")
        return parsed


def match_job(job: Job, profile: Profile | None, matcher: Matcher) -> MatchResult:
    """Orchestrate a match with no side effects.

    An absent profile short-circuits to ``cannot_assess`` *without* calling the
    LLM (MATCH-06). Any ``MatcherError`` is logged with its traceback server-side
    and mapped to ``cannot_assess`` (MATCH-07). Unusable-but-parsed content is
    logged as a warning so it is diagnosable too.
    """
    if profile is None:
        return MatchResult.cannot_assess("no profile has been authored")
    try:
        raw = matcher.evaluate(job, profile)
    except MatcherError:
        logger.exception("matcher evaluation failed")
        return MatchResult.cannot_assess("the evaluation could not be completed")
    result = interpret(raw)
    if result.verdict == "cannot_assess":
        logger.warning("unusable matcher output: %r", raw)
    return result
