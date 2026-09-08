"""Unit tests for the generator prompt (T3).

Covers GEN-07 (grounding), GEN-08 (honest gap framing / non-disclosure), and
GEN-09 (job-language) at the prompt layer. The prompt carries no runtime
authority; these tests assert only that the model is *given* grounded inputs and
the honesty/anti-slop instructions. Whether the model obeys is measured by the
offline eval harness (T7), not asserted here.

Critically, ``render`` OMITS ``salary_expectation`` entirely (AD-032 refinement):
the model cannot leak a figure it never saw.
"""

from jobpilot.generation import SYSTEM_PROMPT, render
from jobpilot.models import Job, MatchResult, Profile, ProfileCreate, SalaryRange


def _job() -> Job:
    return Job(
        id="j1",
        title="Backend Engineer",
        company="Acme Corp",
        description="Build and run services.",
        requirements=["Python", "Kubernetes"],
        created_at="2026-01-01T00:00:00Z",
    )


def _profile_with_salary() -> Profile:
    return Profile.new_from(
        ProfileCreate(
            skills=["Python", "FastAPI"],
            seniority="pleno",
            years_experience=4,
            salary_expectation=[
                SalaryRange(
                    currency="BRL",
                    contract="PJ",
                    floor=12000,
                    target=15000,
                    ceiling=18000,
                )
            ],
            raw_cv="Five years shipping Python services.",
        )
    )


def _match(gaps: list[str]) -> MatchResult:
    return MatchResult(
        score=55, verdict="possible", gaps=gaps, rationale="fits the core"
    )


# ---------------------------------------------------------------------------
# render embeds the grounded inputs (GEN-07)
# ---------------------------------------------------------------------------


def test_render_embeds_job_and_profile_fields():
    text = render(_job(), _profile_with_salary(), _match(["Kubernetes"]))
    assert "Backend Engineer" in text
    assert "Acme Corp" in text
    assert "Build and run services." in text
    assert "Kubernetes" in text  # a requirement
    assert "Python" in text  # a skill
    assert "FastAPI" in text
    assert "pleno" in text
    assert "Five years shipping Python services." in text  # verbatim raw_cv


def test_render_embeds_gaps_under_internal_guidance_header():
    text = render(_job(), _profile_with_salary(), _match(["Kubernetes"]))
    assert "internal guidance" in text.lower()
    assert "do NOT mention" in text or "do not mention" in text.lower()
    assert "Kubernetes" in text


def test_render_shows_none_when_no_gaps():
    text = render(_job(), _profile_with_salary(), _match([]))
    assert "(none)" in text


# ---------------------------------------------------------------------------
# render OMITS salary entirely (AD-032 refinement) — structural non-leak
# ---------------------------------------------------------------------------


def test_render_omits_salary_expectation():
    text = render(_job(), _profile_with_salary(), _match([]))
    assert "12000" not in text
    assert "15000" not in text
    assert "18000" not in text
    assert "BRL" not in text
    assert "salary" not in text.lower()


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT carries the honesty + anti-slop instructions
# ---------------------------------------------------------------------------


def test_system_prompt_has_grounding_instruction():
    lower = SYSTEM_PROMPT.lower()
    assert "only" in lower
    assert "never invent" in lower


def test_system_prompt_has_non_disclosure_and_language_and_salary():
    lower = SYSTEM_PROMPT.lower()
    assert "internal guidance" in lower  # gap machinery hidden
    assert "language of the job" in lower  # GEN-09
    assert "salary" in lower  # no-salary belt-and-suspenders


def test_system_prompt_has_anti_ai_tells_no_em_dash():
    lower = SYSTEM_PROMPT.lower()
    assert "em dash" in lower  # explicit no-em-dash rule
    # and the prompt itself must not contain an em dash
    assert "—" not in SYSTEM_PROMPT
