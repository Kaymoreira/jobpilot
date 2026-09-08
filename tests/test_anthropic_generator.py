"""Unit tests for the AnthropicGenerator adapter (T4).

All offline: the anthropic client is faked (injected) or the constructor is
monkeypatched, so no network call and no API key is needed. These tests pin the
single-attempt, fail-closed contract (GEN-12/13/18/19/27): the text block is
returned on a clean completion, and every provider failure (timeout, API error,
refusal, max_tokens truncation, missing/empty text, unexpected fault) becomes a
GeneratorError. The real client is built with max_retries=0 + the timeout.
"""

import anthropic
import httpx2
import pytest

from jobpilot.generation import (
    SYSTEM_PROMPT,
    AnthropicGenerator,
    GeneratorError,
)
from jobpilot.models import Job, JobCreate, MatchResult, Profile, ProfileCreate

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _job() -> Job:
    return Job.new_from(JobCreate(title="QA Engineer", company="Acme"))


def _profile() -> Profile:
    return Profile.new_from(ProfileCreate(skills=["k6"], seniority="pleno"))


def _match() -> MatchResult:
    return MatchResult(score=60, verdict="possible", gaps=["AWS"], rationale="ok")


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _ThinkingBlock:
    def __init__(self):
        self.type = "thinking"
        self.thinking = ""


class _FakeResponse:
    def __init__(self, content, *, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, *, response=None, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, *, response=None, error=None):
        self.messages = _FakeMessages(response=response, error=error)


# ---------------------------------------------------------------------------
# create success -> the text block (GEN-18/19)
# ---------------------------------------------------------------------------


def test_create_success_returns_the_text_block():
    response = _FakeResponse([_ThinkingBlock(), _TextBlock("Dear team, ...")])
    gen = AnthropicGenerator(client=_FakeClient(response=response))

    draft = gen.generate(_job(), _profile(), _match())

    assert draft == "Dear team, ..."


def test_generate_passes_prompt_and_config_to_create():
    response = _FakeResponse([_TextBlock("letter")])
    client = _FakeClient(response=response)
    gen = AnthropicGenerator(client=client, effort="medium", max_tokens=2048)

    gen.generate(_job(), _profile(), _match())

    (call,) = client.messages.calls
    assert call["model"] == "claude-opus-4-8"
    assert call["system"] == SYSTEM_PROMPT
    assert call["max_tokens"] == 2048
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "medium"}
    assert call["messages"][0]["role"] == "user"
    assert "QA Engineer" in call["messages"][0]["content"]


# ---------------------------------------------------------------------------
# every provider failure -> GeneratorError (GEN-12/13/27)
# ---------------------------------------------------------------------------


def test_api_timeout_becomes_generator_error():
    client = _FakeClient(error=anthropic.APITimeoutError(request=_REQUEST))
    gen = AnthropicGenerator(client=client)
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


def test_api_error_becomes_generator_error():
    client = _FakeClient(
        error=anthropic.APIError("upstream boom", request=_REQUEST, body=None)
    )
    gen = AnthropicGenerator(client=client)
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


def test_refusal_stop_reason_becomes_generator_error():
    response = _FakeResponse([_TextBlock("I can't help")], stop_reason="refusal")
    gen = AnthropicGenerator(client=_FakeClient(response=response))
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


def test_max_tokens_truncation_becomes_generator_error():
    response = _FakeResponse([_TextBlock("Dear team, I am ")], stop_reason="max_tokens")
    gen = AnthropicGenerator(client=_FakeClient(response=response))
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


def test_empty_text_block_becomes_generator_error():
    response = _FakeResponse([_TextBlock("   \n ")], stop_reason="end_turn")
    gen = AnthropicGenerator(client=_FakeClient(response=response))
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


def test_no_text_block_becomes_generator_error():
    # thinking only, no text block -> fail closed, never a hollow draft.
    response = _FakeResponse([_ThinkingBlock()], stop_reason="end_turn")
    gen = AnthropicGenerator(client=_FakeClient(response=response))
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


def test_unexpected_non_sdk_exception_becomes_generator_error():
    client = _FakeClient(error=RuntimeError("unexpected boom"))
    gen = AnthropicGenerator(client=client)
    with pytest.raises(GeneratorError):
        gen.generate(_job(), _profile(), _match())


# ---------------------------------------------------------------------------
# lazy real client is built single-attempt + bounded (GEN-12)
# ---------------------------------------------------------------------------


def test_lazy_client_built_with_no_retries_and_timeout(monkeypatch):
    recorded = {}
    response = _FakeResponse([_TextBlock("thin letter")])

    def fake_ctor(**kwargs):
        recorded.update(kwargs)
        return _FakeClient(response=response)

    monkeypatch.setattr(anthropic, "Anthropic", fake_ctor)
    gen = AnthropicGenerator(timeout=42.0)  # no injected client

    draft = gen.generate(_job(), _profile(), _match())

    assert draft == "thin letter"
    assert recorded["max_retries"] == 0
    assert recorded["timeout"] == 42.0
