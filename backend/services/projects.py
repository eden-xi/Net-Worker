"""
Project listings: every SQL statement about the projects table lives here.

Each function takes an open database connection (db) as its first argument and
returns plain dicts. Routes turn those dicts into API responses (schemas/projects.py).
"""

import csv
import io
import re
from uuid import uuid4

from backend.core.db import transaction
from backend.core.errors import Invalid, NotFound
from backend.schemas.insights import ActivityKind
from backend.schemas.projects import ProjectStatus
from backend.matching import skill_match
from backend.services import activity

# ------------------------------------------
# 1. Reading listings
# ------------------------------------------

def list_open(db):
    """The shared feed: every Open listing, newest first."""
    rows = db.execute(
        "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC, id DESC",
        (ProjectStatus.OPEN,),
    ).fetchall()
    return [dict(row) for row in rows]


def get(db, project_id):
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise NotFound("Project not found.")
    return dict(row)


def list_for_managers(db):
    """Every listing in any status, with who posted it and its applicant pipeline."""
    rows = db.execute("""
        SELECT projects.*,
               COUNT(applications.id) AS applicant_count,
               SUM(applications.application_status = 'Submitted') AS new_count,
               SUM(applications.application_status = 'Under Review') AS review_count,
               SUM(applications.application_status = 'Accepted') AS accepted_count,
               SUM(applications.application_status = 'Rejected') AS rejected_count
        FROM projects
        LEFT JOIN applications ON applications.project_id = projects.id
        GROUP BY projects.id
        ORDER BY projects.created_at DESC, projects.id DESC
    """).fetchall()
    # SUM() over no rows is NULL; show 0 instead.
    return [{**dict(row), **{key: row[key] or 0 for key in
             ("new_count", "review_count", "accepted_count", "rejected_count")}} for row in rows]


def matches_for(db, profile):
    """How well one person (profile: skills + resume_text) fits every Open listing."""
    return [{"project_id": project["id"],
             **skill_match.score(project["required_skills"], project["nice_to_have_skills"],
                                 profile["skills"], profile["resume_text"])}
            for project in list_open(db)]


# ------------------------------------------
# 2. Changing listings
# ------------------------------------------

def create(db, listing, manager):
    """listing is a schemas.projects.ProjectIn (already validated and trimmed); manager is the User."""
    role_id = f"MP-{uuid4().hex[:8].upper()}"
    with transaction(db):
        cursor = db.execute("""
            INSERT INTO projects (role_id, title, client_project, required_skills, nice_to_have_skills,
                                  seniority, location, start_date, status, description,
                                  posted_by_email, posted_by_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (role_id, listing.title, listing.client_project, listing.required_skills,
              listing.nice_to_have_skills, listing.seniority, listing.location, listing.start_date,
              ProjectStatus.OPEN, listing.description, manager.email, manager.name))
        activity.record(db, ActivityKind.LISTING_POSTED, manager, project_id=cursor.lastrowid,
                        to_status=ProjectStatus.OPEN)
    return get(db, cursor.lastrowid)


def set_status(db, project_id, status, actor):
    old_status = get(db, project_id)["status"]          # NotFound if it doesn't exist
    with transaction(db):
        db.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))
        activity.record(db, ActivityKind.LISTING_STATUS, actor, project_id=project_id,
                        from_status=old_status, to_status=status)
    return get(db, project_id)


# ------------------------------------------
# 3. CSV import (the team's column-alias rules, unchanged)
# ------------------------------------------

COLUMN_ALIASES = {
    "role_id": ["role_id", "role id", "project id", "job id", "position id", "requisition id"],
    "title": ["title", "job title", "position", "position title", "role name", "job name"],
    "client_project": ["client_project", "client project", "client", "project name", "account",
                       "business unit"],
    "required_skills": ["required_skills", "required skills", "skills required", "skills", "key skills",
                        "technical skills"],
    "nice_to_have_skills": ["nice_to_have_skills", "nice to have skills", "preferred skills",
                            "additional skills", "bonus skills"],
    "seniority": ["seniority", "experience level", "level", "job level", "career level"],
    "location": ["location", "work location", "job location", "work arrangement", "work type"],
    "start_date": ["start_date", "start date", "beginning date", "project start", "start"],
    "status": ["status", "project status", "role status", "availability"],
    "description": ["description", "job description", "project description", "role description",
                    "details", "summary"],
}


def simplify(name):
    """'Job Title' -> 'jobtitle', so headers match whatever their spacing or case."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def match_headers(headers):
    """{database column: CSV header} for every header we recognise."""
    found = {}
    for column, aliases in COLUMN_ALIASES.items():
        accepted = {simplify(alias) for alias in aliases}
        for header in headers:
            if header and simplify(header) in accepted:
                found[column] = header
                break
    return found


def import_csv(db, raw_bytes):
    """Add listings from a CSV file. Rows whose role ID already exists are skipped."""
    if not raw_bytes:
        raise Invalid("The uploaded CSV file is empty.")

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Invalid("Please save your CSV file using UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))
    headers = match_headers(reader.fieldnames or [])

    missing = [label for column, label in [("role_id", "Project ID / Role ID"), ("title", "Job Title / Position")]
               if column not in headers]
    if missing:
        raise Invalid("Could not recognize required columns: " + ", ".join(missing))

    imported = skipped = 0

    with transaction(db):                       # the whole file goes in, or none of it
        for row in reader:
            values = {column: (row.get(header) or "").strip() for column, header in headers.items()}
            status = ProjectStatus.from_text(values.get("status"))

            if not values["role_id"] or not values["title"] or status is None:
                skipped += 1
                continue

            cursor = db.execute("""
                INSERT OR IGNORE INTO projects (role_id, title, client_project, required_skills,
                    nice_to_have_skills, seniority, location, start_date, status, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (values["role_id"], values["title"], values.get("client_project", ""),
                  values.get("required_skills", ""), values.get("nice_to_have_skills", ""),
                  values.get("seniority", ""), values.get("location", ""), values.get("start_date", ""),
                  status, values.get("description", "")))

            if cursor.rowcount == 1:
                imported += 1
            else:
                skipped += 1

    return {"imported": imported, "skipped": skipped, "total_processed": imported + skipped}
