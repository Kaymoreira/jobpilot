"""Testes do esqueleto M0: prova que a app sobe e o health responde."""

from fastapi.testclient import TestClient

from jobpilot import __version__
from jobpilot.app import create_app


def test_health_retorna_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_app_expoe_titulo_e_versao():
    app = create_app()

    assert app.title == "JobPilot"
    assert app.version == __version__
