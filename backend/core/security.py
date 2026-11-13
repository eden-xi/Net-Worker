"""
Who is signed in, and what they may do.

How a login works:
  1. The login wall sends POST /api/auth/login with email, password and the role clicked.
  2. check_credentials() decides if that person may enter as that role.
  3. start_session() makes a random token, remembers it in SESSIONS, and the route puts
     it in an HttpOnly cookie (page JavaScript can't read it).
  4. Every later request carries the cookie; get_session_user() turns it back into a User.

Who may do what is decided by three FastAPI dependencies (section 3), written on the
routes themselves. A route that needs a manager SAYS so:  Depends(require_manager).

check_credentials() is the ONE function to replace for real company logins (SSO).
"""

import secrets
import time

from fastapi import Depends, Request

from backend.core import config
from backend.core.errors import Forbidden, NotSignedIn
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
# 3. Who may call what: FastAPI dependencies
#
#    def my_route(user: User = Depends(current_user))      any signed-in person
#    def my_route(user: User = Depends(require_manager))   managers only
#    def my_route(user: User = Depends(require_employee))  employees only
#
#    FastAPI runs the dependency BEFORE the route. If it raises, the route never runs.
#    backend/app.py also puts current_user on whole routers, so a new route is
#    protected even if its author forgets (default deny).
# ------------------------------------------

def current_user(request: Request) -> User:
    user = get_session_user(request)
    if user is None:
        raise NotSignedIn("Please log in first.")
    return user


def require_manager(user: User = Depends(current_user)) -> User:
    if user.role != Role.MANAGER:
        raise Forbidden("This area is for project managers only.")
    return user


def require_employee(user: User = Depends(current_user)) -> User:
    if user.role != Role.EMPLOYEE:
        raise Forbidden("Only employees can do this.")
    return user
