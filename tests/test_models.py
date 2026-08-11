"""Unit tests for the domain models (T1: JobCreate, T2: Job)."""

import logging

import pytest
from pydantic import ValidationError

from jobpilot.models import JobCreate

# ---------------------------------------------------------------------------
# T1: JobCreate input model (PJS-03, PJS-04, PJS-08, PJS-11, PJS-18, PJS-19)
# ---------------------------------------------------------------------------


def test_title_and_company_are_trimmed():
    job = JobCreate(title="  Senior QE  ", company="\tAcme\n")

    assert job.title == "Senior QE"
    assert job.company == "Acme"


def test_blank_title_is_rejected():
    with pytest.raises(ValidationError):
        JobCreate(title="   ", company="Acme")


def test_blank_company_is_rejected():
    with pytest.raises(ValidationError):
        JobCreate(title="Senior QE", company="")


def test_missing_required_field_is_rejected():
    with pytest.raises(ValidationError):
        JobCreate(company="Acme")  # title missing


def test_title_over_512_chars_is_rejected():
    with pytest.raises(ValidationError):
        JobCreate(title="x" * 513, company="Acme")


def test_company_over_512_chars_is_rejected():
    with pytest.raises(ValidationError):
        JobCreate(title="Senior QE", company="y" * 513)


def test_title_at_512_chars_is_accepted():
    job = JobCreate(title="x" * 512, company="Acme")

    assert len(job.title) == 512


def test_valid_http_link_is_kept_verbatim():
    job = JobCreate(
        title="Senior QE", company="Acme", link="https://jobs.acme.com/123"
    )

    assert job.link == "https://jobs.acme.com/123"


def test_malformed_link_becomes_none_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="jobpilot"):
        job = JobCreate(title="Senior QE", company="Acme", link="not a url")

    assert job.link is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_non_http_scheme_link_becomes_none():
    job = JobCreate(title="Senior QE", company="Acme", link="ftp://acme.com/x")

    assert job.link is None


def test_description_is_trimmed_and_optional():
    with_desc = JobCreate(title="A", company="B", description="  text  ")
    without_desc = JobCreate(title="A", company="B")

    assert with_desc.description == "text"
    assert without_desc.description is None


def test_unknown_and_server_owned_fields_are_dropped():
    job = JobCreate(
        title="A",
        company="B",
        id="attacker-supplied",
        source="scraped",
        created_at="1999-01-01",
    )

    dumped = job.model_dump()
    assert "id" not in dumped
    assert "source" not in dumped
    assert "created_at" not in dumped
