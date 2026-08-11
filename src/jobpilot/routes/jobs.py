"""HTTP endpoints for the PastedJobSource.

The router depends on the `JobRepository` port through `get_repository`, which
resolves `request.app.state.repo`. Tests override `app.state.repo` to inject a
fake or a failing repository. A storage failure surfaces as a 500 with a generic
body so no internal detail (stack trace, SQL) leaks to the client.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from jobpilot.models import Job, JobCreate
from jobpilot.repository import JobRepository, RepositoryError

router = APIRouter()

INTERNAL_ERROR_BODY = {"detail": "internal error"}


def get_repository(request: Request) -> JobRepository:
    return request.app.state.repo


@router.post("/jobs", status_code=status.HTTP_201_CREATED, response_model=Job)
def create_job(payload: JobCreate, repo: JobRepository = Depends(get_repository)):
    job = Job.new_from(payload)
    try:
        return repo.add(job)
    except RepositoryError:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=INTERNAL_ERROR_BODY,
        )


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, repo: JobRepository = Depends(get_repository)) -> Job:
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return job


@router.get("/jobs", response_model=list[Job])
def list_jobs(repo: JobRepository = Depends(get_repository)) -> list[Job]:
    return repo.list_all()
