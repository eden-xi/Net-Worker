from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import config
from backend.api.admin_routes import router as admin_router
from backend.api.application_routes import router as application_router
from backend.api.auth_routes import router as auth_router
from backend.api.me_routes import router as me_router
from backend.api.pm_routes import router as pm_router
from backend.api.project_routes import router as project_router
from backend.api.user_routes import router as user_router
from backend.database.database import (
    PROJECT_ROOT, create_tables, seed_dev_users, seed_sample_projects,
)

FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app):
    config.validate()
    create_tables()

    if config.auth_mode() == "dev":
        seed_dev_users()
        print(
            "WARNING: AUTH_MODE=dev. Anyone using this computer can sign in as any "
            "user. Use AUTH_MODE=entra for real deployments."
        )

    if config.seed_samples():
        added = seed_sample_projects()
        if added:
            print(f"Added {added} sample roles to the empty database.")

    yield


app = FastAPI(title="ProjectHub API", lifespan=lifespan)


def content_security_policy():
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        # blob: shows profile pictures fetched with the sign-in token.
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        # Who may show this app in a frame: itself, Teams and Microsoft 365.
        "frame-ancestors " + " ".join(config.frame_ancestors()),
    ])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    # No X-Frame-Options: it cannot allow-list Teams, and frame-ancestors in
    # the CSP supersedes it in every browser Teams supports.
    if request.url.path in ("/docs", "/redoc"):
        # FastAPI's API docs pages load scripts from a CDN; keep them
        # working but never embeddable.
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    else:
        response.headers["Content-Security-Policy"] = content_security_policy()
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    private_api = request.url.path.startswith(("/me", "/pm", "/admin", "/applications", "/auth"))
    if private_api and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "healthy"}


app.include_router(auth_router, prefix="/auth", tags=["Sign-in"])
app.include_router(me_router, prefix="/me", tags=["My profile"])
app.include_router(project_router, prefix="/projects", tags=["Projects"])
app.include_router(application_router, prefix="/applications", tags=["Applications"])
app.include_router(pm_router, prefix="/pm", tags=["Project managers"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(user_router, prefix="/users", tags=["Users"])

# Serve the website from the same server, so http://127.0.0.1:8000 opens it.
# Mounted last so the API routes above take priority.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
