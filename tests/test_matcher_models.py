"""Unit tests for the Matcher domain contract (T1).

Covers MATCH-02 (score bands), MATCH-03 (gaps cap), MATCH-04 (rationale cap),
MATCH-10 (no high score / non-null under uncertainty), and MATCH-20
(cannot_assess => empty gaps) at the model layer.

The self-validating ``MatchResult`` is the structural anti-fail-open guard:
uncertainty can never be constructed as a decided, high-scoring result. Optional
fields are exercised explicitly (Lesson L-001): Pydantic v2 skips validators on
defaulted fields, so ``gaps=[]`` is passed, never omitted.
"""

import pytest
from pydantic import ValidationError

from jobpilot.models import (
    GAP_MAX,
    MAX_GAPS,
    POSSIBLE_MAX,
    RATIONALE_MAX,
    WEAK_MAX,
    MatchResult,
    verdict_for_score,
)

# ---------------------------------------------------------------------------
# verdict_for_score band function incl. boundaries (MATCH-02)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "weak"),
        (WEAK_MAX, "weak"),  # 39
        (WEAK_MAX + 1, "possible"),  # 40
        (POSSIBLE_MAX, "possible"),  # 74
        (POSSIBLE_MAX + 1, "strong"),  # 75
        (100, "strong"),
    ],
)
def test_verdict_for_score_bands_and_boundaries(score, expected):
    assert verdict_for_score(score) == expected


# ---------------------------------------------------------------------------
# decided MatchResult happy path (MATCH-01/02)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "verdict"),
    [(10, "weak"), (39, "weak"), (40, "possible"), (74, "possible"), (75, "strong"), (100, "strong")],
)
def test_decided_result_with_matching_band_is_accepted(score, verdict):
    result = MatchResult(score=score, verdict=verdict, gaps=[], rationale="ok")

    assert result.score == score
    assert result.verdict == verdict


# ---------------------------------------------------------------------------
# cannot_assess constructor (MATCH-10, MATCH-20)
# ---------------------------------------------------------------------------


def test_cannot_assess_yields_null_score_empty_gaps_trimmed_reason():
    result = MatchResult.cannot_assess("  the model timed out  ")

    assert result.score is None
    assert result.verdict == "cannot_assess"
    assert result.gaps == []
    assert result.rationale == "the model timed out"


def test_cannot_assess_reason_is_truncated_to_the_rationale_cap():
    result = MatchResult.cannot_assess("x" * (RATIONALE_MAX + 50))

    assert len(result.rationale) == RATIONALE_MAX


# ---------------------------------------------------------------------------
# validator: cannot_assess must be null-score + empty-gaps (MATCH-10, MATCH-20)
# ---------------------------------------------------------------------------


def test_cannot_assess_with_a_score_is_rejected():
    with pytest.raises(ValidationError):
        MatchResult(score=90, verdict="cannot_assess", gaps=[], rationale="x")


def test_cannot_assess_with_non_empty_gaps_is_rejected():
    with pytest.raises(ValidationError):
        MatchResult(
            score=None, verdict="cannot_assess", gaps=["k6"], rationale="x"
        )


# ---------------------------------------------------------------------------
# validator: decided verdict consistency (MATCH-10)
# ---------------------------------------------------------------------------


def test_decided_verdict_contradicting_its_band_is_rejected():
    # 90 is a "strong" score; claiming "weak" must fail construction.
    with pytest.raises(ValidationError):
        MatchResult(score=90, verdict="weak", gaps=[], rationale="x")


def test_decided_verdict_with_null_score_is_rejected():
    with pytest.raises(ValidationError):
        MatchResult(score=None, verdict="strong", gaps=[], rationale="x")


@pytest.mark.parametrize("score", [-1, 101, 150])
def test_out_of_range_score_is_rejected(score):
    with pytest.raises(ValidationError):
        MatchResult(
            score=score, verdict=verdict_for_score(max(0, min(100, score))), gaps=[], rationale="x"
        )


# ---------------------------------------------------------------------------
# validator: bounds on rationale and gaps (MATCH-03, MATCH-04)
# ---------------------------------------------------------------------------


def test_over_length_rationale_is_rejected():
    with pytest.raises(ValidationError):
        MatchResult(
            score=80, verdict="strong", gaps=[], rationale="x" * (RATIONALE_MAX + 1)
        )


def test_more_than_max_gaps_is_rejected():
    with pytest.raises(ValidationError):
        MatchResult(
            score=80,
            verdict="strong",
            gaps=[f"gap {i}" for i in range(MAX_GAPS + 1)],
            rationale="x",
        )


def test_a_gap_over_the_char_cap_is_rejected():
    with pytest.raises(ValidationError):
        MatchResult(
            score=80, verdict="strong", gaps=["x" * (GAP_MAX + 1)], rationale="x"
        )


def test_gaps_at_the_caps_are_accepted():
    result = MatchResult(
        score=80,
        verdict="strong",
        gaps=[f"gap {i}" for i in range(MAX_GAPS)],
        rationale="x",
    )

    assert len(result.gaps) == MAX_GAPS


def test_empty_gaps_accepted_explicitly():
    # Passed explicitly (Lesson L-001), not omitted.
    result = MatchResult(score=80, verdict="strong", gaps=[], rationale="ok")

    assert result.gaps == []
