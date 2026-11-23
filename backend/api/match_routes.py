from fastapi import APIRouter
from pydantic import BaseModel

from backend.database.database import get_connection
from backend.matching import Candidate, rank_projects

router = APIRouter()


class RecommendationRequest(BaseModel):
    skills: list[str] = []
    resume_text: str = ""
    limit: int | None = None


@router.post("/recommend")
def recommend_projects(request: RecommendationRequest):
    """Rank open projects by how well they fit the given skills."""
    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT * FROM projects
            WHERE LOWER(TRIM(status)) = 'open'
            ORDER BY created_at DESC, id ASC
        """).fetchall()
    finally:
        connection.close()

    ranked = rank_projects(
        [dict(row) for row in rows],
        Candidate(request.skills, request.resume_text),
    )

    if request.limit:
        ranked = ranked[: request.limit]

    return ranked
