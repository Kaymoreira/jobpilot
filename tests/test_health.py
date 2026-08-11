"""M0 skeleton tests: prove the app boots and the health check responds."""

from fastapi.testclient import TestClient

from jobpilot import __version__
from jobpilot.app import create_app


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_app_exposes_title_and_version():
    app = create_app()

    assert app.title == "JobPilot"
    assert app.version == __version__
