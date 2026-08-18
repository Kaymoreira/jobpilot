"""Profile repository tests (T3).

The contract suite runs against BOTH the real sqlite adapter and the in-memory
fake, so the fake used by the route tests cannot diverge (BCP-04, BCP-05, BCP-07,
BCP-18, BCP-20). Sqlite-only tests cover the atomicity failing path and the
single-row invariant (BCP-16, BCP-17).
"""

import sqlite3

import pytest

from jobpilot.models import Location, Profile, ProfileCreate, SalaryRange
from jobpilot.repository import RepositoryError, SqliteProfileRepository
from tests.fakes import FakeProfileRepository


def _profile(*, seniority: str = "pleno", created_at=None, **fields) -> Profile:
    data = ProfileCreate(
        skills=fields.pop("skills", ["k6"]), seniority=seniority, **fields
    )
    return Profile.new_from(data, created_at=created_at)


# ---------------------------------------------------------------------------
# Port contract: both implementations must pass identical assertions
# ---------------------------------------------------------------------------


@pytest.fixture(params=["sqlite", "fake"])
def repo(request):
    if request.param == "sqlite":
        return SqliteProfileRepository(sqlite3.connect(":memory:"))
    return FakeProfileRepository()


def test_get_on_empty_store_returns_none(repo):
    assert repo.get() is None


def test_upsert_then_get_returns_equal_profile(repo):
    profile = _profile(
        seniority="senior",
        years_experience=8,
        salary_expectation=[
            SalaryRange(
                currency="BRL",
                contract="CLT",
                floor=6000,
                target=8000,
                ceiling=10000,
            )
        ],
        location=Location(remote_preference="remote", base_location="Ilhéus/BA"),
        raw_cv="my cv 🚀",
    )

    repo.upsert(profile)

    assert repo.get() == profile


def test_second_upsert_replaces_and_preserves_passed_created_at(repo):
    first = _profile(seniority="pleno")
    repo.upsert(first)

    replacement = _profile(
        seniority="senior",
        years_experience=10,
        created_at=first.created_at,
    )
    repo.upsert(replacement)

    stored = repo.get()
    assert stored.seniority == "senior"
    assert stored.years_experience == 10
    assert stored.created_at == first.created_at


def test_skills_salary_and_location_survive_roundtrip(repo):
    profile = _profile(
        skills=["k6", "playwright"],
        salary_expectation=[
            SalaryRange(
                currency="USD",
                contract="PJ",
                floor=1,
                target=2,
                ceiling=3,
            )
        ],
        location=Location(remote_preference="hybrid", timezone="America/Bahia"),
    )

    repo.upsert(profile)
    stored = repo.get()

    assert stored.skills == ["k6", "playwright"]
    assert stored.salary_expectation == profile.salary_expectation
    assert stored.location == profile.location


def test_absent_location_and_empty_salary_roundtrip_as_absent(repo):
    profile = _profile(location=None, salary_expectation=[])

    repo.upsert(profile)
    stored = repo.get()

    assert stored.location is None
    assert stored.salary_expectation == []


# ---------------------------------------------------------------------------
# Sqlite-only: atomicity failing path + single-row invariant
# ---------------------------------------------------------------------------


class _FailOnInsert:
    """Wraps a real connection but raises on INSERT, to force a write failure
    while leaving the previously committed row readable."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, *args, **kwargs):
        if sql.lstrip().upper().startswith("INSERT"):
            raise sqlite3.OperationalError("disk I/O error")
        return self._conn.execute(sql, *args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()


def test_failed_upsert_raises_and_leaves_prior_profile_unchanged():
    conn = sqlite3.connect(":memory:")
    repo = SqliteProfileRepository(conn)
    repo.upsert(_profile(seniority="pleno"))

    repo._conn = _FailOnInsert(conn)
    with pytest.raises(RepositoryError):
        repo.upsert(_profile(seniority="senior"))

    repo._conn = conn
    assert repo.get().seniority == "pleno"


def test_repeated_upserts_keep_a_single_row():
    conn = sqlite3.connect(":memory:")
    repo = SqliteProfileRepository(conn)

    repo.upsert(_profile(seniority="junior"))
    repo.upsert(_profile(seniority="pleno"))
    repo.upsert(_profile(seniority="senior"))

    count = conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0]
    assert count == 1
    assert repo.get().seniority == "senior"
