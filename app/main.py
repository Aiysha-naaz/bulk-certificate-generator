import io
import re
import zipfile

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import service
from .database import Base, engine, get_db
from .models import Certificate, Job
from .schemas import JobCreate

Base.metadata.create_all(engine)
app = FastAPI(title="Bulk Certificate Generator")


def _job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/jobs", status_code=202)
def create_job(body: JobCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    job = service.create_job(db, body)
    background.add_task(service.process_job, job.id)
    return {"job_id": job.id, "status": "pending", "status_url": f"/jobs/{job.id}"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    c = service.counts(db, job.id)
    done = c["success"] + c["failed"]
    return {
        "job_id": job.id,
        "status": job.status,
        "event_name": job.event_name,
        "total": c["total"],
        "succeeded": c["success"],
        "failed": c["failed"],
        "pending": c["pending"],
        "progress_percent": round(100 * done / c["total"], 1) if c["total"] else 100.0,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


@app.get("/jobs/{job_id}/certificates")
def list_certificates(job_id: str, status: str | None = None, db: Session = Depends(get_db)):
    _job_or_404(db, job_id)
    q = select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.row_index)
    if status:
        q = q.where(Certificate.status == status)
    return [
        {
            "id": c.id,
            "row_index": c.row_index,
            "recipient": c.payload,
            "status": c.status,
            "error": c.error,
            "download_url": f"/certificates/{c.id}/download" if c.status == "success" else None,
        }
        for c in db.scalars(q)
    ]


@app.get("/certificates/{cert_id}/download")
def download_certificate(cert_id: str, db: Session = Depends(get_db)):
    cert = db.get(Certificate, cert_id)
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if cert.status != "success":
        raise HTTPException(409, f"Certificate is not available (status: {cert.status})")
    return FileResponse(cert.file_path, media_type="application/pdf",
                        filename=f"certificate-{cert.id[:8]}.pdf")


@app.get("/jobs/{job_id}/download")
def download_job_zip(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    if job.status in ("pending", "processing"):
        raise HTTPException(409, "Job is still running")
    certs = db.scalars(select(Certificate).where(
        Certificate.job_id == job_id, Certificate.status == "success")).all()
    if not certs:
        raise HTTPException(404, "No certificates were generated for this job")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in certs:
            slug = re.sub(r"[^a-z0-9]+", "-", c.payload["name"].lower()).strip("-")
            z.write(c.file_path, f"{c.row_index:04d}-{slug}.pdf")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="job-{job_id[:8]}.zip"'})