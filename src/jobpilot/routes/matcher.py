"""HTTP endpoint for the advisory matcher.

`POST /jobs/{job_id}/match` takes no request body: the job is in the path and
the profile is the singleton, so a caller has nothing to inject (MATCH-05). The
route reads the job (`404` if absent, MATCH-09) and the profile, then delegates
to the side-effect-free `match_job` service — it performs `.get()` reads only and
never writes (MATCH-11/12). A storage read failure surfaces as a generic `500`
(never a verdict); an LLM failure or bad output fails closed to `cannot_assess`
inside `match_job`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from jobpilot.matching import Matcher, match_job
from jobpilot.models import MatchResult
from jobpilot.repository import JobRepository, ProfileRepository, RepositoryError
from jobpilot.routes.jobs import get_repository
from jobpilot.routes.profile import get_profile_repository

logger = logging.getLogger("jobpilot")

router = APIRouter()

INTERNAL_ERROR_BODY = {"detail": "internal error"}


def get_matcher(request: Request) -> Matcher:
    return request.app.state.matcher


@router.post("/jobs/{job_id}/match", response_model=MatchResult)
def match_job_endpoint(
    job_id: str,
    job_repo: JobRepository = Depends(get_repository),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    matcher: Matcher = Depends(get_matcher),
):
    try:
        job = job_repo.get(job_id)
        profile = profile_repo.get()
    except RepositoryError:
        # A storage blip must not be read as a fit verdict — record the cause
        # server-side and return the generic body, like M1/M2.
        logger.exception("failed to read job or profile for match")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=INTERNAL_ERROR_BODY,
        )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return match_job(job, profile, matcher)
