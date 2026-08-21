"""HTTP endpoints for the single candidate profile.

The router depends on the `ProfileRepository` port through
`get_profile_repository`, which resolves `request.app.state.profile_repo`. Tests
override it to inject a fake or a failing repository.

`PUT /profile` is create-or-replace: the route reads first so it can return `201`
on the first author and `200` on a replace, and so a replace preserves the
original `created_at`. A storage failure surfaces as a `500` with a generic body
so no internal detail (stack trace, SQL) leaks to the client, while the real
cause is logged server-side.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from jobpilot.models import Profile, ProfileCreate
from jobpilot.repository import ProfileRepository, RepositoryError

logger = logging.getLogger("jobpilot")

router = APIRouter()

INTERNAL_ERROR_BODY = {"detail": "internal error"}


def get_profile_repository(request: Request) -> ProfileRepository:
    return request.app.state.profile_repo


@router.put("/profile", response_model=Profile)
def upsert_profile(
    payload: ProfileCreate,
    response: Response,
    repo: ProfileRepository = Depends(get_profile_repository),
):
    try:
        existing = repo.get()
        profile = Profile.new_from(
            payload,
            created_at=existing.created_at if existing is not None else None,
        )
        stored = repo.upsert(profile)
    except RepositoryError:
        # Record the real cause (with traceback) server-side so the incident is
        # diagnosable; the client still gets only the generic body below.
        logger.exception("failed to persist profile")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=INTERNAL_ERROR_BODY,
        )
    if existing is None:
        response.status_code = status.HTTP_201_CREATED
    return stored


@router.get("/profile", response_model=Profile)
def read_profile(
    repo: ProfileRepository = Depends(get_profile_repository),
) -> Profile:
    profile = repo.get()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return profile
