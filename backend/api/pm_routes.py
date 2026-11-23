"""Project manager portal.

Every route here reaches projects only through backend.access, so a PM sees
and changes only projects they own or co-manage. Creating projects needs the
PM role; managing an existing project needs only a manager entry for it (so a
co-manager added by an owner can help even without the PM role).
"""

import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field

from backend.access import get_managed_application, get_managed_project
from backend.api.deps import get_db
from backend.auth import get_current_user, require_pm
from backend.csv_import import map_csv_headers
from backend.database.database import APPLICATION_STATUSES, PROJECT_COLUMNS, PROJECT_STATUSES
from backend.matching import Candidate, score_project
from backend.resumes import MEDIA_TYPES, resume_path
from backend.users import avatar_version

router = APIRouter()

MAX_CSV_SIZE = 2 * 1024 * 1024

ProjectStatus = Literal["Open", "On Hold", "Filled", "Closed"]


class ProjectFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    client_project: str = Field("", max_length=200)
    required_skills: str = Field("", max_length=1000)
    nice_to_have_skills: str = Field("", max_length=1000)
    seniority: str = Field("", max_length=50)
    location: str = Field("", max_length=100)
    start_date: str = Field("", max_length=30)
    status: ProjectStatus = "Open"
    description: str = Field("", max_length=10000)
    openings: int = Field(1, ge=1, le=500)


class ProjectCreate(ProjectFields):
    role_id: str = Field(min_length=1, max_length=64)


class ProjectUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    client_project: str | None = Field(None, max_length=200)
    required_skills: str | None = Field(None, max_length=1000)
    nice_to_have_skills: str | None = Field(None, max_length=1000)
    seniority: str | None = Field(None, max_length=50)
    location: str | None = Field(None, max_length=100)
    start_date: str | None = Field(None, max_length=30)
    status: ProjectStatus | None = None
    description: str | None = Field(None, max_length=10000)
    openings: int | None = Field(None, ge=1, le=500)


class ManagerAdd(BaseModel):
    email: EmailStr


class StatusUpdate(BaseModel):
    status: str


def _strip(values):
    return {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}


def _project_response(connection, project_id, user):
    project = get_managed_project(connection, project_id, user)
    project["applicant_count"] = connection.execute(
        "SELECT COUNT(*) FROM applications WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    return project


# ==========================================
# PROJECTS
# ==========================================

@router.get("/projects")
def my_projects(user=Depends(get_current_user), connection=Depends(get_db)):
    """Only the projects this user owns or co-manages."""
    rows = connection.execute(
        """
        SELECT projects.*, project_managers.role AS my_role,
            (SELECT COUNT(*) FROM applications
             WHERE applications.project_id = projects.id) AS applicant_count,
            (SELECT COUNT(*) FROM applications
             WHERE applications.project_id = projects.id
             AND applications.application_status = 'New') AS new_applicant_count,
            (SELECT COUNT(*) FROM applications
             WHERE applications.project_id = projects.id
             AND applications.application_status = 'Accepted') AS accepted_count
        FROM projects
        JOIN project_managers
            ON project_managers.project_id = projects.id
            AND project_managers.user_id = ?
        ORDER BY
            CASE WHEN LOWER(TRIM(projects.status)) = 'open' THEN 0 ELSE 1 END,
            projects.created_at DESC, projects.id DESC
        """,
        (user.id,),
    ).fetchall()

    return [dict(row) for row in rows]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, user=Depends(require_pm), connection=Depends(get_db)):
    values = _strip(body.model_dump())

    if connection.execute("SELECT 1 FROM projects WHERE role_id = ?", (values["role_id"],)).fetchone():
        raise HTTPException(409, "That Role ID is already in use. Choose another.")

    project_id = connection.execute(
        f"""
        INSERT INTO projects ({", ".join(PROJECT_COLUMNS)}, openings, created_by, updated_at, closed_at)
        VALUES ({", ".join("?" for _ in PROJECT_COLUMNS)}, ?, ?, CURRENT_TIMESTAMP,
            CASE WHEN ? = 'Closed' THEN CURRENT_TIMESTAMP END)
        """,
        [values[column] for column in PROJECT_COLUMNS]
        + [values["openings"], user.id, values["status"]],
    ).lastrowid

    connection.execute(
        "INSERT INTO project_managers (project_id, user_id, role) VALUES (?, ?, 'owner')",
        (project_id, user.id),
    )
    connection.commit()

    return _project_response(connection, project_id, user)


@router.get("/projects/{project_id}")
def get_project(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    return _project_response(connection, project_id, user)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: int, body: ProjectUpdate,
    user=Depends(get_current_user), connection=Depends(get_db),
):
    get_managed_project(connection, project_id, user)

    changes = _strip(body.model_dump(exclude_unset=True, exclude_none=True))

    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        closed_at = ""
        if "status" in changes:
            closed_at = (
                ", closed_at = CASE WHEN ? = 'Closed' THEN COALESCE(closed_at, CURRENT_TIMESTAMP) END"
            )

        connection.execute(
            f"UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP{closed_at} WHERE id = ?",
            [*changes.values(), *([changes["status"]] if "status" in changes else []), project_id],
        )
        connection.commit()

    return _project_response(connection, project_id, user)


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    """Owner only: delete a project posted by mistake. Projects that have
    applicants can't be deleted (close them instead), so no one's application
    disappears."""
    get_managed_project(connection, project_id, user, owner_only=True)

    has_applicants = connection.execute(
        "SELECT 1 FROM applications WHERE project_id = ? LIMIT 1", (project_id,)
    ).fetchone()

    if has_applicants:
        raise HTTPException(
            409, "This project has applicants, so it can't be deleted. Close it instead."
        )

    connection.execute("DELETE FROM project_managers WHERE project_id = ?", (project_id,))
    connection.execute("DELETE FROM matches WHERE project_id = ?", (project_id,))
    connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    connection.commit()

    return {"deleted": project_id}


@router.post("/projects/{project_id}/close")
def close_project(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    return update_project(project_id, ProjectUpdate(status="Closed"), user, connection)


@router.post("/projects/{project_id}/reopen")
def reopen_project(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    return update_project(project_id, ProjectUpdate(status="Open"), user, connection)


# ==========================================
# CO-MANAGERS
# ==========================================

def _managers(connection, project_id):
    rows = connection.execute(
        """
        SELECT users.id AS user_id, users.email, users.display_name, project_managers.role,
            users.avatar_filename
        FROM project_managers
        JOIN users ON users.id = project_managers.user_id
        WHERE project_managers.project_id = ?
        ORDER BY CASE project_managers.role WHEN 'owner' THEN 0 ELSE 1 END, users.display_name
        """,
        (project_id,),
    ).fetchall()

    managers = []
    for row in rows:
        manager = dict(row)
        manager["avatar"] = avatar_version(manager.pop("avatar_filename"))
        managers.append(manager)
    return managers


@router.get("/projects/{project_id}/managers")
def list_managers(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    get_managed_project(connection, project_id, user)
    return _managers(connection, project_id)


@router.post("/projects/{project_id}/managers", status_code=201)
def add_manager(
    project_id: int, body: ManagerAdd,
    user=Depends(get_current_user), connection=Depends(get_db),
):
    """Owner only: give someone co-manager access. They must have signed in
    to ProjectHub at least once."""
    get_managed_project(connection, project_id, user, owner_only=True)

    target = connection.execute(
        "SELECT id FROM users WHERE LOWER(email) = ? ORDER BY id LIMIT 1",
        (str(body.email).lower(),),
    ).fetchone()

    if target is None:
        raise HTTPException(
            404, "No one with that email has signed in to ProjectHub yet. Ask them to open it once."
        )

    connection.execute(
        "INSERT OR IGNORE INTO project_managers (project_id, user_id, role) VALUES (?, ?, 'co_manager')",
        (project_id, target["id"]),
    )
    connection.commit()

    return _managers(connection, project_id)


@router.delete("/projects/{project_id}/managers/{user_id}")
def remove_manager(
    project_id: int, user_id: int,
    user=Depends(get_current_user), connection=Depends(get_db),
):
    """The owner can remove co-managers; a co-manager can remove themselves.
    The owner cannot be removed."""
    project = get_managed_project(connection, project_id, user)

    if user_id != user.id and project["my_role"] != "owner":
        raise HTTPException(403, "Only the project owner can remove other managers.")

    target = connection.execute(
        "SELECT role FROM project_managers WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()

    if target is None:
        raise HTTPException(404, "That person does not manage this project.")

    if target["role"] == "owner":
        raise HTTPException(400, "The project owner cannot be removed.")

    connection.execute(
        "DELETE FROM project_managers WHERE project_id = ? AND user_id = ?", (project_id, user_id)
    )
    connection.commit()

    return {"removed": user_id}


# ==========================================
# CSV IMPORT
# ==========================================

@router.post("/projects/upload-csv")
async def upload_projects_csv(
    file: UploadFile = File(...), user=Depends(require_pm), connection=Depends(get_db),
):
    """Add projects from a CSV, owned by you. A row whose Role ID matches a
    project you manage updates it; a Role ID used by anyone else is skipped."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")

    contents = await file.read(MAX_CSV_SIZE + 1)

    if not contents:
        raise HTTPException(400, "The uploaded CSV file is empty.")

    if len(contents) > MAX_CSV_SIZE:
        raise HTTPException(413, "CSV files must be 2 MB or smaller.")

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Please save your CSV file using UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(400, "The CSV file does not contain column headers.")

    mapping = map_csv_headers(reader.fieldnames)
    missing = [
        label for column, label in [("role_id", "Project ID / Role ID"), ("title", "Job Title / Position")]
        if column not in mapping
    ]
    if missing:
        raise HTTPException(400, "Could not recognize required columns: " + ", ".join(missing))

    columns = [column for column in PROJECT_COLUMNS if column in mapping]
    imported, updated, skipped, conflicts = 0, 0, 0, []

    for line_number, row in enumerate(reader, start=2):
        values = {column: (row.get(mapping[column]) or "").strip() for column in columns}

        if not values["role_id"] or not values["title"]:
            skipped += 1
            continue

        if "status" in values:
            status = next(
                (s for s in PROJECT_STATUSES if s.lower() == values["status"].lower()), None
            )
            values["status"] = status or "Open"

        openings = None
        if "openings" in mapping:
            raw = (row.get(mapping["openings"]) or "").strip()
            if raw.isdigit() and 1 <= int(raw) <= 500:
                openings = int(raw)

        existing = connection.execute(
            """
            SELECT projects.id, project_managers.user_id AS manager
            FROM projects
            LEFT JOIN project_managers
                ON project_managers.project_id = projects.id
                AND project_managers.user_id = ?
            WHERE projects.role_id = ?
            """,
            (user.id, values["role_id"]),
        ).fetchone()

        if existing is None:
            project_id = connection.execute(
                f"""
                INSERT INTO projects ({", ".join(columns)}, created_by, updated_at)
                VALUES ({", ".join("?" for _ in columns)}, ?, CURRENT_TIMESTAMP)
                """,
                [values[column] for column in columns] + [user.id],
            ).lastrowid
            connection.execute(
                "INSERT INTO project_managers (project_id, user_id, role) VALUES (?, ?, 'owner')",
                (project_id, user.id),
            )
            imported += 1

        elif existing["manager"] is None:
            # Someone else's project: never overwrite it.
            skipped += 1
            conflicts.append(line_number)

        else:
            changes = {column: values[column] for column in columns if column != "role_id"}
            connection.execute(
                f"""
                UPDATE projects SET {", ".join(f"{column} = ?" for column in changes)},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [*changes.values(), existing["id"]],
            )
            project_id = existing["id"]
            updated += 1

        if openings is not None:
            connection.execute("UPDATE projects SET openings = ? WHERE id = ?", (openings, project_id))

        # Keep closed_at in step with the status, as closing in the app does.
        connection.execute(
            """
            UPDATE projects SET closed_at = CASE
                WHEN status = 'Closed' THEN COALESCE(closed_at, CURRENT_TIMESTAMP) END
            WHERE id = ?
            """,
            (project_id,),
        )

    connection.commit()

    return {
        "message": "CSV upload completed.",
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "conflict_rows": conflicts,
    }


# ==========================================
# APPLICANTS
# ==========================================

@router.get("/projects/{project_id}/applications")
def project_applicants(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    """Applicants to a project you manage, best match first."""
    project = get_managed_project(connection, project_id, user)

    rows = connection.execute(
        """
        SELECT applications.id, applications.application_status, applications.cover_letter,
            applications.submitted_at, applications.updated_at, applications.resume_filename,
            users.id AS user_id, users.display_name AS name, users.email, users.skills,
            users.resume_text, users.avatar_filename,
            matches.match_score, matches.matched_skills
        FROM applications
        JOIN users ON users.id = applications.user_id
        LEFT JOIN matches
            ON matches.user_id = applications.user_id
            AND matches.project_id = applications.project_id
        WHERE applications.project_id = ?
        """,
        (project_id,),
    ).fetchall()

    applicants = []

    for row in rows:
        applicant = dict(row)
        resume_text = applicant.pop("resume_text") or ""
        stored_score = applicant.pop("match_score")
        stored_details = applicant.pop("matched_skills")

        if stored_score is None:
            match = score_project(project, Candidate(applicant["skills"], resume_text))
        else:
            match = {**json.loads(stored_details or "{}"), "score": round(stored_score)}

        applicant["match"] = match
        applicant["has_resume"] = resume_path(applicant.pop("resume_filename")) is not None
        applicant["avatar"] = avatar_version(applicant.pop("avatar_filename"))
        applicants.append(applicant)

    applicants.sort(
        key=lambda a: (a["match"].get("score", 0), a["submitted_at"] or ""), reverse=True
    )
    return applicants


@router.patch("/applications/{application_id}/status")
def update_application_status(
    application_id: int, body: StatusUpdate,
    user=Depends(get_current_user), connection=Depends(get_db),
):
    get_managed_application(connection, application_id, user)

    status = body.status.strip()
    if status not in APPLICATION_STATUSES:
        raise HTTPException(400, "Invalid application status.")

    connection.execute(
        "UPDATE applications SET application_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, application_id),
    )
    connection.commit()

    return {"application_id": application_id, "status": status}


@router.get("/applications/{application_id}/resume")
def download_resume(application_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    """The resume attached to an application to a project you manage."""
    application = get_managed_application(connection, application_id, user)
    path = resume_path(application["resume_filename"])

    if path is None:
        raise HTTPException(404, "No resume is attached to this application.")

    return FileResponse(
        path,
        media_type=MEDIA_TYPES[path.suffix],
        filename=f"resume-application-{application_id}{path.suffix}",
    )
