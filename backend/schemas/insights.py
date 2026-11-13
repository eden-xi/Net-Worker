"""
Data shapes for the "what's happening" features.

  ActivityKind   the four things we log
  ActivityOut    one line of the manager's live activity feed
  TimelineStep   one step of an application's history (Submitted -> Under Review -> ...)
  SkillMatch     how well a person fits a listing (backend/matching/skill_match.py)
  HealthOut      is the server up, and since when has the data been kept?
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ActivityKind(StrEnum):
    LISTING_POSTED = "listing_posted"
    LISTING_STATUS = "listing_status"
    APPLICATION_SUBMITTED = "application_submitted"
    APPLICATION_STATUS = "application_status"


class ActivityOut(BaseModel):
    id: int
    kind: ActivityKind
    actor_name: str | None = None
    message: str                     # ready to show: "Morgan Manager accepted Erin Employee for QA Tester"
    project_id: int | None = None
    application_id: int | None = None
    created_at: datetime


class TimelineStep(BaseModel):
    status: str
    actor_name: str | None = None
    created_at: datetime


class SkillMatch(BaseModel):
    project_id: int | None = None
    score: int                       # 0-100: share of required skills the person has
    matched: list[str]
    missing: list[str]
    bonus: list[str]                 # nice-to-have skills they also have


class HealthOut(BaseModel):
    status: str
    server_started: datetime
    data_since: datetime             # if this is older than server_started, data survived a restart
