"""Unit tests for the eval metric math (T7).

Pure functions, no network, no I/O — the metric math is covered here even though
the eval runner (which calls the real LLM) is offline and non-gating. Inputs are
hand-built (expected_band, MatchResult) pairs (MATCH-15/16/17/18).
"""

from evals.matcher.metrics import (
    cannot_assess_accuracy,
    fabrication_rate,
    precision_recall_strong,
)
from jobpilot.models import MatchResult


def _decided(score: int, gaps=None) -> MatchResult:
    from jobpilot.models import verdict_for_score

    return MatchResult(
        score=score,
        verdict=verdict_for_score(score),
        gaps=gaps or [],
        rationale="x",
    )


# ---------------------------------------------------------------------------
# precision / recall of the strong-vs-not decision (MATCH-16)
# ---------------------------------------------------------------------------


def test_precision_recall_mixed():
    pairs = [
        ("strong", _decided(90)),  # TP
        ("strong", _decided(30)),  # FN (should be strong, called weak)
        ("weak", _decided(80)),  # FP (not strong, called strong)
        ("weak", _decided(10)),  # TN
    ]

    precision, recall = precision_recall_strong(pairs)

    assert precision == 0.5
    assert recall == 0.5


def test_precision_recall_all_strong_correct():
    pairs = [("strong", _decided(90)), ("strong", _decided(80))]

    assert precision_recall_strong(pairs) == (1.0, 1.0)


def test_precision_recall_none_predicted_strong_is_zero_not_crash():
    pairs = [("strong", _decided(30)), ("weak", _decided(10))]

    # No strong predictions: precision denominator is 0 -> 0.0, no ZeroDivision.
    assert precision_recall_strong(pairs) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# fabrication rate on probes (MATCH-17)
# ---------------------------------------------------------------------------


def test_fabrication_rate_counts_unnamed_gap_and_strong_as_leaks():
    probes = [
        ("AWS", _decided(30, gaps=["AWS"])),  # clean: gap named, not strong
        ("AWS", _decided(30, gaps=["Docker"])),  # leak: expected gap not named
        ("AWS", _decided(80, gaps=["AWS"])),  # leak: scored strong despite the gap
    ]

    assert fabrication_rate(probes) == 2 / 3


def test_fabrication_rate_empty_is_zero():
    assert fabrication_rate([]) == 0.0


def test_fabrication_probe_match_is_case_insensitive():
    probes = [("aws", _decided(30, gaps=["Experience with AWS"]))]

    assert fabrication_rate(probes) == 0.0


# ---------------------------------------------------------------------------
# cannot_assess correctness (MATCH-15/18)
# ---------------------------------------------------------------------------


def test_cannot_assess_accuracy():
    pairs = [
        ("cannot_assess", MatchResult.cannot_assess("no profile")),  # correct
        ("weak", _decided(10)),  # correct (neither is cannot_assess)
        ("cannot_assess", _decided(50)),  # wrong (should have abstained)
        ("strong", MatchResult.cannot_assess("timeout")),  # wrong (over-abstained)
    ]

    assert cannot_assess_accuracy(pairs) == 0.5


def test_cannot_assess_accuracy_empty_is_zero():
    assert cannot_assess_accuracy([]) == 0.0
