"""
Manager / admin routes, served under /mp/manager/.

Only managers reach these: marketplace/server.py checks auth.MANAGER_ONLY before
any of this code runs. Everything here reads and writes the SAME database tables the
team's existing backend uses; the only new table is marketplace_listings, which
remembers which manager posted a listing.
"""

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

import backend.api.resume_routes as resume_routes
from backend.api.application_routes import ensure_resume_text_column
from backend.database.database import get_connection
from marketplace.auth import get_session_user

router = APIRouter()

LISTING_STATUSES = ["Open", "Closed", "Filled"]

# Stored resume names are always 32 hex characters + .pdf/.docx (see resume_routes.py).
# Checking the pattern means a database value can never point outside the resume folder.
SAFE_RESUME_NAME = re.compile(r"^[0-9a-f]{32}\.(pdf|docx)$")


def ensure_marketplace_table(connection):
    """New side table: who posted each listing. The existing projects table is not changed."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_listings (
            project_id INTEGER PRIMARY KEY,
            posted_by_email TEXT,
            posted_by_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)


# ------------------------------------------
# 1. Listing management
# ------------------------------------------

@router.get("/projects")
def all_listings():
    """Every listing in any status (the shared feed only shows Open ones), with applicant counts."""
    connection = get_connection()

    try:
        ensure_marketplace_table(connection)
        rows = connection.execute("""
            SELECT
                projects.*,
                marketplace_listings.posted_by_name AS posted_by,
                COUNT(applications.id) AS applicant_count
            FROM projects
            LEFT JOIN marketplace_listings ON marketplace_listings.project_id = projects.id
            LEFT JOIN applications ON applications.project_id = projects.id
            GROUP BY projects.id
            ORDER BY projects.created_at DESC, projects.id DESC
        """).fetchall()
        return [dict(row) for row in rows]

    finally:
        connection.close()


class NewListing(BaseModel):
    title: str
    client_project: str = ""
    required_skills: str = ""
    nice_to_have_skills: str = ""
    seniority: str = ""
    location: str = ""
    start_date: str = ""
    description: str = ""


@router.post("/projects")
def create_listing(listing: NewListing, request: Request):
    title = listing.title.strip()

    if not title:
        raise HTTPException(status_code=400, detail="A listing needs a title.")

    manager = get_session_user(request)
    role_id = f"MP-{uuid4().hex[:8].upper()}"        # same role_id column the CSV import fills
    connection = get_connection()

    try:
        ensure_marketplace_table(connection)
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO projects (
                role_id, title, client_project, required_skills, nice_to_have_skills,
                seniority, location, start_date, status, description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?)
        """, (
            role_id, title, listing.client_project.strip(), listing.required_skills.strip(),
            listing.nice_to_have_skills.strip(), listing.seniority.strip(), listing.location.strip(),
            listing.start_date.strip(), listing.description.strip(),
        ))
        project_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO marketplace_listings (project_id, posted_by_email, posted_by_name) VALUES (?, ?, ?)",
            (project_id, manager["email"], manager["name"]),
        )
        connection.commit()

        return {"message": "Listing published.", "project_id": project_id, "role_id": role_id}

    finally:
        connection.close()


class ListingStatus(BaseModel):
    status: str


@router.patch("/projects/{project_id}/status")
def change_listing_status(project_id: int, update: ListingStatus):
    new_status = update.status.strip()

    if new_status not in LISTING_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(LISTING_STATUSES)}.")

    connection = get_connection()

    try:
        cursor = connection.execute("UPDATE projects SET status = ? WHERE id = ?", (new_status, project_id))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Listing not found.")

        connection.commit()
        return {"message": "Listing updated.", "project_id": project_id, "status": new_status}

    finally:
        connection.close()


# ------------------------------------------
# 2. Document viewer: one application + the listing it was submitted to
# ------------------------------------------

def find_application(connection, application_id):
    ensure_resume_text_column(connection)
    row = connection.execute("""
        SELECT
            applications.id AS application_id,
            applications.application_status,
            applications.cover_letter,
            applications.resume_filename,
            applications.submitted_at,
            employees.name AS applicant_name,
            employees.email AS applicant_email,
            employees.skills AS applicant_skills,
            employees.resume_text,
            projects.id AS project_id,
            projects.role_id,
            projects.title,
            projects.client_project,
            projects.required_skills,
            projects.seniority,
            projects.location,
            projects.start_date,
            projects.status AS project_status
        FROM applications
        JOIN employees ON applications.employee_id = employees.id
        JOIN projects ON applications.project_id = projects.id
        WHERE applications.id = ?
    """, (application_id,)).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    return dict(row)


@router.get("/applications/{application_id}/document")
def application_document(application_id: int):
    """Everything the viewer pane shows next to the attachment."""
    connection = get_connection()

    try:
        details = find_application(connection, application_id)
    finally:
        connection.close()

    filename = details.pop("resume_filename") or ""
    details["attachment_type"] = Path(filename).suffix.lstrip(".") if SAFE_RESUME_NAME.match(filename) else ""
    details["attachment_url"] = (
        f"/mp/manager/applications/{application_id}/attachment" if details["attachment_type"] else ""
    )
    return details


@router.get("/applications/{application_id}/attachment")
def application_attachment(application_id: int):
    """The submitted file itself. PDFs are sent 'inline' so the browser shows them in the pane."""
    connection = get_connection()

    try:
        filename = find_application(connection, application_id)["resume_filename"] or ""
    finally:
        connection.close()

    if not SAFE_RESUME_NAME.match(filename):
        raise HTTPException(status_code=404, detail="No attachment for this application.")

    # Read the folder at request time: deploy/server.py moves it into DATA_DIR at startup.
    path = resume_routes.RESUME_FOLDER / filename

    if not path.exists():
        raise HTTPException(status_code=404, detail="The attachment file is missing (data resets on restart).")

    is_pdf = filename.endswith(".pdf")
    return FileResponse(
        path,
        media_type="application/pdf" if is_pdf else
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"application-{application_id}{path.suffix}",
        content_disposition_type="inline" if is_pdf else "attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )
