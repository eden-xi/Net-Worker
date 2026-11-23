"""Applying to projects. The applicant is always the signed-in user."""

import json
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.api.deps import get_db
from backend.auth import get_current_user
from backend.matching import Candidate, score_project
from backend.resumes import delete_resume_if_unused, read_resume, resume_path, save_resume
from backend.users import get_user_row

router = APIRouter()


@router.post("")
async def submit_application(
    project_id: int = Form(...),
    cover_letter: str = Form("", max_length=5000),
    resume: UploadFile | None = File(None),
    user=Depends(get_current_user),
    connection=Depends(get_db),
):
    """Apply to an open project with the skills on your profile.

    A resume uploaded here also becomes your profile resume. Without one,
    your current profile resume is attached.
    """
    new_resume = await read_resume(resume) if resume and resume.filename else None

    project = connection.execute(
        "SELECT * FROM projects WHERE id = ? AND LOWER(TRIM(status)) = 'open'", (project_id,)
    ).fetchone()

    if project is None:
        raise HTTPException(404, "This project is unavailable.")

    already_applied = connection.execute(
        "SELECT 1 FROM applications WHERE user_id = ? AND project_id = ?", (user.id, project_id)
    ).fetchone()

    if already_applied:
        raise HTTPException(409, "You have already applied to this project.")

    profile = get_user_row(connection, user.id)
    previous_resume = profile["resume_filename"]
    resume_filename = previous_resume if resume_path(previous_resume) else ""
    resume_text = profile["resume_text"] or ""

    if new_resume:
        contents, extension, resume_text = new_resume
        resume_filename = save_resume(contents, extension)

    try:
        if new_resume:
            connection.execute(
                """
                UPDATE users SET resume_filename = ?, resume_text = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (resume_filename, resume_text, user.id),
            )

        application_id = connection.execute(
            """
            INSERT INTO applications (user_id, project_id, application_status,
                resume_filename, cover_letter)
            VALUES (?, ?, 'Submitted', ?, ?)
            """,
            (user.id, project_id, resume_filename, cover_letter.strip()),
        ).lastrowid

        match = score_project(dict(project), Candidate(profile["skills"], resume_text))
        details = {key: value for key, value in match.items() if key != "score"}

        connection.execute(
            """
            INSERT INTO matches (user_id, project_id, match_score, matched_skills)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id, project_id) DO UPDATE SET
                match_score = excluded.match_score,
                matched_skills = excluded.matched_skills,
                created_at = CURRENT_TIMESTAMP
            """,
            (user.id, project_id, match["score"], json.dumps(details)),
        )

        connection.commit()

    except Exception as error:
        connection.rollback()

        if new_resume:
            path = resume_path(resume_filename)
            if path:
                path.unlink(missing_ok=True)

        if isinstance(error, sqlite3.IntegrityError):
            raise HTTPException(409, "You have already applied to this project.")
        raise

    if new_resume:
        delete_resume_if_unused(connection, previous_resume)

    return {
        "message": "Application submitted successfully!",
        "application_id": application_id,
        "status": "Submitted",
        "resume_attached": bool(resume_filename),
        "match_score": match["score"],
    }
