"""Body-size guard tests (T6, PJS-10).

The guard counts actual streamed bytes and never reads Content-Length. Without
it a 60 KB description would be accepted (only title/company are length-capped),
so these tests discriminate the guard's presence.
"""

import asyncio

from fastapi.testclient import TestClient

from jobpilot.app import BodySizeLimitMiddleware, create_app


def make_client() -> TestClient:
    return TestClient(create_app(db_path=":memory:"))


def _oversized_json() -> bytes:
    # ~60 KB, well over the 50 KB limit; description is not length-capped.
    return b'{"title":"A","company":"B","description":"' + b"x" * 60000 + b'"}'


def _assert_too_large(payload: dict) -> None:
    # detail must be a non-empty list matching the Pydantic 422 shape, not a
    # bare string; the offending entry names the body and the too_large type.
    detail = payload["detail"]
    assert isinstance(detail, list) and detail
    entry = detail[0]
    assert entry["type"] == "too_large"
    assert entry["loc"] == ["body"]
    assert entry["msg"] == "request body too large"


def test_oversized_body_is_rejected_422():
    client = make_client()

    resp = client.post(
        "/jobs",
        content=_oversized_json(),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 422
    # Assert the guard rejected it, not a downstream validation/parse error,
    # and that detail is a non-empty list like every other 422 (spec PJS-10).
    _assert_too_large(resp.json())


def test_oversized_body_with_lying_small_content_length_is_still_rejected():
    client = make_client()

    resp = client.post(
        "/jobs",
        content=_oversized_json(),
        headers={"Content-Type": "application/json", "Content-Length": "12"},
    )

    # The guard counts real bytes, so a small Content-Length does not slip it.
    assert resp.status_code == 422
    _assert_too_large(resp.json())


def test_oversized_body_streamed_in_chunks_is_rejected():
    client = make_client()

    def chunks():
        yield b'{"title":"A","company":"B","description":"'
        for _ in range(60):
            yield b"x" * 1000
        yield b'"}'

    # No Content-Length (chunked); the guard must sum bytes across chunks.
    resp = client.post(
        "/jobs", content=chunks(), headers={"Content-Type": "application/json"}
    )

    assert resp.status_code == 422
    _assert_too_large(resp.json())


def test_normal_paste_still_accepted():
    client = make_client()

    resp = client.post("/jobs", json={"title": "Senior QE", "company": "Acme"})

    assert resp.status_code == 201


def test_guard_sums_bytes_across_chunks_at_asgi_level():
    # Drive the middleware directly: httpx coalesces bodies into one chunk, so
    # this is the only way to exercise cross-chunk accumulation. Three 60-byte
    # chunks (180) exceed a 100-byte limit only if the guard sums them.
    sent: list[dict] = []

    async def downstream(scope, receive, send):  # pragma: no cover - not reached
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = [
        {"type": "http.request", "body": b"x" * 60, "more_body": True},
        {"type": "http.request", "body": b"x" * 60, "more_body": True},
        {"type": "http.request", "body": b"x" * 60, "more_body": False},
    ]
    stream = iter(messages)

    async def receive():
        return next(stream)

    async def send(message):
        sent.append(message)

    guard = BodySizeLimitMiddleware(downstream, max_bytes=100)
    asyncio.run(guard({"type": "http"}, receive, send))

    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 422


def test_oversized_rejection_persists_nothing():
    client = make_client()

    client.post(
        "/jobs",
        content=_oversized_json(),
        headers={"Content-Type": "application/json"},
    )

    assert client.get("/jobs").json() == []
