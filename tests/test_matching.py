"""Unit tests for the matching core (T2): interpret + match_job.

Everything runs offline via ``FakeMatcher`` (no network). These tests pin the
fail-closed contract: every uncertain or malformed judgment funnels to
cannot_assess with a null score, never a clamped or high one
(MATCH-03/04/06/07/08/10/13/14/20).
"""

import logging

from jobpilot.matching import MatcherError, MatcherLLMOutput, interpret, match_job
from jobpilot.models import GAP_MAX, Job, JobCreate, Profile, ProfileCreate

from tests.fakes import FakeMatcher


def _job() -> Job:
    return Job.new_from(JobCreate(title="QA Engineer", company="Acme"))


def _profile() -> Profile:
    return Profile.new_from(ProfileCreate(skills=["k6"], seniority="pleno"))


# ---------------------------------------------------------------------------
# interpret: happy path (MATCH-01/02)
# ---------------------------------------------------------------------------


def test_interpret_valid_output_becomes_decided_result_with_band_verdict():
    result = interpret(
        MatcherLLMOutput(score=82, rationale="  strong overlap  ", gaps=["AWS"])
    )

    assert result.score == 82
    assert result.verdict == "strong"
    assert result.gaps == ["AWS"]
    assert result.rationale == "strong overlap"


# ---------------------------------------------------------------------------
# interpret: never clamp an out-of-range score (MATCH-08, MATCH-10)
# ---------------------------------------------------------------------------


def test_interpret_score_above_range_fails_closed_and_is_not_clamped():
    result = interpret(MatcherLLMOutput(score=150, rationale="great"))

    assert result.verdict == "cannot_assess"
    assert result.score is None  # never clamped to 100


def test_interpret_negative_score_fails_closed():
    result = interpret(MatcherLLMOutput(score=-1, rationale="bad"))

    assert result.verdict == "cannot_assess"
    assert result.score is None


# ---------------------------------------------------------------------------
# interpret: empty rationale is unusable (edge case)
# ---------------------------------------------------------------------------


def test_interpret_empty_rationale_fails_closed():
    result = interpret(MatcherLLMOutput(score=80, rationale="   "))

    assert result.verdict == "cannot_assess"
    assert result.score is None


# ---------------------------------------------------------------------------
# interpret: gaps normalization (MATCH-03)
# ---------------------------------------------------------------------------


def test_interpret_trims_and_drops_blank_gaps():
    result = interpret(
        MatcherLLMOutput(score=50, rationale="ok", gaps=["  AWS ", "", "   ", "Go"])
    )

    assert result.gaps == ["AWS", "Go"]


def test_interpret_truncates_over_long_gap_and_caps_count():
    raw = MatcherLLMOutput(
        score=50,
        rationale="ok",
        gaps=["x" * (GAP_MAX + 10)] + [f"gap {i}" for i in range(30)],
    )

    result = interpret(raw)

    assert len(result.gaps) == 20  # MAX_GAPS
    assert all(len(g) <= GAP_MAX for g in result.gaps)
    assert len(result.gaps[0]) == GAP_MAX  # truncated, not dropped


# ---------------------------------------------------------------------------
# match_job: absent profile short-circuits WITHOUT calling the LLM (MATCH-06)
# ---------------------------------------------------------------------------


def test_match_job_absent_profile_returns_cannot_assess_without_llm_call():
    matcher = FakeMatcher(MatcherLLMOutput(score=90, rationale="unused"))

    result = match_job(_job(), None, matcher)

    assert result.verdict == "cannot_assess"
    assert result.score is None
    assert matcher.evaluate_called is False


# ---------------------------------------------------------------------------
# match_job: happy path (MATCH-01)
# ---------------------------------------------------------------------------


def test_match_job_success_returns_interpreted_result():
    matcher = FakeMatcher(MatcherLLMOutput(score=30, rationale="thin overlap"))

    result = match_job(_job(), _profile(), matcher)

    assert result.score == 30
    assert result.verdict == "weak"
    assert matcher.evaluate_called is True


# ---------------------------------------------------------------------------
# match_job: LLM failure -> cannot_assess + logged cause (MATCH-07)
# ---------------------------------------------------------------------------


def test_match_job_matcher_error_fails_closed_and_logs_the_cause(caplog):
    matcher = FakeMatcher(error=MatcherError("boom"))

    with caplog.at_level(logging.ERROR, logger="jobpilot"):
        result = match_job(_job(), _profile(), matcher)

    assert result.verdict == "cannot_assess"
    assert result.score is None
    assert any(record.levelno == logging.ERROR for record in caplog.records)
    assert any("boom" in (record.exc_text or "") for record in caplog.records)


# ---------------------------------------------------------------------------
# match_job: unusable content is logged for diagnosability (MATCH-08)
# ---------------------------------------------------------------------------


def test_match_job_unusable_output_logs_a_warning(caplog):
    matcher = FakeMatcher(MatcherLLMOutput(score=150, rationale="great"))

    with caplog.at_level(logging.WARNING, logger="jobpilot"):
        result = match_job(_job(), _profile(), matcher)

    assert result.verdict == "cannot_assess"
    assert any(record.levelno == logging.WARNING for record in caplog.records)
