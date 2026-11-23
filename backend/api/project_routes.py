import csv
import io
import json
import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.database.database import PROJECT_COLUMNS, get_connection
from backend.matching import Candidate, score_project

router = APIRouter()

MAX_CSV_SIZE = 2 * 1024 * 1024

COLUMN_ALIASES = {
    "role_id": [
        "role_id", "role id", "project id", "job id",
        "position id", "requisition id",
    ],
    "title": [
        "title", "job title", "position", "position title",
        "role name", "job name",
    ],
    "client_project": [
        "client_project", "client project", "client",
        "project name", "account", "business unit",
    ],
    "required_skills": [
        "required_skills", "required skills", "skills required",
        "skills", "key skills", "technical skills",
    ],
    "nice_to_have_skills": [
        "nice_to_have_skills", "nice to have skills",
        "preferred skills", "additional skills", "bonus skills",
    ],
    "seniority": [
        "seniority", "experience level", "level",
        "job level", "career level",
    ],
    "location": [
        "location", "work location", "job location",
        "work arrangement", "work type",
    ],
    "start_date": [
        "start_date", "start date", "beginning date",
        "project start", "start",
    ],
    "status": [
        "status", "project status", "role status", "availability",
    ],
    "description": [
        "description", "job description", "project description",
        "role description", "details", "summary",
    ],
}


def normalize_column_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


NORMALIZED_ALIASES = {
    column: {normalize_column_name(alias) for alias in aliases}
    for column, aliases in COLUMN_ALIASES.items()
}


def map_csv_headers(headers):
    """Map each database column to the CSV header that supplies it."""
    mapping = {}

    for column, accepted in NORMALIZED_ALIASES.items():
        for header in headers:
            if header and normalize_column_name(header) in accepted:
                mapping[column] = header
                break

    return mapping


# ==========================================
# PROJECTS
# ==========================================

@router.get("")
def get_projects(include_closed: bool = False):
    """Open projects, newest first. Managers pass include_closed=true."""
    where = "" if include_closed else "WHERE LOWER(TRIM(projects.status)) = 'open'"

    connection = get_connection()

    try:
        rows = connection.execute(f"""
            SELECT projects.*,
                (SELECT COUNT(*) FROM applications
                 WHERE applications.project_id = projects.id) AS applicant_count
            FROM projects
            {where}
            ORDER BY projects.created_at DESC, projects.id ASC
        """).fetchall()
    finally:
        connection.close()

    return [dict(row) for row in rows]


@router.get("/{project_id}")
def get_project(project_id: int):
    connection = get_connection()

    try:
        project = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        connection.close()

    if project is None:
        raise HTTPException(404, "Project not found")

    return dict(project)


@router.post("/upload-csv")
async def upload_projects_csv(file: UploadFile = File(...)):
    """Add projects from a CSV. Rows whose Role ID already exists are updated."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")

    contents = await file.read(MAX_CSV_SIZE + 1)

    if not contents:
        raise HTTPException(400, "The uploaded CSV file is empty.")

    if len(contents) > MAX_CSV_SIZE:
        raise HTTPException(413, "CSV files must be 2 MB or smaller.")

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Please save your CSV file using UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(400, "The CSV file does not contain column headers.")

    mapping = map_csv_headers(reader.fieldnames)

    missing = [
        label for column, label in [
            ("role_id", "Project ID / Role ID"),
            ("title", "Job Title / Position"),
        ]
        if column not in mapping
    ]
    if missing:
        raise HTTPException(
            400, "Could not recognize required columns: " + ", ".join(missing)
        )

    # Only columns present in the CSV are written, so a re-upload that omits
    # a column (say, description) leaves the existing value alone.
    columns = [column for column in PROJECT_COLUMNS if column in mapping]
    updates = ", ".join(
        f"{column} = excluded.{column}" for column in columns if column != "role_id"
    )

    connection = get_connection()
    imported = updated = skipped = 0

    try:
        for row in reader:
            values = {
                column: (row.get(mapping[column]) or "").strip()
                for column in columns
            }

            if not values["role_id"] or not values["title"]:
                skipped += 1
                continue

            if "status" in values and not values["status"]:
                values["status"] = "Open"

            exists = connection.execute(
                "SELECT 1 FROM projects WHERE role_id = ?", (values["role_id"],)
            ).fetchone()

            connection.execute(
                f"""
                INSERT INTO projects ({", ".join(columns)})
                VALUES ({", ".join("?" for _ in columns)})
                ON CONFLICT(role_id) DO UPDATE SET {updates}
                """,
                [values[column] for column in columns],
            )

            if exists:
                updated += 1
            else:
                imported += 1

        connection.commit()
    finally:
        connection.close()

    return {
        "message": "CSV upload completed successfully.",
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total_processed": imported + updated + skipped,
    }


# ==========================================
# MANAGER: APPLICANTS FOR A PROJECT
# ==========================================

@router.get("/{project_id}/applications")
def get_project_applications(project_id: int):
    """Applicants for a project, best skill match first."""
    connection = get_connection()

    try:
        project = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()

        if project is None:
            raise HTTPException(404, "Project not found")

        rows = connection.execute("""
            SELECT
                applications.*,
                employees.name,
                employees.email,
                employees.skills,
                employees.resume_text,
                matches.match_score,
                matches.matched_skills
            FROM applications
            JOIN employees ON applications.employee_id = employees.id
            LEFT JOIN matches
                ON matches.employee_id = applications.employee_id
                AND matches.project_id = applications.project_id
            WHERE applications.project_id = ?
        """, (project_id,)).fetchall()
    finally:
        connection.close()

    applicants = []

    for row in rows:
        applicant = dict(row)
        resume_text = applicant.pop("resume_text") or ""

        if applicant["match_score"] is None:
            # Applied before matching existed: score it now.
            match = score_project(
                dict(project), Candidate(applicant["skills"], resume_text)
            )
        else:
            match = json.loads(applicant["matched_skills"] or "{}")
            match["score"] = round(applicant["match_score"])

        applicant.pop("matched_skills")
        applicant.pop("match_score")
        applicant["match"] = match
        applicants.append(applicant)

    applicants.sort(
        key=lambda a: (a["match"].get("score", 0), a["submitted_at"] or ""),
        reverse=True,
    )

    return applicants
