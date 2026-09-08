"""Unit tests for the Generator domain contract (T1).

Covers GEN-03 (GenerateResult contract; draft non-null iff generated), GEN-05
(draft bounded <= DRAFT_MAX in the validator), and GEN-15 (never a non-null draft
under failure) at the model layer.

The self-validating ``GenerateResult`` is the structural anti-fail-open guard: a
failed run can never be constructed as a ``generated`` result carrying a letter,
and a ``generated`` result can never carry a null or empty draft. Every shape is
built with explicit field values (Lesson L-001): Pydantic v2 skips validators on
defaulted fields, so we never rely on omission.
"""

import pytest
from pydantic import ValidationError

from jobpilot.models import (
    DRAFT_MAX,
    GENERATED_REASON,
    GenerateResult,
)

# ---------------------------------------------------------------------------
# cannot_generate constructor (GEN-03/15)
# ---------------------------------------------------------------------------


def test_cannot_generate_is_null_draft():
    result = GenerateResult.cannot_generate("profile absent")
    assert result.status == "cannot_generate"
    assert result.draft is None
    assert result.reason == "profile absent"


# ---------------------------------------------------------------------------
# a generated result carries a real draft (GEN-03)
# ---------------------------------------------------------------------------


def test_generated_accepts_a_real_draft():
    result = GenerateResult(
        status="generated", draft="Dear hiring team, ...", reason=GENERATED_REASON
    )
    assert result.status == "generated"
    assert result.draft == "Dear hiring team, ..."
    assert result.reason == "ok"


# ---------------------------------------------------------------------------
# fail-open construction is impossible (GEN-15)
# ---------------------------------------------------------------------------


def test_generated_with_null_draft_raises():
    with pytest.raises(ValidationError):
        GenerateResult(status="generated", draft=None, reason=GENERATED_REASON)


def test_generated_with_empty_draft_raises():
    with pytest.raises(ValidationError):
        GenerateResult(status="generated", draft="", reason=GENERATED_REASON)


def test_generated_with_whitespace_draft_raises():
    with pytest.raises(ValidationError):
        GenerateResult(status="generated", draft="   \n\t ", reason=GENERATED_REASON)


def test_generated_over_draft_max_raises():
    with pytest.raises(ValidationError):
        GenerateResult(
            status="generated", draft="x" * (DRAFT_MAX + 1), reason=GENERATED_REASON
        )


def test_cannot_generate_with_non_null_draft_raises():
    with pytest.raises(ValidationError):
        GenerateResult(
            status="cannot_generate", draft="a leaked letter", reason="match failed"
        )


def test_generated_at_exactly_draft_max_is_accepted():
    result = GenerateResult(
        status="generated", draft="x" * DRAFT_MAX, reason=GENERATED_REASON
    )
    assert result.draft is not None
    assert len(result.draft) == DRAFT_MAX
