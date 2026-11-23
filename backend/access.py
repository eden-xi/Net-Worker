"""Project ownership checks. Every PM endpoint loads projects and applications
through these functions, so a user can only ever reach projects they own or
co-manage.

Projects the user does not manage get 404 rather than 403, so trying other IDs
does not reveal which projects exist.
"""

from fastapi import HTTPException

NOT_FOUND = "Project not found."


def get_managed_project(connection, project_id, user, owner_only=False):
    """The project as a dict with the user's manager role ('owner' or
    'co_manager') in `my_role`. Raises 404 if they do not manage it."""
    row = connection.execute(
        """
        SELECT projects.*, project_managers.role AS my_role
        FROM projects
        JOIN project_managers
            ON project_managers.project_id = projects.id
            AND project_managers.user_id = ?
        WHERE projects.id = ?
        """,
        (user.id, project_id),
    ).fetchone()

    if row is None:
        raise HTTPException(404, NOT_FOUND)

    if owner_only and row["my_role"] != "owner":
        raise HTTPException(403, "Only the project owner can do this.")

    return dict(row)


def get_managed_application(connection, application_id, user):
    """An application to a project the user manages. Raises 404 otherwise."""
    row = connection.execute(
        """
        SELECT applications.*
        FROM applications
        JOIN project_managers
            ON project_managers.project_id = applications.project_id
            AND project_managers.user_id = ?
        WHERE applications.id = ?
        """,
        (user.id, application_id),
    ).fetchone()

    if row is None:
        raise HTTPException(404, "Application not found.")

    return dict(row)


def managed_project_count(connection, user):
    return connection.execute(
        "SELECT COUNT(*) FROM project_managers WHERE user_id = ?", (user.id,)
    ).fetchone()[0]
