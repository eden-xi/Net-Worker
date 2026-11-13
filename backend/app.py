"""
The Net-Worker API: one FastAPI app that collects every router.

deploy/server.py mounts this at /api, so routes here are written without "/api".
Errors raised by services (backend/core/errors.py) become JSON responses in ONE place below.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.errors import AppError
from backend.routes import applications, auth, projects

api = FastAPI(title="Net-Worker API")

api.include_router(auth.router)
api.include_router(projects.router)
api.include_router(applications.router)


@api.exception_handler(AppError)
def app_error(request: Request, error: AppError):
    # NotFound -> 404, Conflict -> 409, Invalid -> 400, TooLarge -> 413
    return JSONResponse({"detail": error.message}, status_code=error.status_code)


@api.get("/health")
def health():
    return {"status": "healthy"}
