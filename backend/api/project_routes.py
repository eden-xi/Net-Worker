"""Browsing open projects. Managing projects lives in pm_routes."""

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_db
from backend.auth import get_current_user

router = APIRouter()

OPEN_PROJECTS_SQL = """
    SELECT projects.id, projects.role_id, projects.title, projects.client_project,
        projects.required_skills, projects.nice_to_have_skills, projects.seniority,
        projects.location, projects.start_date, projects.status, projects.description,
        projects.openings,
        projects.created_at,
        EXISTS (SELECT 1 FROM applications
                WHERE applications.project_id = projects.id
                AND applications.user_id = ?) AS applied
    FROM projects
    WHERE LOWER(TRIM(projects.status)) = 'open'
"""


@router.get("")
def list_open_projects(user=Depends(get_current_user), connection=Depends(get_db)):
    rows = connection.execute(
        OPEN_PROJECTS_SQL + " ORDER BY projects.created_at DESC, projects.id ASC", (user.id,)
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/{project_id}")
def get_open_project(project_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    row = connection.execute(
        OPEN_PROJECTS_SQL + " AND projects.id = ?", (user.id, project_id)
    ).fetchone()

    if row is None:
        raise HTTPException(404, "Project not found.")

    return dict(row)
