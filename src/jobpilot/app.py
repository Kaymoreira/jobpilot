"""JobPilot FastAPI application.

M1: wires the PastedJobSource. The factory opens a SQLite connection, builds a
`SqliteJobRepository`, and exposes it on `app.state.repo` for the jobs router to
resolve. Later pipeline components (Matcher, Generator, ApplicationQueue) arrive
in the following milestones via SDD.
"""

import os
import sqlite3

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from jobpilot import __version__
from jobpilot.repository import SqliteJobRepository
from jobpilot.routes.jobs import router as jobs_router

DEFAULT_DB_PATH = "jobpilot.db"
MAX_BODY_BYTES = 50 * 1024


class BodySizeLimitMiddleware:
    """Reject request bodies over a byte limit before they are parsed.

    Counts the actual bytes streamed in the ASGI ``http.request`` messages; it
    never reads the ``Content-Length`` header, which a client can lie about or
    omit. Bodies within the limit are buffered and replayed downstream. Because
    an oversized body short-circuits, at most ``max_bytes`` (plus one chunk) is
    ever held in memory.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                buffered.append(message)
                break
            total += len(message.get("body", b""))
            buffered.append(message)
            if total > self.max_bytes:
                response = JSONResponse(
                    status_code=422,
                    content={"detail": "request body too large"},
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay, send)


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

    app.add_middleware(BodySizeLimitMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(jobs_router)

    return app


app = create_app()
