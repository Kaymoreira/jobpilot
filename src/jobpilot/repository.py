"""Persistence for jobs, behind a swappable port.

`JobRepository` is the port; `SqliteJobRepository` is the M1 adapter over raw
`sqlite3`. Keeping the domain `Job` free of any ORM lets the canonical model stay
storage-agnostic and makes the failing path (a write error) trivial to inject in
tests.
"""

import json
import sqlite3
from datetime import datetime
from typing import Protocol

from jobpilot.models import Job, Profile

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    company      TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    requirements TEXT NOT NULL DEFAULT '[]',
    link         TEXT,
    created_at   TEXT NOT NULL
)
"""

_COLUMNS = (
    "id, source, title, company, description, requirements, link, created_at"
)


class RepositoryError(Exception):
    """Raised when the store cannot complete an operation."""


class JobRepository(Protocol):
    """The persistence port. Adapters must be interchangeable behind it."""

    def add(self, job: Job) -> Job: ...

    def get(self, job_id: str) -> Job | None: ...

    def list_all(self) -> list[Job]: ...


class SqliteJobRepository:
    """A `JobRepository` backed by a single sqlite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def add(self, job: Job) -> Job:
        try:
            self._conn.execute(
                f"INSERT INTO jobs ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.source,
                    job.title,
                    job.company,
                    job.description,
                    json.dumps(job.requirements),
                    job.link,
                    job.created_at.isoformat(),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise RepositoryError(str(exc)) from exc
        return job

    def get(self, job_id: str) -> Job | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def list_all(self) -> list[Job]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM jobs ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
        return [self._row_to_job(row) for row in rows]

    @staticmethod
    def _row_to_job(row: tuple) -> Job:
        return Job(
            id=row[0],
            source=row[1],
            title=row[2],
            company=row[3],
            description=row[4],
            requirements=json.loads(row[5]),
            link=row[6],
            created_at=datetime.fromisoformat(row[7]),
        )


# ---------------------------------------------------------------------------
# M2: single-row profile persistence
# ---------------------------------------------------------------------------

_PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    skills             TEXT NOT NULL DEFAULT '[]',
    seniority          TEXT NOT NULL,
    years_experience   INTEGER,
    salary_expectation TEXT NOT NULL DEFAULT '[]',
    location           TEXT,
    raw_cv             TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
)
"""

_PROFILE_FIELDS = (
    "skills, seniority, years_experience, salary_expectation, "
    "location, raw_cv, created_at, updated_at"
)


class ProfileRepository(Protocol):
    """The single-profile persistence port. Adapters are interchangeable."""

    def get(self) -> Profile | None: ...

    def upsert(self, profile: Profile) -> Profile: ...


class SqliteProfileRepository:
    """A `ProfileRepository` backed by a single sqlite connection.

    The `CHECK (id = 1)` primary key makes "one canonical profile" a storage
    invariant; `upsert` writes that single row with `ON CONFLICT DO UPDATE`, so a
    replace is atomic and full (never a partial merge).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute(_PROFILE_SCHEMA)
        self._conn.commit()

    def get(self) -> Profile | None:
        row = self._conn.execute(
            f"SELECT {_PROFILE_FIELDS} FROM profile WHERE id = 1"
        ).fetchone()
        return self._row_to_profile(row) if row is not None else None

    def upsert(self, profile: Profile) -> Profile:
        location = (
            json.dumps(profile.location.model_dump())
            if profile.location is not None
            else None
        )
        try:
            self._conn.execute(
                f"INSERT INTO profile (id, {_PROFILE_FIELDS}) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "skills=excluded.skills, seniority=excluded.seniority, "
                "years_experience=excluded.years_experience, "
                "salary_expectation=excluded.salary_expectation, "
                "location=excluded.location, raw_cv=excluded.raw_cv, "
                "created_at=excluded.created_at, updated_at=excluded.updated_at",
                (
                    json.dumps(profile.skills),
                    profile.seniority,
                    profile.years_experience,
                    json.dumps([s.model_dump() for s in profile.salary_expectation]),
                    location,
                    profile.raw_cv,
                    profile.created_at.isoformat(),
                    profile.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise RepositoryError(str(exc)) from exc
        return profile

    @staticmethod
    def _row_to_profile(row: tuple) -> Profile:
        return Profile(
            skills=json.loads(row[0]),
            seniority=row[1],
            years_experience=row[2],
            salary_expectation=json.loads(row[3]),
            location=json.loads(row[4]) if row[4] is not None else None,
            raw_cv=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )
