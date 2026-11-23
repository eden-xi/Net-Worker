import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.application_routes import router as application_router
from backend.api.match_routes import router as match_router
from backend.api.project_routes import router as project_router
from backend.api.resume_routes import router as resume_router
from backend.database.database import PROJECT_ROOT, create_tables, seed_sample_projects

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Browsers may call the API from these pages. The frontend served by this
# app (http://127.0.0.1:8000) is same-origin and needs no entry here.
# Override with a comma-separated list in NETWORKER_CORS_ORIGINS.
DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://eden-xi.github.io",
]


def cors_origins():
    configured = os.environ.get("NETWORKER_CORS_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(app):
    create_tables()

    if os.environ.get("NETWORKER_SEED_SAMPLES", "1") != "0":
        added = seed_sample_projects()
        if added:
            print(f"Added {added} sample roles to the empty database.")

    yield


app = FastAPI(title="ProjectHub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "healthy"}


app.include_router(project_router, prefix="/projects", tags=["Projects"])
app.include_router(application_router, prefix="/applications", tags=["Applications"])
app.include_router(resume_router, prefix="/resumes", tags=["Resumes"])
app.include_router(match_router, prefix="/matches", tags=["Matching"])

# Serve the website from the same server, so http://127.0.0.1:8000 opens it.
# Mounted last so the API routes above take priority.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
