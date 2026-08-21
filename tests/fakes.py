"""Test doubles for the repository ports.

`FakeJobRepository` and `FakeProfileRepository` are in-memory stand-ins used by
the route tests. Each is held to the same behavior as its real sqlite adapter by
the parametrized repository contract tests (`test_repository.py` and
`test_profile_repository.py`), so route tests cannot pass against a fiction.
"""

from jobpilot.models import Job, Profile


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


class FakeProfileRepository:
    """In-memory ProfileRepository. Single-row, mirrors the sqlite adapter."""

    def __init__(self) -> None:
        self._profile: Profile | None = None

    def get(self) -> Profile | None:
        return self._profile

    def upsert(self, profile: Profile) -> Profile:
        self._profile = profile
        return profile
