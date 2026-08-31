"""Unit tests for the matcher prompt (T3): SYSTEM_PROMPT + render.

The prompt carries no runtime authority — grounding is prompt-intended and
eval-measured, never enforced at runtime. These tests pin the prompt's key
commitments (grounding, output format, thin-job caution) and that render()
faithfully embeds the Job and Profile without inventing content
(MATCH-03 grounding intent, MATCH-19 thin-job).
"""

from jobpilot.matching import SYSTEM_PROMPT, render
from jobpilot.models import Job, JobCreate, Location, Profile, ProfileCreate, SalaryRange


def _full_profile() -> Profile:
    return Profile.new_from(
        ProfileCreate(
            skills=["k6", "Playwright"],
            seniority="pleno-senior",
            years_experience=8,
            salary_expectation=[
                SalaryRange(
                    currency="BRL", contract="CLT", floor=6000, target=8000, ceiling=10000
                )
            ],
            location=Location(remote_preference="remote", base_location="Ilhéus/BA"),
            raw_cv="Led k6 performance testing and Terraform IaC at Acme.",
        )
    )


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT commitments (MATCH-03 grounding, output format, MATCH-19)
# ---------------------------------------------------------------------------


def test_system_prompt_states_grounding_rule():
    lowered = SYSTEM_PROMPT.lower()

    assert "only" in lowered
    assert "never invent" in lowered or "do not invent" in lowered


def test_system_prompt_defines_the_output_format():
    lowered = SYSTEM_PROMPT.lower()

    assert "score" in lowered
    assert "0" in SYSTEM_PROMPT and "100" in SYSTEM_PROMPT
    assert "rationale" in lowered
    assert "gaps" in lowered


def test_system_prompt_cautions_against_scoring_thin_jobs_strong():
    lowered = SYSTEM_PROMPT.lower()

    assert "sparse" in lowered or "thin" in lowered or "little" in lowered
    assert "strong" in lowered


def test_system_prompt_weighs_core_over_peripheral_skills():
    lowered = SYSTEM_PROMPT.lower()

    assert "core" in lowered
    assert "nice-to-have" in lowered or "peripheral" in lowered


def test_system_prompt_is_skeptical_of_long_requirement_lists():
    lowered = SYSTEM_PROMPT.lower()

    assert "skepticism" in lowered or "skeptic" in lowered or "do not actually use" in lowered


def test_system_prompt_treats_gaps_as_informational_not_rejection():
    lowered = SYSTEM_PROMPT.lower()

    assert "informational" in lowered
    assert "reject" in lowered


# ---------------------------------------------------------------------------
# render embeds the Job and Profile (MATCH-03 grounding)
# ---------------------------------------------------------------------------


def test_render_embeds_job_fields_and_requirements():
    job = Job.new_from(
        JobCreate(
            title="QA Engineer",
            company="Acme",
            description="Own the test strategy.",
            requirements=["AWS", "k6"],
        )
    )

    rendered = render(job, _full_profile())

    assert "QA Engineer" in rendered
    assert "Acme" in rendered
    assert "Own the test strategy." in rendered
    assert "AWS" in rendered
    assert "k6" in rendered


def test_render_embeds_profile_skills_and_seniority():
    job = Job.new_from(JobCreate(title="QA Engineer", company="Acme"))

    rendered = render(job, _full_profile())

    assert "k6" in rendered
    assert "Playwright" in rendered
    assert "pleno-senior" in rendered


def test_render_embeds_raw_cv_so_cv_only_skills_are_visible():
    job = Job.new_from(JobCreate(title="QA Engineer", company="Acme"))

    rendered = render(job, _full_profile())

    # The verbatim CV is the M2 source of truth; a skill stated only in the CV
    # prose (Terraform, absent from the structured skills list) must reach the
    # model so it is not flagged as a false gap.
    assert "Led k6 performance testing and Terraform IaC at Acme." in rendered
    assert "Terraform" in rendered


def test_render_without_raw_cv_marks_it_not_stated():
    job = Job.new_from(JobCreate(title="QA Engineer", company="Acme"))
    profile = Profile.new_from(ProfileCreate(skills=["k6"], seniority="junior"))

    rendered = render(job, profile)

    assert "(not stated)" in rendered


def test_render_thin_job_produces_text_without_inventing_content():
    # Title/company only — no description, no requirements (MATCH-19 probe).
    job = Job.new_from(JobCreate(title="Engineer", company="Startup"))
    profile = Profile.new_from(ProfileCreate(skills=["k6"], seniority="junior"))

    rendered = render(job, profile)

    assert "Engineer" in rendered
    assert "Startup" in rendered
    # No fabricated requirement text leaks in.
    assert "AWS" not in rendered
