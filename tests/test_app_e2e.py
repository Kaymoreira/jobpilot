"""End-to-end tests over the fully wired app (T5).

These drive `create_app(db_path=":memory:")`, so the paste travels through the
real sqlite adapter. A matching GET proves the job was persisted, not merely
echoed back from the POST response.
"""

from fastapi.testclient import TestClient

from jobpilot.app import create_app
from jobpilot.routes.jobs import INTERNAL_ERROR_BODY, get_repository
from tests.fakes import FakeJobRepository


class _FailingRepository(FakeJobRepository):
    def add(self, job):
        from jobpilot.repository import RepositoryError

        raise RepositoryError("boom")


def make_client() -> TestClient:
    return TestClient(create_app(db_path=":memory:"))


def test_paste_is_persisted_and_read_back_from_the_store():
    client = make_client()

    created = client.post(
        "/jobs", json={"title": "Senior QE", "company": "Acme"}
    ).json()

    # GET reads from sqlite, so a match proves persistence, not echo.
    fetched = client.get(f"/jobs/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created
    assert created["source"] == "pasted"


def test_duplicate_paste_creates_two_distinct_rows():
    client = make_client()
    payload = {"title": "Senior QE", "company": "Acme"}

    first = client.post("/jobs", json=payload).json()
    second = client.post("/jobs", json=payload).json()

    listed = client.get("/jobs").json()
    assert len(listed) == 2
    assert first["id"] != second["id"]


def test_list_is_newest_first_e2e():
    client = make_client()

    a = client.post("/jobs", json={"title": "A", "company": "X"}).json()
    b = client.post("/jobs", json={"title": "B", "company": "Y"}).json()

    assert [j["id"] for j in client.get("/jobs").json()] == [b["id"], a["id"]]


def test_list_empty_e2e():
    client = make_client()

    assert client.get("/jobs").json() == []


def test_unicode_survives_storage_roundtrip():
    client = make_client()

    created = client.post(
        "/jobs", json={"title": "Señor QE 🚀", "company": "Açme ✨"}
    ).json()

    fetched = client.get(f"/jobs/{created['id']}").json()
    assert fetched["title"] == "Señor QE 🚀"
    assert fetched["company"] == "Açme ✨"


def test_health_still_ok():
    client = make_client()

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_repo_failure_returns_500_and_persists_nothing_e2e():
    app = create_app(db_path=":memory:")
    app.dependency_overrides[get_repository] = lambda: _FailingRepository()
    client = TestClient(app)

    resp = client.post("/jobs", json={"title": "A", "company": "B"})

    assert resp.status_code == 500
    assert resp.json() == INTERNAL_ERROR_BODY
    assert client.get("/jobs").json() == []
