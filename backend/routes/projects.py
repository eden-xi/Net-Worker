"""
Listing endpoints, served under /api/projects.

Every route reads the same way:  take validated input -> call a service -> return a schema.
No SQL here; it all lives in backend/services/.

All routes are plain `def` (not `async def`): they do blocking work (SQLite, files), so
FastAPI runs each one in a worker thread and the server keeps answering other requests.
"""

from fastapi import APIRouter, Depends, File, Request, UploadFile

from backend.core import security
from backend.core.db import get_db
from backend.schemas.applications import Applicant
from backend.schemas.projects import (CsvImportResult, ManagedProjectOut, ProjectIn, ProjectOut,
                                      ProjectStatusChange)
from backend.services import applications, projects

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectOut])
def open_listings(db=Depends(get_db)):
    """The shared feed both roles see."""
    return projects.list_open(db)


@router.get("/manage", response_model=list[ManagedProjectOut])
def all_listings(db=Depends(get_db)):
    """Manager: every listing in any status, with applicant counts."""
    return projects.list_for_managers(db)


@router.post("", response_model=ProjectOut, status_code=201)
def create_listing(listing: ProjectIn, request: Request, db=Depends(get_db)):
    manager = security.get_session_user(request)
    return projects.create(db, listing, manager.email, manager.name)


@router.post("/upload-csv", response_model=CsvImportResult)
def upload_csv(file: UploadFile = File(...), db=Depends(get_db)):
    return projects.import_csv(db, file.file.read())


@router.get("/{project_id}", response_model=ProjectOut)
def one_listing(project_id: int, db=Depends(get_db)):
    return projects.get(db, project_id)


@router.patch("/{project_id}/status", response_model=ProjectOut)
def change_status(project_id: int, change: ProjectStatusChange, db=Depends(get_db)):
    return projects.set_status(db, project_id, change.status)


@router.get("/{project_id}/applications", response_model=list[Applicant])
def applicants(project_id: int, db=Depends(get_db)):
    return applications.list_for_project(db, project_id)
