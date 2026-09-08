"""Unit tests for the generation core (T2), all offline via fakes.

Covers the success-side mapper ``build_result`` and the side-effect-free
``generate_letter`` orchestration: the profile-absent short-circuit (GEN-10, no
LLM call), the match-``cannot_assess`` short-circuit (GEN-11, no generation
call), generate-on-weak (GEN-04), the generation-error funnel (GEN-12), and the
empty-draft / over-length handling (GEN-05/13). Every uncertainty converges on
``cannot_generate`` (GEN-20).
"""

import logging

from jobpilot.generation import GeneratorError, build_result, generate_letter
from jobpilot.matching import MatcherError, MatcherLLMOutput
from jobpilot.models import DRAFT_MAX, Job, Profile, ProfileCreate
from tests.fakes import FakeGenerator, FakeMatcher

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _job() -> Job:
    return Job(
        id="j1",
        title="Backend Engineer",
        company="Acme",
        description="Build APIs",
        requirements=["Python", "Kubernetes"],
        created_at="2026-01-01T00:00:00Z",
    )


def _profile() -> Profile:
    return Profile.new_from(
        ProfileCreate(skills=["Python"], seniority="pleno", raw_cv="I write Python.")
    )


def _llm(score: int) -> MatcherLLMOutput:
    return MatcherLLMOutput(score=score, rationale="ok", gaps=["Kubernetes"])


# ---------------------------------------------------------------------------
# build_result (GEN-05/13)
# ---------------------------------------------------------------------------


def test_build_result_wraps_a_normal_draft():
    result = build_result("Dear team, I'd love to join.")
    assert result.status == "generated"
    assert result.draft == "Dear team, I'd love to join."
    assert result.reason == "ok"


def test_build_result_empty_is_cannot_generate():
    result = build_result("   \n\t ")
    assert result.status == "cannot_generate"
    assert result.draft is None


def test_build_result_truncates_over_draft_max():
    result = build_result("x" * (DRAFT_MAX + 500))
    assert result.status == "generated"
    assert result.draft is not None
    assert len(result.draft) == DRAFT_MAX


# ---------------------------------------------------------------------------
# generate_letter: fail-closed short-circuits
# ---------------------------------------------------------------------------


def test_absent_profile_short_circuits_no_llm_call():
    matcher = FakeMatcher(_llm(80))
    generator = FakeGenerator("letter")
    result = generate_letter(_job(), None, matcher, generator)
    assert result.status == "cannot_generate"
    assert result.draft is None
    assert result.reason == "profile absent"
    assert matcher.evaluate_called is False
    assert generator.generate_called is False


def test_match_cannot_assess_short_circuits_no_generation(caplog):
    # A matcher that raises MatcherError -> match_job returns cannot_assess -> no gen.
    matcher = FakeMatcher(error=MatcherError("the matcher call failed"))
    generator = FakeGenerator("letter")
    with caplog.at_level(logging.ERROR, logger="jobpilot"):
        result = generate_letter(_job(), _profile(), matcher, generator)
    assert result.status == "cannot_generate"
    assert result.reason == "match failed"
    assert generator.generate_called is False


def test_match_cannot_assess_from_bad_output_short_circuits():
    # Out-of-range score -> interpret -> cannot_assess -> no generation.
    matcher = FakeMatcher(MatcherLLMOutput(score=150, rationale="x"))
    generator = FakeGenerator("letter")
    result = generate_letter(_job(), _profile(), matcher, generator)
    assert result.status == "cannot_generate"
    assert result.reason == "match failed"
    assert generator.generate_called is False


# ---------------------------------------------------------------------------
# generate_letter: generate on strong / possible / weak (GEN-04)
# ---------------------------------------------------------------------------


def test_weak_verdict_still_generates():
    matcher = FakeMatcher(_llm(20))  # weak band
    generator = FakeGenerator("A weak-fit but honest letter.")
    result = generate_letter(_job(), _profile(), matcher, generator)
    assert result.status == "generated"
    assert result.draft == "A weak-fit but honest letter."
    assert generator.generate_called is True


def test_strong_verdict_generates():
    matcher = FakeMatcher(_llm(90))
    generator = FakeGenerator("A strong-fit letter.")
    result = generate_letter(_job(), _profile(), matcher, generator)
    assert result.status == "generated"


# ---------------------------------------------------------------------------
# generate_letter: generation failure funnel (GEN-12/13)
# ---------------------------------------------------------------------------


def test_generator_error_is_cannot_generate_and_logged(caplog):
    matcher = FakeMatcher(_llm(60))
    generator = FakeGenerator(error=GeneratorError("boom"))
    with caplog.at_level(logging.ERROR, logger="jobpilot"):
        result = generate_letter(_job(), _profile(), matcher, generator)
    assert result.status == "cannot_generate"
    assert result.draft is None
    assert result.reason == "generation failed"
    assert any("generation failed" in r.message for r in caplog.records)


def test_empty_generated_draft_is_cannot_generate():
    matcher = FakeMatcher(_llm(60))
    generator = FakeGenerator("   ")
    result = generate_letter(_job(), _profile(), matcher, generator)
    assert result.status == "cannot_generate"
    assert result.draft is None
