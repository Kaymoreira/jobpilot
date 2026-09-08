"""HTTP endpoint for the advisory generator.

`POST /jobs/{job_id}/generate` takes no request body: the job is in the path and
the profile is the singleton, so a caller has nothing to inject (GEN-06). The
route reads the job (`404` if absent, GEN-14) and the profile, then delegates to
the side-effect-free `generate_letter` service — which recomputes the match
internally for server-authoritative gaps and drafts a letter, performing `.get()`
reads only and never writing (GEN-16/17). A storage read failure surfaces as a
generic `500` (never a draft, GEN-21); a `cannot_assess` match or an LLM failure
fails closed to `cannot_generate` inside `generate_letter`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from jobpilot.generation import Generator, generate_letter
from jobpilot.models import GenerateResult
from jobpilot.repository import JobRepository, ProfileRepository, RepositoryError
from jobpilot.routes.jobs import get_repository
from jobpilot.routes.matcher import get_matcher
from jobpilot.routes.profile import get_profile_repository

logger = logging.getLogger("jobpilot")

router = APIRouter()

INTERNAL_ERROR_BODY = {"detail": "internal error"}


def get_generator(request: Request) -> Generator:
    return request.app.state.generator


@router.post("/jobs/{job_id}/generate", response_model=GenerateResult)
def generate_endpoint(
    job_id: str,
    job_repo: JobRepository = Depends(get_repository),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    matcher=Depends(get_matcher),
    generator: Generator = Depends(get_generator),
):
    try:
        job = job_repo.get(job_id)
        profile = profile_repo.get()
    except RepositoryError:
        # A storage blip must not be read as a draft outcome — record the cause
        # server-side and return the generic body, like M1/M2/M3.
        logger.exception("failed to read job or profile for generate")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=INTERNAL_ERROR_BODY,
        )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return generate_letter(job, profile, matcher, generator)
