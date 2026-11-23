import json
import sqlite3

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, ValidationError, TypeAdapter

from backend.api.resume_routes import read_resume, save_resume
from backend.database.database import get_connection
from backend.matching import Candidate, score_project

router = APIRouter()

ALLOWED_STATUSES = ["Submitted", "Under Review", "Accepted", "Rejected"]

_email_adapter = TypeAdapter(EmailStr)


def validate_email(email):
    try:
        return str(_email_adapter.validate_python(email.strip())).lower()
    except ValidationError:
        raise HTTPException(400, "Please provide a valid email address.")


class ApplicationStatusUpdate(BaseModel):
    status: str


# ==========================================
# SUBMIT AN APPLICATION
# ==========================================

@router.post("")
async def submit_application(
    project_id: int = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    skills: str = Form(""),
    cover_letter: str = Form(""),
    resume: UploadFile | None = File(None),
):
    """Apply to an open project, optionally with a PDF or DOCX resume.

    Without a new resume, the applicant's previously uploaded resume is reused.
    """
    name = name.strip()
    email = validate_email(email)

    if not name:
        raise HTTPException(400, "Please provide your name.")

    # Read and validate the resume before touching the database.
    new_resume = await read_resume(resume) if resume and resume.filename else None

    connection = get_connection()
    saved_path = None

    try:
        project = connection.execute(
            "SELECT * FROM projects WHERE id = ? AND LOWER(TRIM(status)) = 'open'",
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(404, "This project is unavailable.")

        employee = connection.execute(
            "SELECT * FROM employees WHERE email = ?", (email,)
        ).fetchone()

        if employee is not None:
            already_applied = connection.execute(
                "SELECT 1 FROM applications WHERE employee_id = ? AND project_id = ?",
                (employee["id"], project_id),
            ).fetchone()

            if already_applied:
                raise HTTPException(409, "You have already applied to this project.")

        resume_filename = (employee["resume_filename"] if employee else "") or ""
        resume_text = (employee["resume_text"] if employee else "") or ""

        if new_resume:
            contents, extension, resume_text = new_resume
            resume_filename, saved_path = save_resume(contents, extension)

        if employee is not None:
            employee_id = employee["id"]
            connection.execute(
                """
                UPDATE employees
                SET name = ?, skills = ?, resume_filename = ?, resume_text = ?
                WHERE id = ?
                """,
                (name, skills, resume_filename, resume_text, employee_id),
            )
        else:
            employee_id = connection.execute(
                """
                INSERT INTO employees (name, email, skills, resume_filename, resume_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, skills, resume_filename, resume_text),
            ).lastrowid

        application_id = connection.execute(
            """
            INSERT INTO applications (
                employee_id, project_id, application_status,
                resume_filename, cover_letter
            )
            VALUES (?, ?, 'Submitted', ?, ?)
            """,
            (employee_id, project_id, resume_filename, cover_letter),
        ).lastrowid

        # Record how well the applicant matched the project when they applied.
        match = score_project(dict(project), Candidate(skills, resume_text))
        details = {key: value for key, value in match.items() if key != "score"}

        connection.execute(
            """
            INSERT INTO matches (employee_id, project_id, match_score, matched_skills)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(employee_id, project_id) DO UPDATE SET
                match_score = excluded.match_score,
                matched_skills = excluded.matched_skills,
                created_at = CURRENT_TIMESTAMP
            """,
            (employee_id, project_id, match["score"], json.dumps(details)),
        )

        connection.commit()

        return {
            "message": "Application submitted successfully!",
            "application_id": application_id,
            "status": "Submitted",
            "resume_uploaded": new_resume is not None,
            "resume_text_characters": len(resume_text),
            "match_score": match["score"],
        }

    except Exception as error:
        connection.rollback()

        if saved_path and saved_path.exists():
            saved_path.unlink()

        if isinstance(error, sqlite3.IntegrityError):
            raise HTTPException(409, "You have already applied to this project.")

        raise

    finally:
        connection.close()


# ==========================================
# EMPLOYEE APPLICATION TRACKING
# ==========================================

@router.get("/my-applications")
def get_my_applications(email: str):
    email = validate_email(email)

    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT
                applications.id AS application_id,
                projects.title AS project_title,
                projects.client_project AS client_project,
                projects.location AS location,
                applications.application_status AS status,
                applications.submitted_at AS submitted_at,
                applications.updated_at AS updated_at
            FROM applications
            JOIN employees ON applications.employee_id = employees.id
            JOIN projects ON applications.project_id = projects.id
            WHERE LOWER(employees.email) = ?
            ORDER BY applications.submitted_at DESC
        """, (email,)).fetchall()
    finally:
        connection.close()

    return {
        "email": email,
        "total_applications": len(rows),
        "applications": [dict(row) for row in rows],
    }


# ==========================================
# INDIVIDUAL APPLICATIONS
# ==========================================

@router.get("/{application_id}")
def get_application(application_id: int):
    connection = get_connection()

    try:
        application = connection.execute("""
            SELECT
                applications.*,
                employees.name,
                employees.email,
                projects.title,
                projects.role_id
            FROM applications
            JOIN employees ON applications.employee_id = employees.id
            JOIN projects ON applications.project_id = projects.id
            WHERE applications.id = ?
        """, (application_id,)).fetchone()
    finally:
        connection.close()

    if application is None:
        raise HTTPException(404, "Application not found.")

    return dict(application)


@router.patch("/{application_id}/status")
def update_application_status(application_id: int, update: ApplicationStatusUpdate):
    new_status = update.status.strip()

    if new_status not in ALLOWED_STATUSES:
        raise HTTPException(400, "Invalid application status.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE applications
            SET application_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_status, application_id),
        )

        if cursor.rowcount == 0:
            raise HTTPException(404, "Application not found.")

        connection.commit()
    finally:
        connection.close()

    return {
        "message": "Application status updated.",
        "application_id": application_id,
        "status": new_status,
    }
