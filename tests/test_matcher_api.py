"""Integration tests for POST /jobs/{job_id}/match (T5).

The router is mounted on a bare app with fakes on app.state, exercised through
TestClient. These pin the advisory contract end to end: a decided result on the
happy path, the 404-vs-cannot_assess asymmetry (unknown job vs absent profile),
fail-closed on matcher error / bad score, a generic 500 on a storage read
failure, request bodies ignored, and the zero-writes invariant
(MATCH-01/05/06/07/08/09/11/12).
"""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobpilot.matching import MatcherError, MatcherLLMOutput
from jobpilot.models import Job, JobCreate, Profile, ProfileCreate
from jobpilot.repository import RepositoryError
from jobpilot.routes.matcher import router

from tests.fakes import FakeMatcher, FakeJobRepository, FakeProfileRepository


def _job() -> Job:
    return Job.new_from(JobCreate(title="QA Engineer", company="Acme"))


def _profile() -> Profile:
    return Profile.new_from(ProfileCreate(skills=["k6"], seniority="pleno"))


def _build_app(*, job=None, profile=None, matcher=None, job_repo=None, profile_repo=None):
    app = FastAPI()
    app.include_router(router)
    app.state.repo = job_repo if job_repo is not None else FakeJobRepository()
    app.state.profile_repo = (
        profile_repo if profile_repo is not None else FakeProfileRepository()
    )
    app.state.matcher = matcher
    if job is not None:
        app.state.repo.add(job)
    if profile is not None:
        app.state.profile_repo.upsert(profile)
    return app


# ---------------------------------------------------------------------------
# happy path (MATCH-01)
# ---------------------------------------------------------------------------


def test_existing_job_and_profile_returns_decided_result():
    job = _job()
    matcher = FakeMatcher(
        MatcherLLMOutput(score=82, rationale="strong overlap", gaps=["AWS"])
    )
    client = TestClient(_build_app(job=job, profile=_profile(), matcher=matcher))

    resp = client.post(f"/jobs/{job.id}/match")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "score": 82,
        "verdict": "strong",
        "gaps": ["AWS"],
        "rationale": "strong overlap",
    }


# ---------------------------------------------------------------------------
# the 404-vs-cannot_assess asymmetry (MATCH-06, MATCH-09)
# ---------------------------------------------------------------------------


def test_unknown_job_returns_404():
    matcher = FakeMatcher(MatcherLLMOutput(score=50, rationale="unused"))
    client = TestClient(_build_app(profile=_profile(), matcher=matcher))

    resp = client.post("/jobs/does-not-exist/match")

    assert resp.status_code == 404


def test_job_present_but_no_profile_returns_cannot_assess():
    job = _job()
    matcher = FakeMatcher(MatcherLLMOutput(score=90, rationale="unused"))
    client = TestClient(_build_app(job=job, matcher=matcher))  # no profile

    resp = client.post(f"/jobs/{job.id}/match")

    assert resp.status_code == 200  # not 404 — the asymmetry
    body = resp.json()
    assert body["verdict"] == "cannot_assess"
    assert body["score"] is None
    assert body["gaps"] == []
    assert matcher.evaluate_called is False


# ---------------------------------------------------------------------------
# fail-closed paths (MATCH-07, MATCH-08)
# ---------------------------------------------------------------------------


def test_matcher_error_returns_cannot_assess_and_logs_cause(caplog):
    job = _job()
    matcher = FakeMatcher(error=MatcherError("provider down"))
    client = TestClient(_build_app(job=job, profile=_profile(), matcher=matcher))

    with caplog.at_level(logging.ERROR, logger="jobpilot"):
        resp = client.post(f"/jobs/{job.id}/match")

    assert resp.status_code == 200
    assert resp.json()["verdict"] == "cannot_assess"
    assert any("provider down" in (r.exc_text or "") for r in caplog.records)


def test_out_of_range_score_returns_cannot_assess():
    job = _job()
    matcher = FakeMatcher(MatcherLLMOutput(score=150, rationale="great"))
    client = TestClient(_build_app(job=job, profile=_profile(), matcher=matcher))

    resp = client.post(f"/jobs/{job.id}/match")

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "cannot_assess"
    assert body["score"] is None  # never clamped


# ---------------------------------------------------------------------------
# storage read failure -> generic 500 (never a verdict)
# ---------------------------------------------------------------------------


class _FailingJobRepo:
    def get(self, job_id):
        raise RepositoryError("db down")

    def add(self, job):  # pragma: no cover - not exercised
        return job

    def list_all(self):  # pragma: no cover - not exercised
        return []


def test_storage_read_failure_returns_generic_500():
    matcher = FakeMatcher(MatcherLLMOutput(score=50, rationale="unused"))
    client = TestClient(
        _build_app(job_repo=_FailingJobRepo(), profile=_profile(), matcher=matcher)
    )

    resp = client.post("/jobs/anything/match")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "internal error"}


# ---------------------------------------------------------------------------
# request body is ignored (MATCH-05)
# ---------------------------------------------------------------------------


def test_request_body_is_ignored():
    job = _job()
    matcher = FakeMatcher(MatcherLLMOutput(score=30, rationale="thin"))
    client = TestClient(_build_app(job=job, profile=_profile(), matcher=matcher))

    resp = client.post(
        f"/jobs/{job.id}/match",
        json={"score": 100, "verdict": "strong", "rationale": "injected"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 30  # server-derived, not the injected 100
    assert body["rationale"] == "thin"


# ---------------------------------------------------------------------------
# zero-writes invariant (MATCH-11, MATCH-12)
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


def test_match_performs_no_writes():
    job = _job()
    job_spy = _SpyJobRepo(job)
    profile_spy = _SpyProfileRepo(_profile())
    matcher = FakeMatcher(MatcherLLMOutput(score=60, rationale="ok"))
    app = FastAPI()
    app.include_router(router)
    app.state.repo = job_spy
    app.state.profile_repo = profile_spy
    app.state.matcher = matcher
    client = TestClient(app)

    resp = client.post(f"/jobs/{job.id}/match")

    assert resp.status_code == 200
    assert job_spy.writes == 0
    assert profile_spy.writes == 0
