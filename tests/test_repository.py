"""Repository tests (T3).

The contract suite runs against BOTH the real sqlite adapter and the in-memory
fake, so the fake cannot diverge (PJS-06, PJS-12, PJS-13, PJS-16). Sqlite-only
tests cover the atomicity failing path (PJS-14).
"""

import sqlite3

import pytest

from jobpilot.models import Job, JobCreate
from jobpilot.repository import RepositoryError, SqliteJobRepository
from tests.fakes import FakeJobRepository


def _job(title: str = "Senior QE", company: str = "Acme", **kw) -> Job:
    return Job.new_from(JobCreate(title=title, company=company, **kw))


# ---------------------------------------------------------------------------
# Port contract: both implementations must pass identical assertions
# ---------------------------------------------------------------------------


@pytest.fixture(params=["sqlite", "fake"])
def repo(request):
    if request.param == "sqlite":
        return SqliteJobRepository(sqlite3.connect(":memory:"))
    return FakeJobRepository()


def test_add_then_get_roundtrip_returns_equal_job(repo):
    job = _job(description="Test all the paths", requirements=["pytest"])

    repo.add(job)

    assert repo.get(job.id) == job


def test_get_unknown_id_returns_none(repo):
    assert repo.get("does-not-exist") is None


def test_list_all_is_newest_first(repo):
    first = _job(title="First")
    second = _job(title="Second")

    repo.add(first)
    repo.add(second)

    assert [j.id for j in repo.list_all()] == [second.id, first.id]


def test_list_all_empty_returns_empty_list(repo):
    assert repo.list_all() == []


def test_requirements_survive_roundtrip(repo):
    job = _job(requirements=["pytest", "playwright", "hypothesis"])

    repo.add(job)

    assert repo.get(job.id).requirements == ["pytest", "playwright", "hypothesis"]


# ---------------------------------------------------------------------------
# Sqlite-only: atomicity / failing path (PJS-14)
# ---------------------------------------------------------------------------


def test_two_adds_create_distinct_rows():
    repo = SqliteJobRepository(sqlite3.connect(":memory:"))

    repo.add(_job(title="A"))
    repo.add(_job(title="B"))

    rows = repo.list_all()
    assert len(rows) == 2
    assert rows[0].id != rows[1].id


def test_failed_insert_raises_and_persists_nothing():
    repo = SqliteJobRepository(sqlite3.connect(":memory:"))
    job = _job()
    repo.add(job)

    # Re-inserting the same id violates the PRIMARY KEY: the write must fail
    # and leave the row count unchanged (no partial write).
    with pytest.raises(RepositoryError):
        repo.add(job)

    assert len(repo.list_all()) == 1
