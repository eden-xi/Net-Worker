"""
Net-Worker deploy wrapper.

Runs the group's existing ProjectHub app WITHOUT changing it, and adds:
  1. Serves the frontend and the API from one address (API lives at /api).
  2. Keeps the database and resumes in DATA_DIR, away from the files in git.
  3. Asks for a shared test password on every page.
  4. Loads fake demo projects whenever the database is empty.

Run locally:   uvicorn deploy.server:app --reload
"""

import base64
import io
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

# ------------------------------------------
# 1. Settings (read from environment variables)
# ------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEMO_CSV = ROOT / "deploy" / "demo_projects.csv"

DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "deploy" / ".localdata")))
RESUME_DIR = DATA_DIR / "resumes"
RESUME_DIR.mkdir(parents=True, exist_ok=True)

USERNAME = os.getenv("APP_USERNAME", "team")
PASSWORD = os.getenv("APP_PASSWORD", "")

if not PASSWORD and os.getenv("ALLOW_NO_AUTH") != "1":
    raise RuntimeError(
        "APP_PASSWORD is not set. Set it, or set ALLOW_NO_AUTH=1 for local testing."
    )

# ------------------------------------------
# 2. Load the existing app and point it at DATA_DIR
# ------------------------------------------

from backend.api.main import app as projecthub_api, create_tables, upload_projects_csv
import backend.api.application_routes as application_routes
import backend.api.resume_routes as resume_routes
import backend.database.database as database_module

# main.py imports the database file a second way ("import database"),
# so Python holds two copies of it. Both need the new path.
database_copies = [database_module, sys.modules["database"]]

for module in database_copies:
    module.DATABASE_PATH = DATA_DIR / "projecthub.db"

for module in [resume_routes, application_routes]:
    module.RESUME_FOLDER = RESUME_DIR

# ------------------------------------------
# 3. Demo data
# ------------------------------------------

async def load_demo_projects():
    connection = database_module.get_connection()
    project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    connection.close()

    if project_count > 0:
        return

    # Reuse the app's own CSV importer, so the import rules stay in one place.
    demo_file = UploadFile(file=io.BytesIO(DEMO_CSV.read_bytes()), filename="demo.csv")
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
# 4. Password gate
# ------------------------------------------

def password_is_correct(auth_header):
    if not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
    except Exception:
        return False

    user, _, password = decoded.partition(":")
    user_ok = secrets.compare_digest(user.encode(), USERNAME.encode())
    password_ok = secrets.compare_digest(password.encode(), PASSWORD.encode())
    return user_ok and password_ok


@app.middleware("http")
async def require_password(request: Request, call_next):
    no_password_needed = not PASSWORD or request.url.path == "/healthz"

    if no_password_needed or password_is_correct(request.headers.get("authorization", "")):
        return await call_next(request)

    return PlainTextResponse(
        "Password required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Net-Worker test site"'},
    )

# ------------------------------------------
# 5. Routes
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
