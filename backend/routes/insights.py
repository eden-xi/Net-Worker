"""
"What's happening" endpoints, served under /api/insights.

  GET /api/insights/activity?after_id=0    manager: the live activity feed (newest first)

The page polls this every few seconds with after_id = the newest id it has seen,
so each poll only carries what is new (usually nothing).
"""

from fastapi import APIRouter, Depends, Query

from backend.core.db import get_db
from backend.core.security import require_manager
from backend.schemas.insights import ActivityOut
from backend.services import activity

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("/activity", response_model=list[ActivityOut], dependencies=[Depends(require_manager)])
def activity_feed(after_id: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db=Depends(get_db)):
    return activity.recent(db, after_id, limit)
