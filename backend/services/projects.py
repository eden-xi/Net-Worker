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
from backend.schemas.projects import ProjectStatus

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
    """Every listing in any status, with who posted it and how many people applied."""
    rows = db.execute("""
        SELECT projects.*, COUNT(applications.id) AS applicant_count
        FROM projects
        LEFT JOIN applications ON applications.project_id = projects.id
        GROUP BY projects.id
        ORDER BY projects.created_at DESC, projects.id DESC
    """).fetchall()
    return [dict(row) for row in rows]


# ------------------------------------------
# 2. Changing listings
# ------------------------------------------

def create(db, listing, poster_email, poster_name):
    """listing is a schemas.projects.ProjectIn (already validated and trimmed)."""
    role_id = f"MP-{uuid4().hex[:8].upper()}"
    with transaction(db):
        cursor = db.execute("""
            INSERT INTO projects (role_id, title, client_project, required_skills, nice_to_have_skills,
                                  seniority, location, start_date, status, description,
                                  posted_by_email, posted_by_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (role_id, listing.title, listing.client_project, listing.required_skills,
              listing.nice_to_have_skills, listing.seniority, listing.location, listing.start_date,
              ProjectStatus.OPEN, listing.description, poster_email, poster_name))
    return get(db, cursor.lastrowid)


def set_status(db, project_id, status):
    with transaction(db):
        cursor = db.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))
        if cursor.rowcount == 0:
            raise NotFound("Project not found.")
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
