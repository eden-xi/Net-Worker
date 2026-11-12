"""
Marketplace login + sessions.

Two roles:  "employee" (seeking projects)  and  "manager" (posting projects / admin view).

How a login works:
  1. The login wall sends  POST /mp/auth/login  with email, password and the role button clicked.
  2. check_credentials() decides if that person may enter as that role.
  3. We create a random session token, remember it in SESSIONS, and give the
     browser a cookie holding the token (HttpOnly, so page JavaScript can't read it).
  4. Every later request carries the cookie. get_session_user() turns it back into a user.

LOGIN_MODE (environment variable MARKETPLACE_LOGIN_MODE):
  "test"  (default) - only the TEST_ACCOUNTS below can log in, and only as their own role.
  "open"            - anyone can log in with any email + non-empty password, as either role.
                      Use this for open demos. Later, real logins (e.g. Microsoft Entra ID / SSO)
                      replace check_credentials() and nothing else has to change.
"""

import os
import re
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter()

LOGIN_MODE = os.getenv("MARKETPLACE_LOGIN_MODE", "test")
COOKIE_NAME = "mp_session"
SESSION_HOURS = 8
ROLES = ["employee", "manager"]

# ------------------------------------------
# 1. Test accounts (safe to share with the team; not real people)
# ------------------------------------------

TEST_ACCOUNTS = [
    {"email": "employee@networker.test", "password": "employee-demo", "name": "Erin Employee", "role": "employee"},
    {"email": "employee2@networker.test", "password": "employee-demo", "name": "Eli Engineer", "role": "employee"},
    {"email": "manager@networker.test", "password": "manager-demo", "name": "Morgan Manager", "role": "manager"},
    {"email": "admin@networker.test", "password": "manager-demo", "name": "Avery Admin", "role": "manager"},
]

# token -> {"email", "name", "role", "expires_at"}
# Kept in memory: every session ends when the server restarts (same as the free-tier data).
SESSIONS = {}


def check_credentials(email, password, role):
    """Return the user dict if this person may log in as this role, otherwise None.

    This is the ONE function to change when moving from test logins to real logins.
    """
    if LOGIN_MODE == "open":
        if not password:
            return None
        name = email.split("@")[0].replace(".", " ").title()
        return {"email": email, "name": name, "role": role}

    for account in TEST_ACCOUNTS:
        same_email = account["email"] == email
        same_password = secrets.compare_digest(account["password"].encode(), password.encode())
        if same_email and same_password and account["role"] == role:
            return {"email": account["email"], "name": account["name"], "role": account["role"]}

    return None


# ------------------------------------------
# 2. Session helpers
# ------------------------------------------

def start_session(user):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {**user, "expires_at": time.time() + SESSION_HOURS * 3600}
    return token


def get_session_user(request):
    """Return the logged-in user for this request, or None."""
    token = request.cookies.get(COOKIE_NAME, "")
    session = SESSIONS.get(token)

    if session is None:
        return None

    if session["expires_at"] < time.time():
        SESSIONS.pop(token, None)
        return None

    return {"email": session["email"], "name": session["name"], "role": session["role"]}


# ------------------------------------------
# 3. Who may call what (one table, checked by marketplace/server.py on every request)
# ------------------------------------------

# Paths that need a login at all. Static page files and /mp/auth/* are always open,
# otherwise nobody could see the login wall.
LOGIN_REQUIRED_PREFIXES = ["/api/", "/mp/manager/"]

# (HTTP method, path pattern) pairs only a manager may call.
MANAGER_ONLY = [
    ("*", r"^/mp/manager/"),                          # everything in marketplace/manager_routes.py
    ("POST", r"^/api/projects/upload-csv$"),          # existing CSV import
    ("GET", r"^/api/projects/\d+/applications$"),     # existing "who applied?" list
    ("PATCH", r"^/api/applications/\d+/status$"),     # existing status change
    ("GET", r"^/api/applications/\d+$"),              # existing single-application lookup
    ("POST", r"^/api/resumes/upload$"),               # existing orphan upload, not used by employees
    ("POST", r"^/api/applications$"),                 # older JSON apply path; employees use submit-with-resume
]


def access_problem(method, path, query_email, user):
    """Return (status_code, message) if the request must be refused, or None if it may continue."""
    if not any(path.startswith(prefix) for prefix in LOGIN_REQUIRED_PREFIXES):
        return None

    if user is None:
        return 401, "Please log in first."

    for rule_method, pattern in MANAGER_ONLY:
        if rule_method in ("*", method) and re.match(pattern, path):
            if user["role"] != "manager":
                return 403, "This area is for project managers only."

    # Employees may only look up their OWN applications.
    if path == "/api/applications/my-applications" and user["role"] == "employee":
        if (query_email or "").strip().lower() != user["email"]:
            return 403, "You can only view your own applications."

    return None


# ------------------------------------------
# 4. Routes: /mp/auth/login, /mp/auth/me, /mp/auth/logout
# ------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str
    role: str


@router.post("/login")
def login(details: LoginRequest, request: Request, response: Response):
    email = details.email.strip().lower()

    if details.role not in ROLES:
        raise HTTPException(status_code=400, detail="Please choose Employee or Project Manager.")

    if "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    user = check_credentials(email, details.password, details.role)

    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email, password, or role for this account.")

    token = start_session(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,                                   # page JavaScript can't read it
        samesite="lax",                                  # other websites can't post with it
        secure=os.getenv("COOKIE_SECURE") == "1",        # set COOKIE_SECURE=1 on HTTPS hosts
    )
    return {"user": user, "login_mode": LOGIN_MODE}


@router.get("/me")
def me(request: Request):
    user = get_session_user(request)

    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in.")

    return {"user": user, "login_mode": LOGIN_MODE}


@router.get("/mode")
def mode():
    # Lets the login wall show the test-account hint only in test mode.
    return {"login_mode": LOGIN_MODE}


@router.post("/logout")
def logout(request: Request, response: Response):
    SESSIONS.pop(request.cookies.get(COOKIE_NAME, ""), None)
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out."}
