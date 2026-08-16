"""Test doubles for the JobRepository port.

`FakeJobRepository` is an in-memory stand-in used by the route tests. It is held
to the same behavior as the real adapter by the parametrized contract test in
`test_repository.py`, so route tests cannot pass against a fiction.
"""

from jobpilot.models import Job


class FakeJobRepository:
    """In-memory JobRepository. Newest-first mirrors the sqlite adapter."""

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def add(self, job: Job) -> Job:
        self._jobs.append(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return next((job for job in self._jobs if job.id == job_id), None)

    def list_all(self) -> list[Job]:
        return list(reversed(self._jobs))
