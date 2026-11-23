from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NETWORKER_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("NETWORKER_UPLOAD_DIR", str(tmp_path / "uploads"))

    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client


def make_docx(text):
    buffer = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def first_project(client, title):
    return next(p for p in client.get("/projects").json() if p["title"] == title)


def apply(client, project_id, email="ada@example.com", skills="", files=None):
    return client.post(
        "/applications",
        data={
            "project_id": project_id,
            "name": "Ada Lovelace",
            "email": email,
            "skills": skills,
        },
        files=files,
    )


def test_sample_roles_are_seeded_and_only_open_ones_listed(client):
    open_projects = client.get("/projects").json()
    all_projects = client.get("/projects", params={"include_closed": True}).json()

    assert len(all_projects) == 19
    assert len(open_projects) == 15
    assert all(p["status"] == "Open" for p in open_projects)
    assert all("applicant_count" in p for p in all_projects)


def test_website_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "ProjectHub" in response.text
    assert client.get("/sample-projects.json").status_code == 200


def test_recommendations_rank_by_skill_match(client):
    response = client.post(
        "/matches/recommend",
        json={"skills": ["Power BI", "DAX", "SQL", "Excel", "Data Cleaning"]},
    )
    ranked = response.json()

    assert response.status_code == 200
    assert ranked[0]["title"] == "Data Analyst"
    assert ranked[0]["match"]["score"] == 80
    scores = [p["match"]["score"] for p in ranked]
    assert scores == sorted(scores, reverse=True)


def test_application_records_match_and_manager_sees_ranked_applicants(client):
    project = first_project(client, "Data Analyst")

    strong = apply(client, project["id"], "strong@example.com", "SQL, Excel, Power BI, Data Cleaning")
    weak = apply(client, project["id"], "weak@example.com", "Excel")

    assert strong.status_code == 200, strong.text
    assert strong.json()["match_score"] == 80
    assert weak.json()["match_score"] == 20

    applicants = client.get(f"/projects/{project['id']}/applications").json()
    assert [a["email"] for a in applicants] == ["strong@example.com", "weak@example.com"]
    assert applicants[1]["match"]["missing_required"] == ["SQL", "Power BI", "Data Cleaning"]
    assert "resume_text" not in applicants[0]


def test_resume_text_feeds_the_match(client):
    project = first_project(client, "Data Analyst")
    resume = make_docx("Analyst with SQL, Power BI and Python experience.")

    response = apply(
        client, project["id"], skills="Excel",
        files={"resume": ("resume.docx", resume, "application/octet-stream")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["resume_uploaded"] is True
    # Excel (skills) + SQL, Power BI (resume) = 3/4 required, Python 1/2 nice.
    assert response.json()["match_score"] == 70


def test_duplicate_application_is_rejected(client):
    project = first_project(client, "Data Analyst")
    assert apply(client, project["id"]).status_code == 200
    assert apply(client, project["id"]).status_code == 409


def test_closed_project_rejects_applications(client):
    filled = next(
        p for p in client.get("/projects", params={"include_closed": True}).json()
        if p["status"] == "Filled"
    )
    assert apply(client, filled["id"]).status_code == 404


def test_invalid_inputs(client):
    project = first_project(client, "Data Analyst")

    assert apply(client, project["id"], email="not-an-email").status_code == 400

    fake_pdf = {"resume": ("resume.pdf", b"not a pdf", "application/pdf")}
    assert apply(client, project["id"], files=fake_pdf).status_code == 400

    exe = {"resume": ("resume.exe", b"MZ", "application/octet-stream")}
    assert apply(client, project["id"], files=exe).status_code == 400


def test_status_update_and_tracking(client):
    project = first_project(client, "Data Analyst")
    application_id = apply(client, project["id"]).json()["application_id"]

    assert client.patch(
        f"/applications/{application_id}/status", json={"status": "Bogus"}
    ).status_code == 400

    assert client.patch(
        f"/applications/{application_id}/status", json={"status": "Accepted"}
    ).status_code == 200

    tracked = client.get("/applications/my-applications", params={"email": "ADA@example.com"}).json()
    assert tracked["total_applications"] == 1
    assert tracked["applications"][0]["status"] == "Accepted"


def test_resume_parse_detects_known_skills(client):
    resume = make_docx("Skilled in Terraform, Kubernetes and Python.")

    response = client.post(
        "/resumes/parse",
        files={"file": ("cv.docx", resume, "application/octet-stream")},
    )

    assert response.status_code == 200
    assert set(response.json()["detected_skills"]) >= {"Terraform", "Kubernetes", "Python"}


def test_csv_upload_adds_and_updates_roles(client):
    csv_text = (
        "Job ID,Job Title,Skills,Status\n"
        "NEW-1,Rust Developer,Rust; Linux,Open\n"
        "SMP-001,Data Analyst,SQL; Excel,Filled\n"
        ",Missing ID,,Open\n"
    )

    result = client.post(
        "/projects/upload-csv",
        files={"file": ("roles.csv", csv_text.encode(), "text/csv")},
    ).json()

    assert (result["imported"], result["updated"], result["skipped"]) == (1, 1, 1)

    titles = [p["title"] for p in client.get("/projects").json()]
    assert "Rust Developer" in titles
    assert "Data Analyst" not in titles  # now Filled

    # Columns missing from the CSV keep their existing values.
    analyst = next(
        p for p in client.get("/projects", params={"include_closed": True}).json()
        if p["role_id"] == "SMP-001"
    )
    assert analyst["client_project"] == "Summit Retail Group - Sales Reporting"
