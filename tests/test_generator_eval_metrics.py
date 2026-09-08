"""Unit tests for the generator eval metrics (T7), pure and offline.

The metric math is deterministic string heuristics, so it is unit-tested here;
the runner's real-LLM call is not gated (AD-019/AD-028). A tiny corpus makes
these numbers directional, not robust (GEN-26). These tests pin the fabrication,
gap-honesty, language, and thin-job-padding measurements (GEN-22..25).
"""

from evals.generator import metrics


# ---------------------------------------------------------------------------
# fabrication rate (GEN-22)
# ---------------------------------------------------------------------------


def test_fabrication_rate_counts_leaked_forbidden_facts():
    items = [
        (["AWS", "PhD"], "I have deep AWS experience."),  # leaks "AWS"
        (["Kubernetes"], "I ship Python services daily."),  # clean
    ]
    assert metrics.fabrication_rate(items) == 0.5


def test_fabrication_rate_is_zero_when_no_leaks():
    items = [(["AWS"], "I write Python."), (["Go"], "I use FastAPI.")]
    assert metrics.fabrication_rate(items) == 0.0


def test_fabrication_rate_empty_is_zero():
    assert metrics.fabrication_rate([]) == 0.0


def test_fabrication_is_case_insensitive():
    items = [(["kubernetes"], "Strong KUBERNETES background.")]
    assert metrics.fabrication_rate(items) == 1.0


# ---------------------------------------------------------------------------
# gap-honesty (GEN-23)
# ---------------------------------------------------------------------------


def test_gap_claimed_when_possession_marker_shares_the_sentence():
    items = [("Kubernetes", "I am an expert in Kubernetes and Go.")]
    assert metrics.gap_claim_rate(items) == 1.0


def test_gap_framed_honestly_is_not_a_claim():
    items = [("Kubernetes", "I am eager to grow my Kubernetes skills.")]
    assert metrics.gap_claim_rate(items) == 0.0


def test_gap_not_mentioned_is_not_a_claim():
    items = [("Kubernetes", "I write Python and love testing.")]
    assert metrics.gap_claim_rate(items) == 0.0


# ---------------------------------------------------------------------------
# language appropriateness (GEN-24)
# ---------------------------------------------------------------------------


def test_language_matches_english():
    letter = "I would be glad to join the team and help with the work."
    assert metrics.language_matches("en", letter) is True


def test_language_matches_portuguese():
    letter = "Gostaria de fazer parte da equipe e ajudar com o trabalho."
    assert metrics.language_matches("pt", letter) is True


def test_language_mismatch_detected():
    letter = "Gostaria de fazer parte da equipe de trabalho."
    assert metrics.language_matches("en", letter) is False


def test_language_match_rate_over_items():
    items = [
        ("en", "I would be glad to help with the work."),
        ("pt", "Gostaria de ajudar com o trabalho da equipe."),
    ]
    assert metrics.language_match_rate(items) == 1.0


# ---------------------------------------------------------------------------
# thin-job padding (GEN-25)
# ---------------------------------------------------------------------------


def test_thin_job_padding_flags_invented_specifics():
    # A thin job (title/company only) whose letter invents a concrete stack.
    items = [(["Kubernetes", "5 years"], "I have 5 years on Kubernetes at scale.")]
    assert metrics.thin_job_padding_rate(items) == 1.0


def test_thin_job_no_padding_is_zero():
    items = [(["Kubernetes"], "I am excited about this role and your mission.")]
    assert metrics.thin_job_padding_rate(items) == 0.0
