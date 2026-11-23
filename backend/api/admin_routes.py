"""User role management. Admins can grant or remove project manager access;
they get no extra access to other people's projects or applicants."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.auth import require_admin
from backend.users import avatar_version

router = APIRouter()


class RoleUpdate(BaseModel):
    role: Literal["employee", "pm", "admin"]


@router.get("/users")
def list_users(user=Depends(require_admin), connection=Depends(get_db)):
    rows = connection.execute("""
        SELECT users.id, users.email, users.display_name, users.role, users.auth_provider,
            users.created_at, users.avatar_filename,
            (SELECT COUNT(*) FROM project_managers
             WHERE project_managers.user_id = users.id) AS managed_projects
        FROM users
        ORDER BY users.display_name COLLATE NOCASE
    """).fetchall()

    users = []
    for row in rows:
        item = dict(row)
        item["avatar"] = avatar_version(item.pop("avatar_filename"))
        users.append(item)
    return users


@router.patch("/users/{user_id}/role")
def set_role(user_id: int, body: RoleUpdate, user=Depends(require_admin), connection=Depends(get_db)):
    """Change a user's role. Their projects and co-managers are unaffected."""
    if user_id == user.id:
        raise HTTPException(400, "You cannot change your own role.")

    cursor = connection.execute(
        "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (body.role, user_id),
    )

    if cursor.rowcount == 0:
        raise HTTPException(404, "User not found.")

    connection.commit()
    return {"id": user_id, "role": body.role}
