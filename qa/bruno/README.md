# JobPilot API — Bruno collection

Native [Bruno](https://www.usebruno.com/) collection for **manual** testing of
the Jobs and Profile endpoints. It exercises the happy path and the failure
path; every request documents the status code it should return in its `docs`
tab.

This is a Fase 1 chore. There are **no CI wiring and no automated assertions** by
design, that is a separate Fase 2 card. You read the responses yourself and
compare against the documented expectation.

## Layout

```
qa/bruno/
├── bruno.json                 # collection manifest
├── environments/
│   └── Local.bru              # baseUrl = http://127.0.0.1:8000
├── Happy Path/
│   ├── 01 Health.bru
│   ├── 02 Create job.bru
│   ├── 03 List jobs.bru
│   ├── 04 Get job by id.bru
│   ├── 05 Upsert profile (create).bru
│   ├── 06 Upsert profile (replace).bru
│   └── 07 Get profile.bru
└── Failure Path/
    ├── 01 Create job - blank title.bru
    ├── 02 Create job - oversized body.bru
    ├── 03 Get job - not found.bru
    ├── 04 Upsert profile - no skills.bru
    ├── 05 Upsert profile - bad salary.bru
    └── 06 Get profile - not found.bru
```

## Run the API

From the repository root, with the project's virtualenv active:

```bash
uvicorn jobpilot.app:app --host 127.0.0.1 --port 8000
```

The server persists to `jobpilot.db` (SQLite) by default. To point at a clean,
throwaway file so the failure-path "not found" cases behave as documented, set
`JOBPILOT_DB`:

```bash
JOBPILOT_DB=jobpilot-qa.db uvicorn jobpilot.app:app --host 127.0.0.1 --port 8000
```

Confirm it is up with `GET /health` (Happy Path → Health), which should return
`200`.

## Run the collection

1. Open Bruno and **Open Collection**, pointing at `qa/bruno/`.
2. Select the **Local** environment (top-right). It sets `baseUrl` to
   `http://127.0.0.1:8000`.
3. Send the requests and compare each response's status code with the value in
   the request's `docs` tab.

### Suggested order

Some requests depend on state, so run them in sequence:

**Failure Path first (fresh DB):** the two "not found" cases assume nothing has
been created yet.

- `Get job - not found` → 404
- `Get profile - not found` → 404
- `Create job - blank title` → 422
- `Create job - oversized body` → 422. A pre-request script generates a
  60000-char body at send time (no large literal committed to the repo), so you
  just send it as-is. Also covered by the automated pytest suite
  (`tests/test_body_limit.py`). See the request's `docs` tab.
- `Upsert profile - no skills` → 422
- `Upsert profile - bad salary` → 422

**Then Happy Path:**

1. `Health` → 200
2. `Create job` → 201. Copy the returned `id`.
3. `List jobs` → 200 (array now contains the job).
4. `Get job by id` → 200. First set the request's `jobId` variable to the id
   from step 2.
5. `Upsert profile (create)` → 201 (first author on a fresh DB).
6. `Upsert profile (replace)` → 200 (profile now exists; `created_at` is
   preserved, `updated_at` advances).
7. `Get profile` → 200.

## Endpoint reference

| Method & path      | Happy | Failure |
|--------------------|-------|---------|
| `GET /health`      | 200   | —       |
| `POST /jobs`       | 201   | 422 (blank title / body > 50 KB) |
| `GET /jobs`        | 200   | —       |
| `GET /jobs/{id}`   | 200   | 404 (unknown id) |
| `PUT /profile`     | 201 create / 200 replace | 422 (no skills / bad salary range) |
| `GET /profile`     | 200   | 404 (no profile yet) |
