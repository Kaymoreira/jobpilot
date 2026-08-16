"""Domain models for JobPilot.

`JobCreate` is the validated paste input; `Job` (added in T2) is the canonical
stored/response shape. Validation lives here so an invalid paste fails
explicitly instead of producing a half-filled Job.
"""

import logging
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, field_validator

logger = logging.getLogger("jobpilot")

MAX_FIELD_LEN = 512


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
