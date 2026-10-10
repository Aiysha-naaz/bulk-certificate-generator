# Bulk Certificate Generator

A backend API that accepts a list of recipients and generates a PDF certificate for each one using a single predefined template. Built with FastAPI, SQLAlchemy (SQLite by default) and ReportLab.

## Setup

Requires Python 3.10 or higher.

```
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

## Run

```
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs

Optional environment variables:
- `DATABASE_URL` (default: `sqlite:///./certs.db`)
- `CERT_OUTPUT_DIR` (default: `./generated`)

## Run tests

```
pytest -v
```

## Submit a certificate generation request

```
curl -X POST http://localhost:8000/jobs -H "Content-Type: application/json" -d '{
  "event_name": "PyCon 2026",
  "issued_date": "2026-10-01",
  "recipients": [
    {"name": "Asha Rao", "email": "asha@example.com"},
    {"name": "Ravi Kumar", "email": "ravi@example.com", "course": "Python 101"}
  ]
}'
```

Returns `202 Accepted` with a `job_id` and a `status_url`. `issued_date` and `course` are optional.

## Track progress and retrieve certificates

| Endpoint | Purpose |
|---|---|
| `GET /jobs/{job_id}` | Status, counts (total, succeeded, failed, pending) and progress percent |
| `GET /jobs/{job_id}/certificates` | Per-recipient result with error message; filter with `?status=failed` |
| `GET /certificates/{cert_id}/download` | Download one PDF |
| `GET /jobs/{job_id}/download` | Download a ZIP of all successful PDFs |
| `POST /jobs/{job_id}/retry` | Re-run only the certificates that failed during generation (validation failures are not retried) |

Job statuses: `pending`, `processing`, `completed`, `completed_with_errors`, `failed`.

## Design decisions

**Background processing.** `POST /jobs` returns immediately with `202` and the work runs in a FastAPI background task. A large batch would otherwise block the request and risk HTTP timeouts. The client polls `GET /jobs/{job_id}` for progress.

**Per-recipient validation.** The request shape is validated by FastAPI (422 on a malformed request). Each recipient is then validated individually, so one bad row does not reject the whole request. Invalid rows are stored as `failed` with a reason, and valid rows still get certificates.

**Failure isolation.** Each certificate is generated in its own try/except and committed separately. One failure never stops the rest of the job, and progress is visible while the job runs.

**Retry.** Only certificates that failed during generation are retried. Validation failures are skipped, because bad data would fail the same way again. `process_job` only picks up `pending` rows, so re-running it redoes just the reset ones.

**Status derived from data.** Counts come from a `GROUP BY` query on the certificates table instead of stored counters, so they cannot drift out of sync.

**File naming.** PDFs are stored on disk named by certificate UUID, so user input never ends up in a file path.

**Limits.** A single request accepts 1 to 5000 recipients.

## Limitations and what I would change for production

- **Durability.** Background tasks run inside the web process. If the server restarts mid-job, the job stays stuck in `processing`. In production I would use a task queue (Celery or RQ with Redis). `process_job` takes only a job id, so moving it to a queue is a small change.
- **Multiple workers.** Two workers could pick up the same job. I would claim a job with an atomic `UPDATE ... WHERE status = 'pending'` before processing.
- **Storage.** PDFs are on local disk. In production I would use object storage such as S3.
- **Authentication.** Endpoints are open. A real deployment needs auth and per-user access to jobs.