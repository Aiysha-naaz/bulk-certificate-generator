from app import generator

GOOD = [
    {"name": "Asha Rao", "email": "asha@example.com"},
    {"name": "Ravi Kumar", "email": "ravi@example.com", "course": "Python 101"},
]


def make_job(client, recipients, **extra):
    return client.post("/jobs", json={"event_name": "PyCon", "recipients": recipients, **extra})


def test_create_job(client):
    r = make_job(client, GOOD)
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"] and body["status_url"].endswith(body["job_id"])


def test_request_level_validation(client):
    assert make_job(client, []).status_code == 422
    assert client.post("/jobs", json={"recipients": GOOD}).status_code == 422  # no event_name


def test_invalid_recipient_does_not_block_others(client):
    bad = [{"name": "", "email": "x@example.com"}, {"name": "No Email"}, {"name": "Bad", "email": "nope"}]
    job_id = make_job(client, GOOD + bad).json()["job_id"]
    s = client.get(f"/jobs/{job_id}").json()
    assert (s["total"], s["succeeded"], s["failed"]) == (5, 2, 3)
    assert s["status"] == "completed_with_errors"
    failed = client.get(f"/jobs/{job_id}/certificates", params={"status": "failed"}).json()
    assert all("validation error" in f["error"] for f in failed)


def test_certificate_generation_creates_pdf(client):
    job_id = make_job(client, GOOD).json()["job_id"]
    certs = client.get(f"/jobs/{job_id}/certificates").json()
    r = client.get(certs[0]["download_url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_job_status_and_progress(client):
    job_id = make_job(client, GOOD).json()["job_id"]
    s = client.get(f"/jobs/{job_id}").json()
    assert s["status"] == "completed"
    assert s["progress_percent"] == 100.0
    assert s["pending"] == 0
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_individual_generation_failure(client, monkeypatch):
    real = generator.generate_pdf

    def flaky(cert_id, name, *a, **kw):
        if name == "Boom":
            raise RuntimeError("render failed")
        return real(cert_id, name, *a, **kw)

    monkeypatch.setattr(generator, "generate_pdf", flaky)
    recipients = [GOOD[0], {"name": "Boom", "email": "boom@example.com"}, GOOD[1]]
    job_id = make_job(client, recipients).json()["job_id"]

    s = client.get(f"/jobs/{job_id}").json()
    assert (s["succeeded"], s["failed"], s["status"]) == (2, 1, "completed_with_errors")
    failed = client.get(f"/jobs/{job_id}/certificates", params={"status": "failed"}).json()
    assert failed[0]["recipient"]["name"] == "Boom"
    assert "render failed" in failed[0]["error"]


def test_retrieve_certificates(client):
    job_id = make_job(client, GOOD + [{"name": "Bad", "email": "nope"}]).json()["job_id"]
    certs = client.get(f"/jobs/{job_id}/certificates").json()
    assert len(certs) == 3
    failed = [c for c in certs if c["status"] == "failed"][0]
    assert client.get(f"/certificates/{failed['id']}/download").status_code == 409
    assert client.get("/certificates/unknown/download").status_code == 404

    z = client.get(f"/jobs/{job_id}/download")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    

def test_retry_failed_generation(client, monkeypatch):
    real = generator.generate_pdf
    state = {"fail": True}

    def flaky(cert_id, name, *a, **kw):
        if name == "Boom" and state["fail"]:
            raise RuntimeError("render failed")
        return real(cert_id, name, *a, **kw)

    monkeypatch.setattr(generator, "generate_pdf", flaky)
    recipients = [GOOD[0], {"name": "Boom", "email": "boom@example.com"},
                  {"name": "Bad", "email": "nope"}]
    job_id = make_job(client, recipients).json()["job_id"]

    s = client.get(f"/jobs/{job_id}").json()
    assert (s["succeeded"], s["failed"]) == (1, 2)

    state["fail"] = False  # the problem is fixed, so a retry should work
    r = client.post(f"/jobs/{job_id}/retry")
    assert r.status_code == 202
    assert r.json()["retrying"] == 1  # only Boom, not the validation failure

    s = client.get(f"/jobs/{job_id}").json()
    assert (s["succeeded"], s["failed"]) == (2, 1)
    assert s["status"] == "completed_with_errors"

    # Only the validation failure is left, so retrying again is refused
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409
    assert client.post("/jobs/does-not-exist/retry").status_code == 404