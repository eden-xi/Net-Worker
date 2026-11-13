"""
Net-Worker server: the one process that runs on Render.

  1. Serves the frontend and the API from one address (API lives at /api).
  2. Asks for a shared team password on every page.
  3. On startup: builds the database tables and loads demo projects if it is empty.

All settings (data folder, password) come from backend/core/config.py.

Run locally:   $env:ALLOW_NO_AUTH="1"; uvicorn deploy.server:app --reload
"""

import base64
import io
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.api.main import app as projecthub_api, upload_projects_csv
from backend.core import config
from backend.core.db import connect, create_tables

# ------------------------------------------
# 1. Settings
# ------------------------------------------

FRONTEND = config.ROOT / "frontend"

if not config.TEAM_PASSWORD and not config.ALLOW_NO_PASSWORD:
    raise RuntimeError(
        "APP_PASSWORD is not set. Set it, or set ALLOW_NO_AUTH=1 for local testing."
    )

# ------------------------------------------
# 2. Demo data
# ------------------------------------------

async def load_demo_projects():
    connection = connect()
    project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    connection.close()

    if project_count > 0:
        return

    # Reuse the app's own CSV importer, so the import rules stay in one place.
    demo_file = UploadFile(file=io.BytesIO(config.DEMO_CSV.read_bytes()), filename="demo.csv")
    result = await upload_projects_csv(demo_file)
    print(f"Demo projects loaded: {result['imported']}")


@asynccontextmanager
async def lifespan(app):
    # A mounted app's own startup code doesn't run, so we do it here.
    create_tables()
    await load_demo_projects()
    yield


app = FastAPI(title="Net-Worker", lifespan=lifespan)

# ------------------------------------------
# 3. Password gate
# ------------------------------------------

def password_is_correct(auth_header):
    if not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
    except Exception:
        return False

    user, _, password = decoded.partition(":")
    user_ok = secrets.compare_digest(user.encode(), config.TEAM_USERNAME.encode())
    password_ok = secrets.compare_digest(password.encode(), config.TEAM_PASSWORD.encode())
    return user_ok and password_ok


@app.middleware("http")
async def require_password(request: Request, call_next):
    no_password_needed = not config.TEAM_PASSWORD or request.url.path == "/healthz"

    if no_password_needed or password_is_correct(request.headers.get("authorization", "")):
        return await call_next(request)

    return PlainTextResponse(
        "Password required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Net-Worker test site"'},
    )

# ------------------------------------------
# 4. Routes
# ------------------------------------------

OLD_API_URL = "http://127.0.0.1:8000"


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/app.js")
def frontend_script():
    # Serve app.js with the API address swapped. The file on disk is untouched.
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    if OLD_API_URL not in script:
        print(f"WARNING: {OLD_API_URL} not found in app.js; the API address was not swapped.")

    return Response(script.replace(OLD_API_URL, "/api"), media_type="application/javascript")


# Order matters: /api first, then everything else goes to the frontend folder.
app.mount("/api", projecthub_api)
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
