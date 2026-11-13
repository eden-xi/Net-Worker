"""
Net-Worker server: the one process that runs on Render.

  1. Serves the frontend (frontend/) and the API (backend/app.py, at /api) from one address.
  2. Asks for a shared team password on every page (the browser pop-up).
  3. Checks the login + role rules on every /api request.
  4. On startup: builds the database tables and loads demo projects if it is empty.

All settings (data folder, passwords, login mode) come from backend/core/config.py.

Run locally:   $env:ALLOW_NO_AUTH="1"; uvicorn deploy.server:app --reload
"""

import base64
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.app import api
from backend.core import config, security
from backend.core.db import connect, create_tables
from backend.services import projects

FRONTEND = config.ROOT / "frontend"

if not config.TEAM_PASSWORD and not config.ALLOW_NO_PASSWORD:
    raise RuntimeError("APP_PASSWORD is not set. Set it, or set ALLOW_NO_AUTH=1 for local testing.")

# ------------------------------------------
# 1. Startup: tables + demo data
# ------------------------------------------

def load_demo_projects():
    connection = connect()
    try:
        if connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            result = projects.import_csv(connection, config.DEMO_CSV.read_bytes())
            print(f"Demo projects loaded: {result['imported']}")
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(app):
    create_tables()
    load_demo_projects()
    yield


app = FastAPI(title="Net-Worker", lifespan=lifespan)

# ------------------------------------------
# 2. Middleware. The one added LAST runs FIRST, so on each request:
#      team password  ->  login + role rules  ->  the route
# ------------------------------------------

@app.middleware("http")
async def require_login(request: Request, call_next):
    user = security.get_session_user(request)
    problem = security.access_problem(request.method, request.url.path, request.query_params.get("email"), user)

    if problem:
        status_code, message = problem
        return JSONResponse({"detail": message}, status_code=status_code)

    return await call_next(request)


def team_password_is_correct(auth_header):
    if not auth_header.startswith("Basic "):
        return False
    try:
        user, _, password = base64.b64decode(auth_header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    user_ok = secrets.compare_digest(user.encode(), config.TEAM_USERNAME.encode())
    password_ok = secrets.compare_digest(password.encode(), config.TEAM_PASSWORD.encode())
    return user_ok and password_ok


@app.middleware("http")
async def require_team_password(request: Request, call_next):
    no_password_needed = not config.TEAM_PASSWORD or request.url.path == "/healthz"

    if no_password_needed or team_password_is_correct(request.headers.get("authorization", "")):
        return await call_next(request)

    return PlainTextResponse("Password required", status_code=401,
                             headers={"WWW-Authenticate": 'Basic realm="Net-Worker test site"'})

# ------------------------------------------
# 3. Routes. Order matters: /healthz, then /api, then the frontend catches everything else.
# ------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.mount("/api", api)
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
