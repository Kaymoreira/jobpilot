"""Domain models for JobPilot.

`JobCreate` is the validated paste input; `Job` (added in T2) is the canonical
stored/response shape. Validation lives here so an invalid paste fails
explicitly instead of producing a half-filled Job.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("jobpilot")

MAX_FIELD_LEN = 512
MAX_SKILL_LEN = 128
MAX_RAW_CV_LEN = 50 * 1024  # 50 KB, counted in characters

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _looks_like_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class JobCreate(BaseModel):
    """A pasted job posting, validated at the boundary.

    Required: ``title`` and ``company`` (non-blank, at most 512 chars). Optional:
    ``description``, ``requirements``, ``link``. A malformed ``link`` is dropped
    to ``None`` with a warning rather than rejected, since the link is optional
    and never fetched in M1. Unknown fields (``id``/``source``/``created_at``)
    are ignored, so the caller cannot set server-owned values.
    """

    title: str
    company: str
    description: str | None = None
    requirements: list[str] = []
    link: str | None = None

    @field_validator("title", "company")
    @classmethod
    def _non_blank_and_bounded(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        if len(stripped) > MAX_FIELD_LEN:
            raise ValueError(f"must be at most {MAX_FIELD_LEN} characters")
        return stripped

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("link")
    @classmethod
    def _lenient_link(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        if _looks_like_http_url(candidate):
            return candidate
        logger.warning("discarding malformed link: %r", value)
        return None


class Job(BaseModel):
    """The canonical persisted/returned job.

    ``id``, ``source`` and ``created_at`` are server-owned. Build instances with
    ``Job.new_from`` so those values are always generated here, never taken from
    caller input.
    """

    id: str
    source: Literal["pasted"] = "pasted"
    title: str
    company: str
    description: str = ""
    requirements: list[str] = []
    link: str | None = None
    created_at: datetime

    @classmethod
    def new_from(cls, data: JobCreate) -> "Job":
        return cls(
            id=uuid4().hex,
            title=data.title,
            company=data.company,
            description=data.description or "",
            requirements=list(data.requirements),
            link=data.link,
            created_at=datetime.now(UTC),
        )


# ---------------------------------------------------------------------------
# M2: candidate profile — value objects and validated input model
# ---------------------------------------------------------------------------

Seniority = Literal["junior", "pleno", "pleno-senior", "senior"]
Contract = Literal["CLT", "PJ", "other"]


class SalaryRange(BaseModel):
    """One salary expectation keyed by ``(currency, contract)``.

    ``currency`` is an ISO-4217-style upper-case triplet. The range must satisfy
    ``0 < floor <= target <= ceiling`` — a single number or a ``0``/negative bound
    would let the Matcher (M3) read the expectation as "any salary ok" (fail-open).
    """

    currency: str
    contract: Contract
    floor: int
    target: int
    ceiling: int

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, value: str) -> str:
        candidate = value.strip()
        if not _CURRENCY_RE.match(candidate):
            raise ValueError("must be a 3-letter upper-case currency code")
        return candidate

    @model_validator(mode="after")
    def _ordered_and_positive(self) -> "SalaryRange":
        if not 0 < self.floor <= self.target <= self.ceiling:
            raise ValueError("must satisfy 0 < floor <= target <= ceiling")
        return self


class Location(BaseModel):
    """Where and how the candidate wants to work. All free text is trimmed."""

    remote_preference: Literal["remote", "hybrid", "onsite"]
    open_to_international: bool = False
    base_location: str | None = None
    timezone: str | None = None

    @field_validator("base_location", "timezone")
    @classmethod
    def _trim_and_bound(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) > MAX_FIELD_LEN:
            raise ValueError(f"must be at most {MAX_FIELD_LEN} characters")
        return stripped


class ProfileCreate(BaseModel):
    """The authored candidate profile, validated at the boundary.

    Required: at least one non-blank ``skill`` and a ``seniority``. Everything
    else is optional and never fabricated when absent (BCP-04). ``raw_cv`` is
    stored verbatim after trim, never parsed (AD-009). Server-owned fields
    (``created_at``/``updated_at``) are not declared, so caller values are
    dropped (BCP-06).
    """

    skills: list[str]
    seniority: Seniority
    years_experience: int | None = Field(default=None, ge=0, le=60)
    salary_expectation: list[SalaryRange] = []
    location: Location | None = None
    raw_cv: str | None = None

    @field_validator("skills")
    @classmethod
    def _normalize_skills(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            skill = raw.strip()
            if not skill:
                continue
            if len(skill) > MAX_SKILL_LEN:
                raise ValueError(f"each skill must be at most {MAX_SKILL_LEN} characters")
            key = skill.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(skill)
        if not normalized:
            raise ValueError("at least one non-blank skill is required")
        return normalized

    @field_validator("raw_cv")
    @classmethod
    def _trim_raw_cv(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) > MAX_RAW_CV_LEN:
            raise ValueError("raw_cv must be at most 50 KB")
        return stripped

    @model_validator(mode="after")
    def _no_duplicate_salary_keys(self) -> "ProfileCreate":
        seen: set[tuple[str, str]] = set()
        for entry in self.salary_expectation:
            key = (entry.currency, entry.contract)
            if key in seen:
                raise ValueError(
                    "duplicate (currency, contract) in salary_expectation"
                )
            seen.add(key)
        return self


class Profile(ProfileCreate):
    """The canonical persisted/returned profile.

    Carries every normalized ``ProfileCreate`` field plus server-owned
    ``created_at``/``updated_at``. Build instances with ``Profile.new_from`` so
    those timestamps are always generated here: ``created_at`` is preserved from
    the existing row on a replace, ``updated_at`` always advances.
    """

    created_at: datetime
    updated_at: datetime

    @classmethod
    def new_from(
        cls, data: ProfileCreate, *, created_at: datetime | None = None
    ) -> "Profile":
        now = datetime.now(UTC)
        return cls(
            skills=data.skills,
            seniority=data.seniority,
            years_experience=data.years_experience,
            salary_expectation=data.salary_expectation,
            location=data.location,
            raw_cv=data.raw_cv,
            created_at=created_at or now,
            updated_at=now,
        )
