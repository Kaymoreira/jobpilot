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

from pydantic import BaseModel

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
- Use ONLY the facts in the Profile and the Job below. Never invent skills, \
experience, seniority, or qualifications the Profile does not state. If the \
Profile does not mention something the Job asks for, that is a gap, not an \
assumption in the candidate's favor.

Output format:
- score: an integer from 0 to 100 for overall fit (higher means a better fit).
- rationale: two or three sentences explaining the score, citing only stated \
facts.
- gaps: the Job's stated requirements for which the Profile shows no evidence. \
Use an empty list when the Profile covers everything the Job asks for. Do not \
list a gap you cannot tie to a Job requirement.

Scoring discipline:
- A sparse or thin job posting (little or no description or requirements) does \
NOT justify a strong fit. With little to match against, prefer a low or middling \
score and say why. Never read missing information as a point in the candidate's \
favor.
- Do not reward keyword overlap alone; weigh seniority, core skills, and the \
Job's actual requirements.
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
