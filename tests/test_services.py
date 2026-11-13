"""
Move 2 tests: schemas + services + thin routes.

Most tests call services DIRECTLY with a database connection: no HTTP, no browser.
That is the point of the service layer: the same functions work for routes, tests,
and (later) the MCP server. A few tests check the API contract through HTTP.
"""

import io
import zipfile

import pytest
from docx import Document

from backend.core import config
from backend.core.db import connect, create_tables
from backend.core.errors import Conflict, Invalid, NotFound, TooLarge
from backend.schemas.projects import ProjectIn, ProjectOut, ProjectStatus
from backend.schemas.users import User
from backend.services import applications, projects, resumes
from tests.conftest import login, make_pdf

CSV = (b"Job ID,Job Title,Client,Skills,Status\n"
       b"T-1,Backend Engineer,Payments,Python; SQL,open\n"
       b"T-2,Data Analyst,Health,SQL,OPEN \n"
       b"T-3,Old Role,Legacy,COBOL,Closed\n"
       b"T-4,Strange Role,X,Y,On hold\n")


ERIN = User(email="erin@x.test", name="Erin", role="employee")
MORGAN = User(email="manager@networker.test", name="Morgan Manager", role="manager")


@pytest.fixture
def db(data_dir):
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture
def listing(db):
    return projects.create(db, ProjectIn(title="  Teams bot  ", required_skills="Python; Azure"), MORGAN)


# ------------------------------------------
# Projects
# ------------------------------------------

def test_csv_import_recognises_aliases_and_statuses(db):
    result = projects.import_csv(db, CSV)
    assert result == {"imported": 3, "skipped": 1, "total_processed": 4}       # "On hold" is not a status

    statuses = {row["role_id"]: row["status"] for row in db.execute("SELECT role_id, status FROM projects")}
    assert statuses == {"T-1": "Open", "T-2": "Open", "T-3": "Closed"}

    again = projects.import_csv(db, CSV)                                         # same file twice
    assert again["imported"] == 0


@pytest.mark.parametrize("raw, message", [
    (b"", "empty"),
    (b"Name,Colour\nx,y\n", "Could not recognize"),
    ("Job ID,Job Title\nT-9,Café role\n".encode("cp1252"), "UTF-8"),
])
def test_csv_import_rejects_bad_files(db, raw, message):
    with pytest.raises(Invalid, match=message):
        projects.import_csv(db, raw)


def test_feed_shows_only_open_listings(db, listing):
    assert listing["title"] == "Teams bot"                     # ProjectIn trimmed the spaces
    assert [row["id"] for row in projects.list_open(db)] == [listing["id"]]

    projects.set_status(db, listing["id"], ProjectStatus.CLOSED, MORGAN)
    assert projects.list_open(db) == []

    managed = projects.list_for_managers(db)
    assert managed[0]["posted_by_name"] == "Morgan Manager" and managed[0]["applicant_count"] == 0


def test_old_free_text_statuses_are_normalised(db):
    db.execute("INSERT INTO projects (role_id, title, status) VALUES ('L-1', 'Legacy', ' oPeN ')")
    db.execute("INSERT INTO projects (role_id, title, status) VALUES ('L-2', 'Weird', 'paused')")
    db.commit()
    create_tables()
    rows = dict(db.execute("SELECT role_id, status FROM projects").fetchall())
    assert rows == {"L-1": "Open", "L-2": "Closed"}


def test_missing_listing_raises_not_found(db):
    with pytest.raises(NotFound):
        projects.get(db, 999)


# ------------------------------------------
# Resumes
# ------------------------------------------

def docx_bytes(text):
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_resume_checks(data_dir):
    assert "Python" in resumes.read_valid_resume("cv.pdf", make_pdf()).text
    assert "Kotlin" in resumes.read_valid_resume("cv.docx", docx_bytes("Kotlin and Swift")).text

    with pytest.raises(Invalid, match="Only PDF and DOCX"):
        resumes.read_valid_resume("cv.exe", b"MZ...")
    with pytest.raises(Invalid, match="not a valid PDF"):
        resumes.read_valid_resume("cv.pdf", b"<html>pretending</html>")
    with pytest.raises(TooLarge):
        resumes.read_valid_resume("cv.pdf", b"%PDF-" + b"0" * config.MAX_RESUME_BYTES)

    fake_docx = io.BytesIO()
    with zipfile.ZipFile(fake_docx, "w") as archive:
        archive.writestr("hello.txt", "not a Word file")
    with pytest.raises(Invalid, match="could not read"):
        resumes.read_valid_resume("cv.docx", fake_docx.getvalue())


def test_stored_names_cannot_escape_the_folder(data_dir):
    assert resumes.path_for("../../etc/passwd") is None
    assert resumes.path_for("0" * 32 + ".pdf") == config.RESUME_DIR / ("0" * 32 + ".pdf")


# ------------------------------------------
# Applications
# ------------------------------------------

def test_apply_then_duplicate_is_refused_without_orphan_files(db, listing):
    resume = resumes.read_valid_resume("cv.pdf", make_pdf())
    receipt = applications.submit(db, listing["id"], ERIN, "Python", "Hi", resume)
    assert receipt["resume_uploaded"] is True

    with pytest.raises(Conflict):
        applications.submit(db, listing["id"], ERIN, "Python", "Again", resume)

    assert len(list(config.RESUME_DIR.iterdir())) == 1          # the refused attempt saved nothing


def test_apply_to_closed_listing_is_refused(db, listing):
    projects.set_status(db, listing["id"], ProjectStatus.FILLED, MORGAN)
    with pytest.raises(NotFound, match="no longer open"):
        applications.submit(db, listing["id"], ERIN, "", "", None)


def test_second_application_reuses_profile_resume(db, listing):
    other = projects.create(db, ProjectIn(title="Second"), MORGAN)
    resume = resumes.read_valid_resume("cv.pdf", make_pdf())
    applications.submit(db, listing["id"], ERIN, "Python", "", resume)
    applications.submit(db, other["id"], ERIN, "Python", "", None)

    viewer = applications.get_document(db, applications.list_for_email(db, "erin@x.test")[0]["application_id"])
    assert viewer["attachment_type"] == "pdf"
    assert viewer["project"]["title"] in ("Teams bot", "Second")


def test_review_flow(db, listing):
    receipt = applications.submit(db, listing["id"], ERIN, "Python", "", None)
    applications.set_status(db, receipt["application_id"], "Under Review", MORGAN)

    applicant = applications.list_for_project(db, listing["id"])[0]
    assert (applicant["status"], applicant["has_attachment"]) == ("Under Review", False)

    with pytest.raises(NotFound):
        applications.attachment_path(db, receipt["application_id"])


# ------------------------------------------
# API contract (through HTTP)
# ------------------------------------------

def test_feed_returns_exactly_the_public_shape(client):
    login(client, "employee")
    listing = client.get("/api/projects").json()[0]
    assert set(listing) == set(ProjectOut.model_fields)          # no internal columns leak out
    assert "posted_by_email" not in listing


def test_bad_status_is_refused_by_the_schema(client):
    login(client, "manager")
    project_id = client.get("/api/projects").json()[0]["id"]
    response = client.patch(f"/api/projects/{project_id}/status", json={"status": "Maybe"})
    assert response.status_code == 422


def test_service_errors_become_http_codes(client):
    login(client, "manager")
    assert client.get("/api/projects/999").status_code == 404
    assert client.get("/api/applications/999/document").status_code == 404
    bad_csv = client.post("/api/projects/upload-csv", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert bad_csv.status_code == 400 and "Could not recognize" in bad_csv.json()["detail"]


def test_transaction_rolls_back_everything_on_error(db):
    from backend.core.db import transaction

    with pytest.raises(RuntimeError):
        with transaction(db):
            db.execute("INSERT INTO projects (role_id, title) VALUES ('R-1', 'Half-written')")
            raise RuntimeError("something failed halfway")

    assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
