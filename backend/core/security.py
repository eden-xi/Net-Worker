"""
Who is signed in, and what they may do.

How a login works:
  1. The login wall sends POST /api/auth/login with email, password and the role clicked.
  2. check_credentials() decides if that person may enter as that role.
  3. start_session() makes a random token, remembers it in SESSIONS, and the route puts
     it in an HttpOnly cookie (page JavaScript can't read it).
  4. Every later request carries the cookie; get_session_user() turns it back into a User.

check_credentials() is the ONE function to replace for real company logins (SSO).
"""

import re
import secrets
import time

from backend.core import config
from backend.schemas.users import Role, User

# ------------------------------------------
# 1. Test accounts (safe to share with the team; not real people)
# ------------------------------------------

TEST_ACCOUNTS = [
    {"email": "employee@networker.test", "password": "employee-demo", "name": "Erin Employee", "role": "employee"},
    {"email": "employee2@networker.test", "password": "employee-demo", "name": "Eli Engineer", "role": "employee"},
    {"email": "manager@networker.test", "password": "manager-demo", "name": "Morgan Manager", "role": "manager"},
    {"email": "admin@networker.test", "password": "manager-demo", "name": "Avery Admin", "role": "manager"},
]

# token -> {"user": User, "expires_at": seconds}
# Kept in memory: every session ends when the server restarts.
SESSIONS = {}


def check_credentials(email, password, role):
    """Return a User if this person may sign in as this role, otherwise None."""
    if config.LOGIN_MODE == "open":
        if not password:
            return None
        name = email.split("@")[0].replace(".", " ").title()
        return User(email=email, name=name, role=role)

    for account in TEST_ACCOUNTS:
        same_email = account["email"] == email
        same_password = secrets.compare_digest(account["password"].encode(), password.encode())
        if same_email and same_password and account["role"] == role:
            return User(email=account["email"], name=account["name"], role=account["role"])

    return None


# ------------------------------------------
# 2. Sessions
# ------------------------------------------

def start_session(user):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"user": user, "expires_at": time.time() + config.SESSION_HOURS * 3600}
    return token


def end_session(token):
    SESSIONS.pop(token or "", None)


def get_session_user(request):
    """The signed-in User for this request, or None."""
    token = request.cookies.get(config.COOKIE_NAME, "")
    session = SESSIONS.get(token)

    if session is None:
        return None

    if session["expires_at"] < time.time():
        end_session(token)
        return None

    return session["user"]


# ------------------------------------------
# 3. Who may call what: a rule table checked by deploy/server.py on every request
#    (Move 3 replaces this with FastAPI dependencies on each route.)
# ------------------------------------------

# Paths anyone may call without signing in (otherwise nobody could see the login wall).
PUBLIC_API_PATHS = ["/api/auth/", "/api/health"]

# (HTTP method, path pattern) pairs only a manager may call.
MANAGER_ONLY = [
    ("GET", r"^/api/projects/manage$"),
    ("POST", r"^/api/projects$"),
    ("POST", r"^/api/projects/upload-csv$"),
    ("PATCH", r"^/api/projects/\d+/status$"),
    ("GET", r"^/api/projects/\d+/applications$"),
    ("GET", r"^/api/applications/\d+/(document|attachment)$"),
    ("PATCH", r"^/api/applications/\d+/status$"),
]


def access_problem(method, path, query_email, user):
    """Return (status_code, message) if the request must be refused, or None if it may continue."""
    if not path.startswith("/api/") or any(path.startswith(public) for public in PUBLIC_API_PATHS):
        return None

    if user is None:
        return 401, "Please log in first."

    for rule_method, pattern in MANAGER_ONLY:
        if rule_method == method and re.match(pattern, path):
            if user.role != Role.MANAGER:
                return 403, "This area is for project managers only."

    # Employees may only look up their OWN applications.
    if path == "/api/applications/mine" and user.role == Role.EMPLOYEE:
        if (query_email or "").strip().lower() != user.email:
            return 403, "You can only view your own applications."

    return None
