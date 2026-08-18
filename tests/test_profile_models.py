"""Unit tests for the profile domain models (T1: value objects + ProfileCreate).

Covers BCP-03/-04/-05/-06/-09/-10/-11/-12/-14/-15/-19/-20 at the model layer.
Optional fields are tested by passing them explicitly (Lesson L-001): Pydantic v2
skips validators on defaulted fields, so omission would not exercise the branch.
"""

import pytest
from pydantic import ValidationError

from jobpilot.models import Location, ProfileCreate, SalaryRange

# ---------------------------------------------------------------------------
# skills normalization (BCP-03, BCP-09, BCP-14, BCP-19)
# ---------------------------------------------------------------------------


def test_skills_are_trimmed_and_blanks_dropped():
    profile = ProfileCreate(
        skills=["  k6 ", "", "   ", "playwright"], seniority="pleno"
    )

    assert profile.skills == ["k6", "playwright"]


def test_skills_deduped_case_insensitively_preserving_first_seen_order():
    profile = ProfileCreate(
        skills=[" k6 ", "Playwright", "K6", "playwright", "cypress"],
        seniority="pleno",
    )

    assert profile.skills == ["k6", "Playwright", "cypress"]


def test_skill_over_128_chars_is_rejected():
    with pytest.raises(ValidationError):
        ProfileCreate(skills=["x" * 129], seniority="pleno")


def test_skill_at_128_chars_is_accepted():
    profile = ProfileCreate(skills=["x" * 128], seniority="pleno")

    assert len(profile.skills[0]) == 128


def test_empty_skills_list_is_rejected():
    with pytest.raises(ValidationError):
        ProfileCreate(skills=[], seniority="pleno")


def test_all_blank_skills_is_rejected():
    with pytest.raises(ValidationError):
        ProfileCreate(skills=["   ", "\t", ""], seniority="pleno")


# ---------------------------------------------------------------------------
# seniority enum (BCP-10)
# ---------------------------------------------------------------------------


def test_invalid_seniority_is_rejected():
    with pytest.raises(ValidationError):
        ProfileCreate(skills=["k6"], seniority="SDET III")


@pytest.mark.parametrize(
    "level", ["junior", "pleno", "pleno-senior", "senior"]
)
def test_valid_seniority_values_accepted(level):
    profile = ProfileCreate(skills=["k6"], seniority=level)

    assert profile.seniority == level


# ---------------------------------------------------------------------------
# SalaryRange cross-field rules (BCP-11)
# ---------------------------------------------------------------------------


def test_salary_range_floor_over_ceiling_is_rejected():
    with pytest.raises(ValidationError):
        SalaryRange(
            currency="BRL", contract="CLT", floor=9000, target=8000, ceiling=7000
        )


def test_salary_range_zero_or_negative_is_rejected():
    with pytest.raises(ValidationError):
        SalaryRange(
            currency="BRL", contract="PJ", floor=0, target=5000, ceiling=9000
        )


def test_valid_salary_range_is_accepted():
    salary = SalaryRange(
        currency="BRL", contract="CLT", floor=6000, target=8000, ceiling=10000
    )

    assert (salary.floor, salary.target, salary.ceiling) == (6000, 8000, 10000)


def test_malformed_currency_is_rejected():
    with pytest.raises(ValidationError):
        SalaryRange(
            currency="brl", contract="CLT", floor=1, target=2, ceiling=3
        )


# ---------------------------------------------------------------------------
# duplicate (currency, contract) in salary_expectation (BCP-12, BCP-20)
# ---------------------------------------------------------------------------


def test_duplicate_currency_contract_pair_is_rejected():
    entry = {
        "currency": "BRL",
        "contract": "CLT",
        "floor": 6000,
        "target": 8000,
        "ceiling": 10000,
    }
    with pytest.raises(ValidationError):
        ProfileCreate(
            skills=["k6"], seniority="pleno", salary_expectation=[entry, entry]
        )


def test_distinct_currency_contract_pairs_accepted():
    profile = ProfileCreate(
        skills=["k6"],
        seniority="pleno",
        salary_expectation=[
            SalaryRange(
                currency="BRL",
                contract="CLT",
                floor=6000,
                target=8000,
                ceiling=10000,
            ),
            SalaryRange(
                currency="BRL",
                contract="PJ",
                floor=9000,
                target=11000,
                ceiling=13000,
            ),
        ],
    )

    assert len(profile.salary_expectation) == 2


def test_empty_salary_expectation_list_is_accepted():
    # Empty list = "no expectation stated", not an error (BCP-20).
    profile = ProfileCreate(
        skills=["k6"], seniority="pleno", salary_expectation=[]
    )

    assert profile.salary_expectation == []


# ---------------------------------------------------------------------------
# years_experience bound (BCP-15)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("years", [-1, 61])
def test_years_experience_out_of_range_is_rejected(years):
    with pytest.raises(ValidationError):
        ProfileCreate(skills=["k6"], seniority="pleno", years_experience=years)


def test_years_experience_valid_and_absent_accepted():
    with_years = ProfileCreate(
        skills=["k6"], seniority="pleno", years_experience=8
    )
    absent = ProfileCreate(skills=["k6"], seniority="pleno", years_experience=None)

    assert with_years.years_experience == 8
    assert absent.years_experience is None


# ---------------------------------------------------------------------------
# raw_cv verbatim + cap (BCP-05, BCP-14)
# ---------------------------------------------------------------------------


def test_raw_cv_is_trimmed():
    profile = ProfileCreate(
        skills=["k6"], seniority="pleno", raw_cv="  my cv text  "
    )

    assert profile.raw_cv == "my cv text"


def test_raw_cv_over_50kb_is_rejected():
    with pytest.raises(ValidationError):
        ProfileCreate(
            skills=["k6"], seniority="pleno", raw_cv="x" * (50 * 1024 + 1)
        )


# ---------------------------------------------------------------------------
# optional fields + server-owned fields (BCP-04, BCP-06)
# ---------------------------------------------------------------------------


def test_optional_fields_absent_are_not_fabricated():
    # Passed explicitly (Lesson L-001), not omitted.
    profile = ProfileCreate(
        skills=["k6"],
        seniority="pleno",
        years_experience=None,
        salary_expectation=[],
        location=None,
        raw_cv=None,
    )

    assert profile.years_experience is None
    assert profile.salary_expectation == []
    assert profile.location is None
    assert profile.raw_cv is None


def test_caller_supplied_server_fields_are_dropped():
    profile = ProfileCreate(
        skills=["k6"],
        seniority="pleno",
        created_at="1999-01-01",
        updated_at="1999-01-01",
    )

    dumped = profile.model_dump()
    assert "created_at" not in dumped
    assert "updated_at" not in dumped


def test_location_value_object_is_accepted_and_trimmed():
    location = Location(
        remote_preference="hybrid",
        open_to_international=True,
        base_location="  Ilhéus/BA  ",
        timezone=None,
    )

    assert location.base_location == "Ilhéus/BA"
    assert location.open_to_international is True
    assert location.timezone is None
