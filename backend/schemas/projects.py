"""
Data shapes for project listings.

  ProjectStatus      the ONLY list of listing statuses in the codebase
  ProjectIn          what a manager sends to create a listing (validated, trimmed)
  ProjectOut         what the API sends back for a listing
  ManagedProjectOut  ProjectOut + who posted it + how many applied (manager view)
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProjectStatus(StrEnum):
    OPEN = "Open"
    CLOSED = "Closed"
    FILLED = "Filled"

    @classmethod
    def from_text(cls, text):
        """'open', ' OPEN ' -> ProjectStatus.OPEN. Blank -> OPEN. Unknown text -> None."""
        cleaned = (text or "").strip().lower()
        if not cleaned:
            return cls.OPEN
        for status in cls:
            if status.value.lower() == cleaned:
                return status
        return None


class ProjectIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)       # "  Title " -> "Title"

    title: str = Field(min_length=1, max_length=120)
    client_project: str = Field("", max_length=120)
    required_skills: str = Field("", max_length=500)
    nice_to_have_skills: str = Field("", max_length=500)
    seniority: str = Field("", max_length=40)
    location: str = Field("", max_length=80)
    start_date: str = Field("", max_length=20)
    description: str = Field("", max_length=4000)


class ProjectOut(BaseModel):
    id: int
    role_id: str
    title: str
    client_project: str | None = None
    required_skills: str | None = None
    nice_to_have_skills: str | None = None
    seniority: str | None = None
    location: str | None = None
    start_date: str | None = None
    status: ProjectStatus
    description: str | None = None
    created_at: datetime


class ManagedProjectOut(ProjectOut):
    posted_by_name: str | None = None
    applicant_count: int
    new_count: int = 0              # pipeline: Submitted
    review_count: int = 0           #           Under Review
    accepted_count: int = 0
    rejected_count: int = 0


class ProjectStatusChange(BaseModel):
    status: ProjectStatus


class CsvImportResult(BaseModel):
    imported: int
    skipped: int
    total_processed: int
