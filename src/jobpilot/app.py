"""JobPilot FastAPI application.

M0: skeleton. Exposes only the health check. The pipeline components
(JobSource, Normalizer, Matcher, Generator, ApplicationQueue) arrive in the
following milestones via SDD.
"""

from fastapi import FastAPI

from jobpilot import __version__


def create_app() -> FastAPI:
    """Create and configure the application instance.

    A factory instead of a global app: makes it easy to test with a clean
    instance per test and to inject dependencies in future milestones.
    """
    app = FastAPI(title="JobPilot", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
