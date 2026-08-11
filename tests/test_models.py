"""Unit tests for the domain models (T1: JobCreate, T2: Job)."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jobpilot.models import Job, JobCreate

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


def test_absent_link_stays_none():
    # An omitted link must never be fabricated into a value (fail-open guard).
    job = JobCreate(title="A", company="B")

    assert job.link is None


def test_explicit_null_link_stays_none():
    # Passing link=None explicitly runs the validator (unlike the default,
    # which Pydantic skips); it must return None, not fabricate a value.
    job = JobCreate(title="A", company="B", link=None)

    assert job.link is None


def test_supplying_a_link_makes_no_outbound_http(monkeypatch):
    import socket

    def _no_network(*args, **kwargs):
        raise AssertionError("M1 must not make outbound HTTP for a pasted link")

    monkeypatch.setattr(socket.socket, "connect", _no_network)

    job = Job.new_from(
        JobCreate(title="A", company="B", link="https://acme.com/123")
    )

    assert job.link == "https://acme.com/123"


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


# ---------------------------------------------------------------------------
# T2: canonical Job + new_from (PJS-02, PJS-05, PJS-07, PJS-13, PJS-15, PJS-16)
# ---------------------------------------------------------------------------


def test_new_from_always_sets_source_pasted():
    job = Job.new_from(JobCreate(title="Senior QE", company="Acme"))

    assert job.source == "pasted"


def test_new_from_generates_unique_ids():
    data = JobCreate(title="Senior QE", company="Acme")

    first = Job.new_from(data)
    second = Job.new_from(data)

    assert first.id != second.id
    assert first.id  # non-empty


def test_new_from_sets_timezone_aware_utc_created_at():
    job = Job.new_from(JobCreate(title="Senior QE", company="Acme"))

    assert isinstance(job.created_at, datetime)
    assert job.created_at.utcoffset() == timedelta(0)


def test_new_from_defaults_description_and_requirements_when_absent():
    job = Job.new_from(JobCreate(title="Senior QE", company="Acme"))

    assert job.description == ""
    assert job.requirements == []


def test_new_from_carries_supplied_fields():
    data = JobCreate(
        title="Senior QE",
        company="Acme",
        description="Test everything",
        requirements=["pytest", "playwright"],
        link="https://acme.com/1",
    )

    job = Job.new_from(data)

    assert job.title == "Senior QE"
    assert job.company == "Acme"
    assert job.description == "Test everything"
    assert job.requirements == ["pytest", "playwright"]
    assert job.link == "https://acme.com/1"


def test_new_from_preserves_unicode_and_emoji():
    data = JobCreate(title="Señor QE 🚀", company="Açme ✨")

    job = Job.new_from(data)

    assert job.title == "Señor QE 🚀"
    assert job.company == "Açme ✨"


def test_caller_cannot_override_source_via_job_create():
    # source is server-owned: JobCreate ignores it, new_from never reads it.
    data = JobCreate(title="A", company="B", source="scraped")

    assert Job.new_from(data).source == "pasted"
