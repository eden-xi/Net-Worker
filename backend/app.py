"""
The Net-Worker API: one FastAPI app that collects every router.

deploy/server.py mounts this at /api, so routes here are written without "/api".

Security is DEFAULT DENY: every router except auth is included with
Depends(current_user), so a route added later is protected even if its author forgets.
Errors raised by services (backend/core/errors.py) become JSON responses in ONE place below.
"""

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.db import data_since
from backend.core.errors import AppError
from backend.core.security import current_user
from backend.routes import applications, auth, insights, projects
from backend.schemas.insights import HealthOut

SERVER_STARTED = datetime.now(timezone.utc)

api = FastAPI(title="Net-Worker API")

signed_in = [Depends(current_user)]

api.include_router(auth.router)                                    # login must work without a session
api.include_router(projects.router, dependencies=signed_in)
api.include_router(applications.router, dependencies=signed_in)
api.include_router(insights.router, dependencies=signed_in)


@api.exception_handler(AppError)
def app_error(request: Request, error: AppError):
    # NotFound 404, Conflict 409, Invalid 400, TooLarge 413, NotSignedIn 401, Forbidden 403
    return JSONResponse({"detail": error.message}, status_code=error.status_code)


@api.get("/health", response_model=HealthOut)
def health():
    # If data_since is OLDER than server_started, the data survived a restart (persistent disk).
    # If they are about the same, this server started with an empty data folder.
    return {"status": "healthy", "server_started": SERVER_STARTED, "data_since": data_since()}
