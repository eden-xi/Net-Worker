"""
Net-Worker Marketplace server: the login wall + two role dashboards.

Builds on deploy/server.py WITHOUT changing it. Importing that file already:
  - points the database and resume folder at DATA_DIR,
  - defines the team password gate and the startup routine (tables + demo projects).

This file adds:
  - /mp/auth/*     login, logout, "who am I"            (marketplace/auth.py)
  - /mp/manager/*  manager-only listing tools + viewer  (marketplace/manager_routes.py)
  - a login check on /api/* and /mp/manager/* using the rule table in auth.py
  - the new frontend (marketplace/frontend/) at /

Run locally from the repo root:
  $env:ALLOW_NO_AUTH="1"; uvicorn marketplace.server:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import deploy.server as base          # existing wrapper: data paths, password gate, startup
from marketplace.auth import access_problem, get_session_user, router as auth_router
from marketplace.manager_routes import router as manager_router

FRONTEND = Path(__file__).resolve().parent / "frontend"

app = FastAPI(title="Net-Worker Marketplace", lifespan=base.lifespan)


# ------------------------------------------
# Middleware. The one added LAST runs FIRST, so the order on a request is:
#   1. team password (base.require_password)  ->  2. marketplace login + role check
# ------------------------------------------

@app.middleware("http")
async def require_login(request: Request, call_next):
    user = get_session_user(request)
    problem = access_problem(request.method, request.url.path, request.query_params.get("email"), user)

    if problem:
        status_code, message = problem
        return JSONResponse({"detail": message}, status_code=status_code)

    return await call_next(request)


app.middleware("http")(base.require_password)


# ------------------------------------------
# Routes. Order matters: specific paths first, the static frontend last.
# ------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.include_router(auth_router, prefix="/mp/auth", tags=["Marketplace auth"])
app.include_router(manager_router, prefix="/mp/manager", tags=["Marketplace manager"])
app.mount("/api", base.projecthub_api)                     # the team's backend, unchanged
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="marketplace")
