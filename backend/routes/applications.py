"""
Application endpoints, served under /api/applications.

  POST  /api/applications                    apply (form + optional resume file)
  GET   /api/applications/mine               "My applications"
  GET   /api/applications/{id}/document      manager: viewer data (listing + applicant)
  GET   /api/applications/{id}/attachment    manager: the submitted file itself
  PATCH /api/applications/{id}/status        manager: Submitted / Under Review / Accepted / Rejected
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from backend.core import config
from backend.core.db import get_db
from backend.core.errors import Invalid
from backend.schemas.applications import (ApplicationDocument, ApplicationReceipt, ApplicationStatusChange,
                                          ApplicationStatusOut, MyApplication)
from backend.services import applications, resumes

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.post("", response_model=ApplicationReceipt, status_code=201)
def apply(
    project_id: int = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    skills: str = Form(""),
    cover_letter: str = Form(""),
    resume: UploadFile | None = File(None),
    db=Depends(get_db),
):
    name = name.strip()
    email = email.strip().lower()

    if not name:
        raise Invalid("Please provide your name.")

    resume_file = None
    if resume is not None:
        content = resume.file.read(config.MAX_RESUME_BYTES + 1)     # +1 byte: enough to spot "too big"
        resume_file = resumes.read_valid_resume(resume.filename, content)

    return applications.submit(db, project_id, name, email, skills.strip(), cover_letter.strip(), resume_file)


@router.get("/mine", response_model=list[MyApplication])
def my_applications(email: str, db=Depends(get_db)):
    return applications.list_for_email(db, email.strip().lower())


@router.get("/{application_id}/document", response_model=ApplicationDocument)
def document(application_id: int, db=Depends(get_db)):
    return applications.get_document(db, application_id)


@router.get("/{application_id}/attachment")
def attachment(application_id: int, db=Depends(get_db)):
    path = applications.attachment_path(db, application_id)
    is_pdf = path.suffix == ".pdf"
    return FileResponse(
        path,
        media_type="application/pdf" if is_pdf else
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"application-{application_id}{path.suffix}",
        content_disposition_type="inline" if is_pdf else "attachment",     # PDFs open inside the page
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.patch("/{application_id}/status", response_model=ApplicationStatusOut)
def change_status(application_id: int, change: ApplicationStatusChange, db=Depends(get_db)):
    return applications.set_status(db, application_id, change.status)
