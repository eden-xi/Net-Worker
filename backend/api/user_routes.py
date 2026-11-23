from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.api.deps import get_db
from backend.auth import get_current_user
from backend.avatars import avatar_path
from backend.users import get_user_row

router = APIRouter()


@router.get("/{user_id}/avatar")
def get_avatar(user_id: int, user=Depends(get_current_user), connection=Depends(get_db)):
    """A user's profile picture. Visible to anyone signed in, as in Teams."""
    row = get_user_row(connection, user_id)
    path = avatar_path(row["avatar_filename"]) if row else None

    if path is None:
        raise HTTPException(404, "No profile picture.")

    # The frontend requests ?v=<version>, so a changed picture gets a new URL.
    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"}
    )
