"""
Data shapes for applications (an employee applying to a listing).

  ApplicationStatus      the ONLY list of application statuses in the codebase
  ApplicationReceipt     what the employee gets back after applying
  MyApplication          one row of "My applications"
  Applicant              one row of a listing's applicant list (manager view)
  ApplicationDocument    everything the manager's document viewer shows
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from backend.schemas.insights import SkillMatch, TimelineStep
from backend.schemas.projects import ProjectOut


class ApplicationStatus(StrEnum):
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class ApplicationStatusChange(BaseModel):
    status: ApplicationStatus


class ApplicationStatusOut(BaseModel):
    application_id: int
    status: ApplicationStatus


class ApplicationReceipt(BaseModel):
    application_id: int
    status: ApplicationStatus
    resume_uploaded: bool
    message: str


class MyApplication(BaseModel):
    application_id: int
    project_id: int
    project_title: str
    client_project: str | None = None
    location: str | None = None
    status: ApplicationStatus
    submitted_at: datetime
    updated_at: datetime
    timeline: list[TimelineStep] = []


class Applicant(BaseModel):
    application_id: int
    name: str | None = None
    email: str
    skills: str | None = None
    status: ApplicationStatus
    submitted_at: datetime
    has_attachment: bool
    match: SkillMatch


class ApplicationDocument(BaseModel):
    application_id: int
    status: ApplicationStatus
    cover_letter: str | None = None
    submitted_at: datetime
    applicant_name: str | None = None
    applicant_email: str
    applicant_skills: str | None = None
    resume_text: str | None = None
    project: ProjectOut
    attachment_type: Literal["pdf", "docx", ""]
    attachment_url: str
    match: SkillMatch
