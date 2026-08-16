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

from jobpilot.models import Job

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
