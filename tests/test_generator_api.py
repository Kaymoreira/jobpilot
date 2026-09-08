"""Integration tests for POST /jobs/{job_id}/generate (T5).

The router is mounted on a bare app with fakes on app.state, exercised through
TestClient. These pin the advisory contract end to end: a generated draft on the
happy path, the 404-vs-cannot_generate asymmetry (unknown job vs absent
profile), fail-closed on a cannot_assess match or a generation error, a generic
500 on a storage read failure, request bodies ignored, and the zero-writes
invariant (GEN-01/06/10/11/14/16/17/21).
"""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobpilot.generation import GeneratorError
from jobpilot.matching import MatcherError, MatcherLLMOutput
from jobpilot.models import Job, JobCreate, Profile, ProfileCreate
from jobpilot.repository import RepositoryError
from jobpilot.routes.generator import router

from tests.fakes import (
    FakeGenerator,
    FakeJobRepository,
    FakeMatcher,
    FakeProfileRepository,
)


def _job() -> Job:
    return Job.new_from(JobCreate(title="QA Engineer", company="Acme"))


def _profile() -> Profile:
    return Profile.new_from(ProfileCreate(skills=["k6"], seniority="pleno"))


def _ok_matcher() -> FakeMatcher:
    return FakeMatcher(MatcherLLMOutput(score=60, rationale="core fit", gaps=["AWS"]))


def _build_app(
    *, job=None, profile=None, matcher=None, generator=None, job_repo=None, profile_repo=None
):
    app = FastAPI()
    app.include_router(router)
    app.state.repo = job_repo if job_repo is not None else FakeJobRepository()
    app.state.profile_repo = (
        profile_repo if profile_repo is not None else FakeProfileRepository()
    )
    app.state.matcher = matcher
    app.state.generator = generator
    if job is not None:
        app.state.repo.add(job)
    if profile is not None:
        app.state.profile_repo.upsert(profile)
    return app


# ---------------------------------------------------------------------------
# happy path (GEN-01)
# ---------------------------------------------------------------------------


def test_existing_job_and_profile_returns_generated_draft():
    job = _job()
    app = _build_app(
        job=job,
        profile=_profile(),
        matcher=_ok_matcher(),
        generator=FakeGenerator("Dear team, I'd love to help."),
    )
    client = TestClient(app)

    resp = client.post(f"/jobs/{job.id}/generate")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "status": "generated",
        "draft": "Dear team, I'd love to help.",
        "reason": "ok",
    }


# ---------------------------------------------------------------------------
# the 404-vs-cannot_generate asymmetry (GEN-10, GEN-14)
# ---------------------------------------------------------------------------


def test_unknown_job_returns_404():
    app = _build_app(
        profile=_profile(), matcher=_ok_matcher(), generator=FakeGenerator("x")
    )
    client = TestClient(app)

    resp = client.post("/jobs/does-not-exist/generate")

    assert resp.status_code == 404


def test_job_present_but_no_profile_returns_cannot_generate():
    job = _job()
    matcher = _ok_matcher()
    generator = FakeGenerator("unused")
    app = _build_app(job=job, matcher=matcher, generator=generator)  # no profile
    client = TestClient(app)

    resp = client.post(f"/jobs/{job.id}/generate")

    assert resp.status_code == 200  # not 404 — the asymmetry
    body = resp.json()
    assert body["status"] == "cannot_generate"
    assert body["draft"] is None
    assert body["reason"] == "profile absent"
    assert matcher.evaluate_called is False
    assert generator.generate_called is False


# ---------------------------------------------------------------------------
# fail-closed paths (GEN-11, GEN-12)
# ---------------------------------------------------------------------------


def test_match_cannot_assess_returns_cannot_generate_no_generation():
    job = _job()
    matcher = FakeMatcher(error=MatcherError("provider down"))
    generator = FakeGenerator("unused")
    app = _build_app(job=job, profile=_profile(), matcher=matcher, generator=generator)
    client = TestClient(app)

    resp = client.post(f"/jobs/{job.id}/generate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cannot_generate"
    assert body["reason"] == "match failed"
    assert generator.generate_called is False


def test_generation_error_returns_cannot_generate_and_logs_cause(caplog):
    job = _job()
    generator = FakeGenerator(error=GeneratorError("model exploded"))
    app = _build_app(
        job=job, profile=_profile(), matcher=_ok_matcher(), generator=generator
    )
    client = TestClient(app)

    with caplog.at_level(logging.ERROR, logger="jobpilot"):
        resp = client.post(f"/jobs/{job.id}/generate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cannot_generate"
    assert body["draft"] is None
    assert body["reason"] == "generation failed"
    assert any("generation failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# storage read failure -> generic 500 (GEN-21)
# ---------------------------------------------------------------------------


class _FailingJobRepo:
    def get(self, job_id):
        raise RepositoryError("db down")

    def add(self, job):  # pragma: no cover - not exercised
        return job

    def list_all(self):  # pragma: no cover - not exercised
        return []


def test_storage_read_failure_returns_generic_500():
    app = _build_app(
        job_repo=_FailingJobRepo(),
        profile=_profile(),
        matcher=_ok_matcher(),
        generator=FakeGenerator("x"),
    )
    client = TestClient(app)

    resp = client.post("/jobs/anything/generate")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "internal error"}


# ---------------------------------------------------------------------------
# request body is ignored (GEN-06)
# ---------------------------------------------------------------------------


def test_request_body_is_ignored():
    job = _job()
    app = _build_app(
        job=job,
        profile=_profile(),
        matcher=_ok_matcher(),
        generator=FakeGenerator("server letter"),
    )
    client = TestClient(app)

    resp = client.post(
        f"/jobs/{job.id}/generate",
        json={"status": "generated", "draft": "injected letter", "reason": "x"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] == "server letter"  # server-derived, not the injected one


# ---------------------------------------------------------------------------
# zero-writes invariant (GEN-16, GEN-17)
# ---------------------------------------------------------------------------


class _SpyJobRepo:
    def __init__(self, job):
        self._job = job
        self.writes = 0

    def get(self, job_id):
        return self._job if self._job.id == job_id else None

    def add(self, job):  # pragma: no cover - asserting it is never called
        self.writes += 1
        return job

    def list_all(self):  # pragma: no cover - not exercised
        return [self._job]


class _SpyProfileRepo:
    def __init__(self, profile):
        self._profile = profile
        self.writes = 0

    def get(self):
        return self._profile

    def upsert(self, profile):  # pragma: no cover - asserting it is never called
        self.writes += 1
        return profile


def test_generate_performs_no_writes():
    job = _job()
    job_spy = _SpyJobRepo(job)
    profile_spy = _SpyProfileRepo(_profile())
    app = FastAPI()
    app.include_router(router)
    app.state.repo = job_spy
    app.state.profile_repo = profile_spy
    app.state.matcher = _ok_matcher()
    app.state.generator = FakeGenerator("a letter")
    client = TestClient(app)

    resp = client.post(f"/jobs/{job.id}/generate")

    assert resp.status_code == 200
    assert job_spy.writes == 0
    assert profile_spy.writes == 0
