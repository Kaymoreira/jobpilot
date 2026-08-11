"""JobPilot FastAPI application.

M1: wires the PastedJobSource. The factory opens a SQLite connection, builds a
`SqliteJobRepository`, and exposes it on `app.state.repo` for the jobs router to
resolve. Later pipeline components (Matcher, Generator, ApplicationQueue) arrive
in the following milestones via SDD.
"""

import os
import sqlite3

from fastapi import FastAPI

from jobpilot import __version__
from jobpilot.repository import SqliteJobRepository
from jobpilot.routes.jobs import router as jobs_router

DEFAULT_DB_PATH = "jobpilot.db"


def create_app(db_path: str | None = None) -> FastAPI:
    """Create and configure the application instance.

    A factory instead of a global app: makes it easy to test with a clean
    instance per test. ``db_path`` defaults to the ``JOBPILOT_DB`` env var, then
    to ``jobpilot.db``; tests pass ``":memory:"`` for an isolated store.
    """
    app = FastAPI(title="JobPilot", version=__version__)

    path = db_path or os.environ.get("JOBPILOT_DB", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path, check_same_thread=False)
    app.state.repo = SqliteJobRepository(conn)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(jobs_router)

    return app


app = create_app()
