# JobPilot

Autonomous job-application agent. It ingests job postings, scores the *fit*
against my CV, generates a tailored CV and cover letter for each posting, and
builds a **queue of ready-to-send applications**.

**Product decision:** the agent is autonomous up to the queue. The **final
submission is always a human click**, never an automatic submit on a
third-party job board. Reasons: (1) the ToS of LinkedIn, Gupy and similar
boards forbid automated submission; (2) applying to the wrong job is the
classic *fail-open* (the gate that approves when it should block). The decision
point stays with the person.

## Architecture (ports and adapters)

```
[JobSource] -> [Normalizer] -> [Matcher] -> [Generator] -> [ApplicationQueue] -> [Report/UI]
  (port)       (canonical Job)  (score+fit)  (CV+cover)     (persistence)         (one click)
```

The job source is pluggable: the core does not depend on *where the job comes
from*.

## Stack

- Python 3.12+ / FastAPI
- pytest + pytest-cov with a **coverage gate** (`--cov-fail-under=80`)
- SQLite (local persistence, from M1 onward)

## Running

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash/macOS/Linux:    source .venv/bin/activate
pip install -e ".[dev]"

# API
uvicorn jobpilot.app:app --reload
# health:      http://127.0.0.1:8000/health
# interactive: http://127.0.0.1:8000/docs

# Tests + coverage
pytest
```

## Status

M0 (skeleton) done: FastAPI + health check + coverage gate active and verified
on the failing path. Later milestones (M1+) are delivered through spec-driven
development.

## Roadmap

See the planning brief for the milestone breakdown (M0-M7).
