"""Aplicacao FastAPI do JobPilot.

M0: esqueleto. Expoe apenas o health check. Os componentes do pipeline
(JobSource, Normalizer, Matcher, Generator, ApplicationQueue) entram nos
milestones seguintes via SDD.
"""

from fastapi import FastAPI

from jobpilot import __version__


def create_app() -> FastAPI:
    """Cria e configura a instancia da aplicacao.

    Factory em vez de app global: facilita testar com uma instancia limpa
    por teste e injetar dependencias nos milestones futuros.
    """
    app = FastAPI(title="JobPilot", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
