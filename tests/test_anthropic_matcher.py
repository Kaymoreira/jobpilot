"""Unit tests for the AnthropicMatcher adapter (T4).

All offline: the anthropic client is faked (injected) or the constructor is
monkeypatched, so no network call and no API key is needed. These tests pin the
single-attempt, fail-closed contract (MATCH-07/08/13/14): every provider failure
(timeout, API error, refusal, truncation, unparseable output) becomes a
MatcherError, and the real client is built with max_retries=0 + the timeout.
"""

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from jobpilot.matching import (
    SYSTEM_PROMPT,
    AnthropicMatcher,
    MatcherError,
    MatcherLLMOutput,
)
from jobpilot.models import Job, JobCreate, Profile, ProfileCreate

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _job() -> Job:
    return Job.new_from(JobCreate(title="QA Engineer", company="Acme"))


def _profile() -> Profile:
    return Profile.new_from(ProfileCreate(skills=["k6"], seniority="pleno"))


def _validation_error() -> ValidationError:
    try:
        MatcherLLMOutput.model_validate({"rationale": "missing score"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


class _FakeResponse:
    def __init__(self, parsed_output, *, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, *, response=None, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, *, response=None, error=None):
        self.messages = _FakeMessages(response=response, error=error)


# ---------------------------------------------------------------------------
# parse success (MATCH-13/14)
# ---------------------------------------------------------------------------


def test_parse_success_returns_the_llm_output():
    output = MatcherLLMOutput(score=82, rationale="strong fit", gaps=["AWS"])
    client = _FakeClient(response=_FakeResponse(output))
    matcher = AnthropicMatcher(client=client)

    result = matcher.evaluate(_job(), _profile())

    assert result is output


def test_evaluate_passes_prompt_and_config_to_parse():
    output = MatcherLLMOutput(score=50, rationale="ok")
    client = _FakeClient(response=_FakeResponse(output))
    matcher = AnthropicMatcher(client=client, effort="medium")

    matcher.evaluate(_job(), _profile())

    (call,) = client.messages.calls
    assert call["model"] == "claude-opus-4-8"
    assert call["system"] == SYSTEM_PROMPT
    assert call["output_format"] is MatcherLLMOutput
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "medium"}
    assert call["messages"][0]["role"] == "user"
    assert "QA Engineer" in call["messages"][0]["content"]


# ---------------------------------------------------------------------------
# every provider failure -> MatcherError (MATCH-07/08)
# ---------------------------------------------------------------------------


def test_api_timeout_becomes_matcher_error():
    client = _FakeClient(error=anthropic.APITimeoutError(request=_REQUEST))
    matcher = AnthropicMatcher(client=client)

    with pytest.raises(MatcherError):
        matcher.evaluate(_job(), _profile())


def test_api_error_becomes_matcher_error():
    client = _FakeClient(
        error=anthropic.APIError("upstream boom", request=_REQUEST, body=None)
    )
    matcher = AnthropicMatcher(client=client)

    with pytest.raises(MatcherError):
        matcher.evaluate(_job(), _profile())


def test_unparseable_output_becomes_matcher_error():
    client = _FakeClient(error=_validation_error())
    matcher = AnthropicMatcher(client=client)

    with pytest.raises(MatcherError):
        matcher.evaluate(_job(), _profile())


def test_refusal_stop_reason_becomes_matcher_error():
    output = MatcherLLMOutput(score=90, rationale="ignored")
    client = _FakeClient(response=_FakeResponse(output, stop_reason="refusal"))
    matcher = AnthropicMatcher(client=client)

    with pytest.raises(MatcherError):
        matcher.evaluate(_job(), _profile())


def test_truncated_output_becomes_matcher_error():
    output = MatcherLLMOutput(score=90, rationale="ignored")
    client = _FakeClient(response=_FakeResponse(output, stop_reason="max_tokens"))
    matcher = AnthropicMatcher(client=client)

    with pytest.raises(MatcherError):
        matcher.evaluate(_job(), _profile())


def test_missing_parsed_output_becomes_matcher_error():
    # end_turn but no parsed payload — fail closed, never return None.
    client = _FakeClient(response=_FakeResponse(None, stop_reason="end_turn"))
    matcher = AnthropicMatcher(client=client)

    with pytest.raises(MatcherError):
        matcher.evaluate(_job(), _profile())


# ---------------------------------------------------------------------------
# lazy real client is built single-attempt + bounded (MATCH-07)
# ---------------------------------------------------------------------------


def test_lazy_client_built_with_no_retries_and_timeout(monkeypatch):
    recorded = {}
    output = MatcherLLMOutput(score=10, rationale="thin")

    def fake_ctor(**kwargs):
        recorded.update(kwargs)
        return _FakeClient(response=_FakeResponse(output))

    monkeypatch.setattr(anthropic, "Anthropic", fake_ctor)
    matcher = AnthropicMatcher(timeout=42.0)  # no injected client

    result = matcher.evaluate(_job(), _profile())

    assert result is output
    assert recorded["max_retries"] == 0
    assert recorded["timeout"] == 42.0
