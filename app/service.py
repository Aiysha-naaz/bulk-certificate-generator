from datetime import date
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import generator
from .database import SessionLocal
from .models import Job, Certificate, now
from .schemas import JobCreate, Recipient


def create_job(db: Session, data: JobCreate) -> Job:
    job = Job(
        event_name=data.event_name,
        issued_date=(data.issued_date or date.today()).isoformat(),
    )
    db.add(job)
    db.flush()

    for i, raw in enumerate(data.recipients):
        try:
            clean = Recipient.model_validate(raw).model_dump()
            db.add(Certificate(job_id=job.id, row_index=i, payload=clean))
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            db.add(Certificate(job_id=job.id, row_index=i, payload=raw,
                               status="failed", error=f"validation error: {msg}"))
    db.commit()
    return job


def counts(db: Session, job_id: str) -> dict:
    rows = db.execute(
        select(Certificate.status, func.count()).where(Certificate.job_id == job_id)
        .group_by(Certificate.status)
    ).all()
    c = {"pending": 0, "success": 0, "failed": 0}
    c.update(dict(rows))
    c["total"] = sum(c.values())
    return c


def process_job(job_id: str) -> None:
    """Runs in the background with its own session. Each certificate is
    isolated in try/except and committed individually so progress is visible
    and one failure never stops the rest."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        job.status = "processing"
        db.commit()

        pending = db.scalars(
            select(Certificate).where(Certificate.job_id == job_id, Certificate.status == "pending")
            .order_by(Certificate.row_index)
        ).all()

        for cert in pending:
            try:
                p = cert.payload
                cert.file_path = generator.generate_pdf(
                    cert.id, p["name"], job.event_name, job.issued_date, p.get("course")
                )
                cert.status = "success"
            except Exception as e:  # noqa: BLE001
                cert.status = "failed"
                cert.error = f"generation error: {e}"
            db.commit()

        c = counts(db, job_id)
        if c["failed"] == 0:
            job.status = "completed"
        elif c["success"] == 0:
            job.status = "failed"
        else:
            job.status = "completed_with_errors"
        job.finished_at = now()
        db.commit()
    except Exception:
        db.rollback()
        job = db.get(Job, job_id)
        if job:
            job.status = "failed"
            db.commit()
        raise
    finally:
        db.close()


def reset_failed_generations(db: Session, job_id: str) -> int:
    """Move certificates that failed during generation back to pending.
    Validation failures are skipped, because retrying bad data cannot help."""
    certs = db.scalars(
        select(Certificate).where(
            Certificate.job_id == job_id,
            Certificate.status == "failed",
            Certificate.error.like("generation error:%"),
        )
    ).all()
    for c in certs:
        c.status = "pending"
        c.error = None
    db.commit()
    return len(certs)