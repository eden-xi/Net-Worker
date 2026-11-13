"""
"What's happening" endpoints, served under /api/insights.

  GET /api/insights/activity?after_id=0    manager: the live activity feed (newest first)
  GET /api/insights/matches                employee: "% match" for every Open listing

The page polls this every few seconds with after_id = the newest id it has seen,
so each poll only carries what is new (usually nothing).
"""

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db
from backend.core.security import require_employee, require_manager
from backend.schemas.insights import ActivityOut, SkillMatch
from backend.schemas.users import User
from backend.services import activity, applications, projects

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("/activity", response_model=list[ActivityOut], dependencies=[Depends(require_manager)])
def activity_feed(after_id: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db=Depends(get_db)):
    return activity.recent(db, after_id, limit)


@router.get("/matches", response_model=list[SkillMatch])
def my_matches(employee: User = Depends(require_employee), db=Depends(get_db)):
    return projects.matches_for(db, applications.get_profile(db, employee))
