"""
Application endpoints, served under /api/applications.

  POST  /api/applications                    employee: apply (form + optional resume file)
  GET   /api/applications/mine               employee: "My applications" (with timelines)
  GET   /api/applications/profile            employee: my skills + whether a resume is on file
  PUT   /api/applications/profile            employee: save my skills (powers "% match")
  GET   /api/applications/{id}/document      manager: viewer data (listing + applicant)
  GET   /api/applications/{id}/attachment    manager: the submitted file itself
  PATCH /api/applications/{id}/status        manager: Submitted / Under Review / Accepted / Rejected

Identity always comes from the session (Depends), never from the form or the URL.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from backend.core import config
from backend.core.db import get_db
from backend.core.security import require_employee, require_manager
from backend.schemas.applications import (ApplicationDocument, ApplicationReceipt, ApplicationStatusChange,
                                          ApplicationStatusOut, MyApplication)
from backend.schemas.users import ProfileIn, ProfileOut, User
from backend.services import applications, resumes

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.post("", response_model=ApplicationReceipt, status_code=201)
def apply(
    project_id: int = Form(...),
    skills: str = Form(""),
    cover_letter: str = Form(""),
    resume: UploadFile | None = File(None),
    employee: User = Depends(require_employee),
    db=Depends(get_db),
):
    resume_file = None
    if resume is not None:
        content = resume.file.read(config.MAX_RESUME_BYTES + 1)     # +1 byte: enough to spot "too big"
        resume_file = resumes.read_valid_resume(resume.filename, content)

    # Name and email come from the signed-in session, so nobody can apply as someone else.
    return applications.submit(db, project_id, employee, skills.strip(), cover_letter.strip(), resume_file)


@router.get("/mine", response_model=list[MyApplication])
def my_applications(employee: User = Depends(require_employee), db=Depends(get_db)):
    return applications.list_for_email(db, employee.email)


@router.get("/profile", response_model=ProfileOut)
def my_profile(employee: User = Depends(require_employee), db=Depends(get_db)):
    return applications.get_profile(db, employee)


@router.put("/profile", response_model=ProfileOut)
def save_my_profile(profile: ProfileIn, employee: User = Depends(require_employee), db=Depends(get_db)):
    return applications.save_profile(db, employee, profile.skills)


@router.get("/{application_id}/document", response_model=ApplicationDocument,
            dependencies=[Depends(require_manager)])
def document(application_id: int, db=Depends(get_db)):
    return applications.get_document(db, application_id)


@router.get("/{application_id}/attachment", dependencies=[Depends(require_manager)])
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
def change_status(application_id: int, change: ApplicationStatusChange, manager: User = Depends(require_manager),
                  db=Depends(get_db)):
    return applications.set_status(db, application_id, change.status, manager)
