
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from backend.api.resume_routes import (
    extract_pdf_text,
    extract_docx_text
)

from backend.core import config
from backend.core.db import connect as get_connection


router = APIRouter()


@router.post("/submit-with-resume")
async def submit_application_with_resume(
    project_id: int = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    skills: str = Form(""),
    cover_letter: str = Form(""),
    resume: UploadFile | None = File(None)
):
    name = name.strip()
    email = email.strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Please provide your name.")

    if "@" not in email:
        raise HTTPException(status_code=400, detail="Please provide a valid email.")

    connection = get_connection()
    saved_path = None

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id FROM projects
            WHERE id = ?
            AND LOWER(TRIM(status)) = 'open'
        """, (project_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="This project is unavailable."
            )

        cursor.execute(
            "SELECT * FROM employees WHERE email = ?",
            (email,)
        )

        employee = cursor.fetchone()
        employee_id = employee["id"] if employee else None

        if employee_id is not None:
            cursor.execute("""
                SELECT id FROM applications
                WHERE employee_id = ? AND project_id = ?
            """, (employee_id, project_id))

            if cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="You have already applied to this project."
                )

        resume_filename = employee["resume_filename"] or "" if employee else ""
        resume_text = employee["resume_text"] or "" if employee else ""

        if resume is not None:
            original_filename = resume.filename or ""
            extension = Path(original_filename).suffix.lower()

            if extension not in [".pdf", ".docx"]:
                raise HTTPException(
                    status_code=400,
                    detail="Only PDF and DOCX resumes are accepted."
                )

            file_contents = await resume.read(config.MAX_RESUME_BYTES + 1)

            if not file_contents:
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded resume is empty."
                )

            if len(file_contents) > config.MAX_RESUME_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Resume must be 5 MB or smaller."
                )

            if extension == ".pdf":
                if not file_contents.startswith(b"%PDF-"):
                    raise HTTPException(
                        status_code=400,
                        detail="The uploaded file is not a valid PDF."
                    )

                resume_text = extract_pdf_text(file_contents)

            else:
                if not file_contents.startswith(b"PK"):
                    raise HTTPException(
                        status_code=400,
                        detail="The uploaded file is not a valid DOCX document."
                    )

                resume_text = extract_docx_text(file_contents)

            resume_filename = f"{uuid4().hex}{extension}"
            saved_path = config.RESUME_DIR / resume_filename
            saved_path.write_bytes(file_contents)

        if employee:
            cursor.execute("""
                UPDATE employees
                SET name = ?, skills = ?,
                    resume_filename = ?, resume_text = ?
                WHERE id = ?
            """, (
                name, skills, resume_filename,
                resume_text, employee_id
            ))

        else:
            cursor.execute("""
                INSERT INTO employees (
                    name, email, skills, resume_filename, resume_text
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                name, email, skills,
                resume_filename, resume_text
            ))

            employee_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO applications (
                employee_id, project_id,
                application_status, resume_filename, cover_letter
            )
            VALUES (?, ?, 'Submitted', ?, ?)
        """, (
            employee_id, project_id,
            resume_filename, cover_letter
        ))

        application_id = cursor.lastrowid
        connection.commit()

        return {
            "message": "Application submitted successfully!",
            "application_id": application_id,
            "status": "Submitted",
            "resume_uploaded": bool(resume_filename),
            "resume_text_characters": len(resume_text)
        }

    except sqlite3.IntegrityError:
        connection.rollback()

        if saved_path and saved_path.exists():
            saved_path.unlink()

        raise HTTPException(
            status_code=409,
            detail="You have already applied to this project."
        )

    except Exception:
        connection.rollback()

        if saved_path and saved_path.exists():
            saved_path.unlink()

        raise

    finally:
        connection.close()


# ==========================================
# EMPLOYEE APPLICATION TRACKING
# ==========================================

@router.get("/my-applications")
def get_my_applications(email: str):
    email = email.strip().lower()

    if "@" not in email:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid email address."
        )

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                applications.id AS application_id,
                projects.title AS project_title,
                projects.client_project AS client_project,
                projects.location AS location,
                applications.application_status AS status,
                applications.submitted_at AS submitted_at,
                applications.updated_at AS updated_at

            FROM applications

            JOIN employees
                ON applications.employee_id = employees.id

            JOIN projects
                ON applications.project_id = projects.id

            WHERE LOWER(employees.email) = ?

            ORDER BY applications.submitted_at DESC
        """, (email,))

        applications = cursor.fetchall()

        return {
            "email": email,
            "total_applications": len(applications),
            "applications": [
                dict(application)
                for application in applications
            ]
        }

    finally:
        connection.close()
