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
