"""
Net-Worker server: the one process that runs on Render.

  1. Serves the frontend (frontend/) and the API (backend/app.py, at /api) from one address.
  2. Asks for a shared team password on every page (the browser pop-up).
  3. On startup: builds the database tables and loads demo projects if it is empty.

Who may call which API route is NOT decided here: each route declares it with
Depends(current_user / require_manager / require_employee). See backend/core/security.py.

All settings (data folder, passwords, login mode) come from backend/core/config.py.

Run locally:   $env:ALLOW_NO_AUTH="1"; uvicorn deploy.server:app --reload
"""

import base64
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.app import api
from backend.core import config
from backend.core.db import connect, create_tables, data_since
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
    print(f"Data folder: {config.DATA_DIR} (kept since {data_since()})")
    yield


app = FastAPI(title="Net-Worker", lifespan=lifespan)

# ------------------------------------------
# 2. Middleware: the team password, and (only if configured) other sites allowed to call us
# ------------------------------------------

# The page and the API share one address, so browsers need no CORS permission at all.
# Only list extra sites in ALLOWED_ORIGINS if one really needs to call the API.
if config.ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])


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
