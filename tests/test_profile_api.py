"""API tests for the profile router (T4).

The router is mounted on a throwaway app with an injected repository, so these
tests exercise the HTTP contract independently of app wiring (T5). The happy
path uses the contract-tested FakeProfileRepository; the failure path uses a stub
whose upsert raises, to prove the 500 leaks nothing and the prior state stands.
"""

import logging
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobpilot.repository import RepositoryError
from jobpilot.routes.profile import INTERNAL_ERROR_BODY, router
from tests.fakes import FakeProfileRepository


class _FailingRepository(FakeProfileRepository):
    """upsert() blows up with an internal-looking message that must NOT leak.

    get() still returns whatever was stored, so the "prior state unchanged"
    assertion is meaningful.
    """

    def upsert(self, profile):
        raise RepositoryError("near 'SELECT': syntax error; secret table users")


def make_client(repo=None) -> TestClient:
    app = FastAPI()
    app.state.profile_repo = repo if repo is not None else FakeProfileRepository()
    app.include_router(router)
    return TestClient(app)


VALID = {"skills": ["k6"], "seniority": "pleno-senior"}


# ---------------------------------------------------------------------------
# Happy path + create/replace state (BCP-01, BCP-02, BCP-07, BCP-08)
# ---------------------------------------------------------------------------


def test_put_create_returns_201_with_server_timestamps():
    client = make_client()

    resp = client.put("/profile", json=VALID)

    assert resp.status_code == 201
    body = resp.json()
    assert body["skills"] == ["k6"]
    assert body["seniority"] == "pleno-senior"
    assert body["created_at"]
    assert body["updated_at"]


def test_second_put_returns_200_preserving_created_at_and_advancing_updated_at():
    client = make_client()

    # Control the clock so create and replace get distinct timestamps: a real
    # replace must advance updated_at, so we can assert a *strict* increase. With
    # the wall clock the two writes could land in the same microsecond, letting a
    # mutant that freezes updated_at slip through a `>=` assertion.
    t_create = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    t_replace = datetime(2026, 8, 20, 12, 0, 5, tzinfo=UTC)
    with patch("jobpilot.models.datetime") as clock:
        clock.now.side_effect = [t_create, t_replace]
        created = client.put("/profile", json=VALID).json()
        replaced = client.put(
            "/profile", json={"skills": ["cypress"], "seniority": "senior"}
        )

    assert replaced.status_code == 200
    body = replaced.json()
    assert body["skills"] == ["cypress"]
    # created_at is pinned to the first write; updated_at strictly advances.
    assert body["created_at"] == created["created_at"]
    assert datetime.fromisoformat(body["created_at"]) == t_create
    assert datetime.fromisoformat(body["updated_at"]) == t_replace
    assert body["updated_at"] > created["updated_at"]


def test_get_before_any_put_returns_404():
    client = make_client()

    assert client.get("/profile").status_code == 404


def test_get_after_put_returns_200_identical_values():
    client = make_client()

    created = client.put("/profile", json=VALID).json()
    fetched = client.get("/profile")

    assert fetched.status_code == 200
    assert fetched.json() == created


# ---------------------------------------------------------------------------
# 422 rejection matrix (BCP-09..15, BCP-21)
# ---------------------------------------------------------------------------


def test_empty_skills_returns_422_naming_skills():
    client = make_client()

    resp = client.put("/profile", json={"skills": [], "seniority": "pleno"})

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(entry["loc"][-1] == "skills" for entry in detail)


def test_blank_skills_returns_422_naming_skills():
    client = make_client()

    resp = client.put(
        "/profile", json={"skills": ["  ", ""], "seniority": "pleno"}
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(entry["loc"][-1] == "skills" for entry in detail)


def test_bad_seniority_returns_422_naming_seniority():
    client = make_client()

    resp = client.put(
        "/profile", json={"skills": ["k6"], "seniority": "SDET III"}
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(entry["loc"][-1] == "seniority" for entry in detail)


def test_bad_salary_range_returns_422():
    client = make_client()

    resp = client.put(
        "/profile",
        json={
            "skills": ["k6"],
            "seniority": "pleno",
            "salary_expectation": [
                {
                    "currency": "BRL",
                    "contract": "CLT",
                    "floor": 9000,
                    "target": 8000,
                    "ceiling": 7000,
                }
            ],
        },
    )

    assert resp.status_code == 422


def test_duplicate_currency_contract_returns_422():
    client = make_client()
    entry = {
        "currency": "BRL",
        "contract": "CLT",
        "floor": 6000,
        "target": 8000,
        "ceiling": 10000,
    }

    resp = client.put(
        "/profile",
        json={
            "skills": ["k6"],
            "seniority": "pleno",
            "salary_expectation": [entry, entry],
        },
    )

    assert resp.status_code == 422


def test_years_experience_out_of_range_returns_422():
    client = make_client()

    resp = client.put(
        "/profile",
        json={"skills": ["k6"], "seniority": "pleno", "years_experience": 61},
    )

    assert resp.status_code == 422


def test_empty_object_body_returns_422():
    client = make_client()

    assert client.put("/profile", json={}).status_code == 422


def test_non_json_content_type_returns_422():
    client = make_client()

    resp = client.put(
        "/profile",
        content="not json at all",
        headers={"Content-Type": "text/plain"},
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rejected replace keeps prior profile (BCP-16)
# ---------------------------------------------------------------------------


def test_rejected_replace_leaves_prior_profile_unchanged():
    client = make_client()
    created = client.put("/profile", json=VALID).json()

    bad = client.put("/profile", json={"skills": [], "seniority": "pleno"})
    assert bad.status_code == 422

    assert client.get("/profile").json() == created


# ---------------------------------------------------------------------------
# Repository failure → 500, no leak, logged server-side (BCP-17, BCP-22)
# ---------------------------------------------------------------------------


def test_repo_failure_returns_500_with_generic_body_and_no_leak():
    client = make_client(repo=_FailingRepository())

    resp = client.put("/profile", json=VALID)

    assert resp.status_code == 500
    assert resp.json() == INTERNAL_ERROR_BODY
    leaked = resp.text
    for secret in ("SELECT", "secret", "syntax error", "Traceback", "users"):
        assert secret not in leaked
    # nothing persisted: empty state still fails closed
    assert client.get("/profile").status_code == 404


def test_repo_failure_logs_internal_cause_server_side(caplog):
    client = make_client(repo=_FailingRepository())

    with caplog.at_level(logging.ERROR, logger="jobpilot"):
        resp = client.put("/profile", json=VALID)

    assert resp.status_code == 500
    assert "failed to persist profile" in caplog.text
    assert "SELECT" in caplog.text
    assert "SELECT" not in resp.text
