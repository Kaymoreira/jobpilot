"""API tests for the jobs router (T4).

The router is mounted on a throwaway app with an injected repository, so these
tests exercise the HTTP contract independently of app wiring (T5). The happy
path uses the contract-tested FakeJobRepository; the failure path uses a stub
that raises to prove the 500 leaks nothing.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobpilot.repository import RepositoryError
from jobpilot.routes.jobs import INTERNAL_ERROR_BODY, router
from tests.fakes import FakeJobRepository


class _FailingRepository(FakeJobRepository):
    """add() blows up with an internal-looking message that must NOT leak."""

    def add(self, job):
        raise RepositoryError("near 'SELECT': syntax error; secret table users")


def make_client(repo=None) -> TestClient:
    app = FastAPI()
    app.state.repo = repo if repo is not None else FakeJobRepository()
    app.include_router(router)
    return TestClient(app)


VALID = {"title": "Senior QE", "company": "Acme", "description": "Test everything"}


def test_post_valid_returns_201_and_canonical_job():
    client = make_client()

    resp = client.post("/jobs", json=VALID)

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    assert body["source"] == "pasted"
    assert body["title"] == "Senior QE"
    assert body["company"] == "Acme"
    assert body["description"] == "Test everything"
    assert body["created_at"]


def test_post_then_get_by_id_reads_back_identical():
    client = make_client()

    created = client.post("/jobs", json=VALID).json()
    fetched = client.get(f"/jobs/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json() == created


def test_missing_title_returns_422_naming_the_field():
    client = make_client()

    resp = client.post("/jobs", json={"company": "Acme"})

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(
        entry["loc"][-1] == "title" and entry["type"] == "missing"
        for entry in detail
    )


def test_blank_title_returns_422_value_error():
    client = make_client()

    resp = client.post("/jobs", json={"title": "   ", "company": "Acme"})

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(entry["loc"][-1] == "title" for entry in detail)


def test_empty_object_body_returns_422():
    client = make_client()

    resp = client.post("/jobs", json={})

    assert resp.status_code == 422


def test_non_json_body_returns_422():
    client = make_client()

    resp = client.post(
        "/jobs", content="not json at all", headers={"Content-Type": "text/plain"}
    )

    assert resp.status_code == 422


def test_malformed_link_returns_201_with_null_link():
    client = make_client()

    resp = client.post(
        "/jobs", json={"title": "A", "company": "B", "link": "not a url"}
    )

    assert resp.status_code == 201
    assert resp.json()["link"] is None


def test_title_over_512_returns_422():
    client = make_client()

    resp = client.post("/jobs", json={"title": "x" * 513, "company": "Acme"})

    assert resp.status_code == 422


def test_caller_supplied_id_and_source_are_ignored():
    client = make_client()

    resp = client.post(
        "/jobs",
        json={"title": "A", "company": "B", "id": "attacker", "source": "scraped"},
    )

    body = resp.json()
    assert resp.status_code == 201
    assert body["id"] != "attacker"
    assert body["source"] == "pasted"


def test_get_unknown_id_returns_404():
    client = make_client()

    assert client.get("/jobs/nope").status_code == 404


def test_list_returns_newest_first():
    client = make_client()

    first = client.post("/jobs", json={"title": "First", "company": "A"}).json()
    second = client.post("/jobs", json={"title": "Second", "company": "B"}).json()

    listed = client.get("/jobs").json()

    assert [j["id"] for j in listed] == [second["id"], first["id"]]


def test_list_empty_returns_empty_list():
    client = make_client()

    resp = client.get("/jobs")

    assert resp.status_code == 200
    assert resp.json() == []


def test_repo_failure_returns_500_with_generic_body_and_no_leak():
    client = make_client(repo=_FailingRepository())

    resp = client.post("/jobs", json=VALID)

    assert resp.status_code == 500
    assert resp.json() == INTERNAL_ERROR_BODY
    leaked = resp.text
    for secret in ("SELECT", "secret", "syntax error", "Traceback", "users"):
        assert secret not in leaked
    # nothing persisted
    assert client.get("/jobs").json() == []
