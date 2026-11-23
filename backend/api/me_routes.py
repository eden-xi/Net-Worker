"""The signed-in user's own profile, resume, recommendations and applications."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend import config
from backend.access import managed_project_count
from backend.api.deps import get_db
from backend.auth import get_current_user
from backend.matching import Candidate, detect_skills, rank_projects, split_skills
from backend.avatars import delete_avatar, process_avatar, save_avatar
from backend.resumes import delete_resume_if_unused, read_resume, save_resume
from backend.skills_vocabulary import COMMON_SKILLS
from backend.users import User, avatar_version, get_user_row

router = APIRouter()


class ProfileUpdate(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=100)


def profile_response(connection, user):
    row = get_user_row(connection, user.id)
    candidate = Candidate(row["skills"], row["resume_text"])

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "skills": split_skills(row["skills"]),
        "has_resume": bool(row["resume_filename"]),
        "avatar": avatar_version(row["avatar_filename"]),
        "years_of_experience": candidate.years,
        "managed_projects": managed_project_count(connection, user),
        "can_become_pm": config.pm_self_service() and not user.has_role("pm"),
    }


@router.get("")
def get_me(user=Depends(get_current_user), connection=Depends(get_db)):
    return profile_response(connection, user)


@router.put("")
def update_me(body: ProfileUpdate, user=Depends(get_current_user), connection=Depends(get_db)):
    skills = split_skills(", ".join(skill[:60] for skill in body.skills))

    connection.execute(
        "UPDATE users SET skills = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (", ".join(skills), user.id),
    )
    connection.commit()

    return profile_response(connection, user)


def skill_vocabulary(connection):
    """Built-in skills plus every skill any project asks for."""
    vocabulary = list(COMMON_SKILLS)

    for row in connection.execute("SELECT required_skills, nice_to_have_skills FROM projects"):
        vocabulary.extend(split_skills(row["required_skills"]))
        vocabulary.extend(split_skills(row["nice_to_have_skills"]))

    return vocabulary


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...), user=Depends(get_current_user), connection=Depends(get_db),
):
    """Store the user's resume and suggest skills found in it.

    The suggestions are not added to the profile; the user reviews them and
    saves with PUT /me.
    """
    contents, extension, text = await read_resume(file)

    previous = get_user_row(connection, user.id)["resume_filename"]
    filename = save_resume(contents, extension)

    connection.execute(
        """
        UPDATE users SET resume_filename = ?, resume_text = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (filename, text, user.id),
    )
    connection.commit()
    delete_resume_if_unused(connection, previous)

    current = {skill.lower() for skill in split_skills(get_user_row(connection, user.id)["skills"])}
    detected = detect_skills(text, skill_vocabulary(connection))

    return {
        "has_extractable_text": bool(text),
        "extracted_character_count": len(text),
        "detected_skills": detected,
        "new_skills": [skill for skill in detected if skill.lower() not in current],
        "years_of_experience": Candidate("", text).years,
    }


@router.put("/avatar")
async def upload_avatar(
    file: UploadFile = File(...), user=Depends(get_current_user), connection=Depends(get_db),
):
    """Set your profile picture. It is cropped to a square."""
    data = await process_avatar(file)
    previous = get_user_row(connection, user.id)["avatar_filename"]
    filename = save_avatar(data)

    connection.execute(
        "UPDATE users SET avatar_filename = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (filename, user.id),
    )
    connection.commit()
    delete_avatar(previous)

    return profile_response(connection, user)


@router.delete("/avatar")
def remove_avatar(user=Depends(get_current_user), connection=Depends(get_db)):
    previous = get_user_row(connection, user.id)["avatar_filename"]

    connection.execute(
        "UPDATE users SET avatar_filename = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user.id,),
    )
    connection.commit()
    delete_avatar(previous)

    return profile_response(connection, user)


@router.get("/recommendations")
def recommendations(
    min_score: int = 1,
    location: str = "",
    seniority: str = "",
    user=Depends(get_current_user),
    connection=Depends(get_db),
):
    """Open projects ranked by fit with the user's skills and resume."""
    row = get_user_row(connection, user.id)

    projects = connection.execute(
        """
        SELECT projects.*,
            EXISTS (SELECT 1 FROM applications
                    WHERE applications.project_id = projects.id
                    AND applications.user_id = ?) AS applied
        FROM projects
        WHERE LOWER(TRIM(status)) = 'open'
        ORDER BY created_at DESC, id ASC
        """,
        (user.id,),
    ).fetchall()

    projects = [
        dict(project) for project in projects
        if (not location or project["location"] == location)
        and (not seniority or (project["seniority"] or "").lower() == seniority.lower())
    ]

    ranked = rank_projects(projects, Candidate(row["skills"], row["resume_text"]))
    return [project for project in ranked if project["match"]["score"] >= min_score]


@router.get("/applications")
def my_applications(user=Depends(get_current_user), connection=Depends(get_db)):
    rows = connection.execute(
        """
        SELECT
            applications.id AS application_id,
            projects.title AS project_title,
            projects.client_project AS client_project,
            projects.location AS location,
            applications.application_status AS status,
            applications.submitted_at AS submitted_at,
            applications.updated_at AS updated_at
        FROM applications
        JOIN projects ON applications.project_id = projects.id
        WHERE applications.user_id = ?
        ORDER BY applications.submitted_at DESC, applications.id DESC
        """,
        (user.id,),
    ).fetchall()

    return [dict(row) for row in rows]


@router.post("/become-pm")
def become_pm(user=Depends(get_current_user), connection=Depends(get_db)):
    """Self-service project manager access (when PM_SELF_SERVICE is on)."""
    if user.has_role("pm"):
        return profile_response(connection, user)

    if not config.pm_self_service():
        raise HTTPException(403, "Ask an administrator for project manager access.")

    connection.execute(
        "UPDATE users SET role = 'pm', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user.id,)
    )
    connection.commit()

    return profile_response(connection, User(user.id, user.email, user.display_name, "pm"))
