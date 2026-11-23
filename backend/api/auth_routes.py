from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from backend import config
from backend.api.deps import get_db
from backend.auth import issue_dev_token
from backend.users import ensure_dev_user, to_user

router = APIRouter()

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


class DevLoginRequest(BaseModel):
    email: EmailStr
    display_name: str = Field("", max_length=100)


@router.get("/config")
def auth_config(connection=Depends(get_db)):
    """What the frontend needs to know to sign the user in."""
    result = {"mode": config.auth_mode(), "pm_self_service": config.pm_self_service()}

    if config.auth_mode() == "dev":
        rows = connection.execute(
            "SELECT email, display_name, role FROM users WHERE auth_provider = 'dev' "
            "ORDER BY CASE role WHEN 'employee' THEN 0 WHEN 'pm' THEN 1 ELSE 2 END, id"
        ).fetchall()
        result["dev_users"] = [dict(row) for row in rows]

    return result


@router.post("/dev-login")
def dev_login(body: DevLoginRequest, request: Request, connection=Depends(get_db)):
    """Sign in as a test user (created on first use). Dev mode only, and by
    default only from this computer."""
    if config.auth_mode() != "dev":
        raise HTTPException(404, "Not found")

    client_host = request.client.host if request.client else ""
    if client_host not in LOCAL_HOSTS and not config.dev_login_any_host():
        raise HTTPException(403, "Dev sign-in is only allowed from this computer.")

    email = str(body.email).lower()
    existing = connection.execute(
        "SELECT display_name FROM users WHERE auth_provider = 'dev' AND external_id = ?", (email,)
    ).fetchone()
    # Keep an existing user's name unless a new one is given.
    name = (
        body.display_name.strip()
        or (existing["display_name"] if existing else "")
        or email.split("@")[0]
    )

    row = ensure_dev_user(connection, email, name, "employee")
    user = to_user(row)

    return {
        "token": issue_dev_token(user.id),
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name,
                 "role": user.role},
    }
