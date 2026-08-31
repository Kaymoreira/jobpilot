"""Test doubles for the repository ports.

`FakeJobRepository` and `FakeProfileRepository` are in-memory stand-ins used by
the route tests. Each is held to the same behavior as its real sqlite adapter by
the parametrized repository contract tests (`test_repository.py` and
`test_profile_repository.py`), so route tests cannot pass against a fiction.
"""

from jobpilot.matching import MatcherLLMOutput
from jobpilot.models import Job, Profile


class FakeMatcher:
    """In-memory Matcher. Constructed with a canned ``MatcherLLMOutput`` to
    return, or an exception to raise. Records whether ``evaluate`` was called so
    the profile-absent short-circuit (no LLM call) can be asserted."""

    def __init__(
        self,
        output: MatcherLLMOutput | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._output = output
        self._error = error
        self.evaluate_called = False

    def evaluate(self, job: Job, profile: Profile) -> MatcherLLMOutput:
        self.evaluate_called = True
        if self._error is not None:
            raise self._error
        assert self._output is not None, "FakeMatcher needs an output or an error"
        return self._output


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
