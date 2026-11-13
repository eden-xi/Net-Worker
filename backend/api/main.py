
import csv
import io
import re
import sqlite3
from contextlib import asynccontextmanager

from pydantic import BaseModel, EmailStr
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.api.resume_routes import router as resume_router
from backend.api.application_routes import router as application_router
from backend.core.db import connect as get_connection, create_tables


# Runs when this app is started on its own (uvicorn backend.api.main:app).
# When deploy/server.py mounts it, deploy/server.py runs create_tables() instead.
@asynccontextmanager
async def lifespan(app):
    create_tables()
    yield


app = FastAPI(title="ProjectHub API", lifespan=lifespan)
app.include_router(resume_router, prefix="/resumes", tags=["Resumes"])
app.include_router(application_router, prefix="/applications", tags=["Applications"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# CSV COLUMN RECOGNITION
# ==========================================

COLUMN_ALIASES = {
    "role_id": [
        "role_id", "role id", "project id", "job id",
        "position id", "requisition id"
    ],
    "title": [
        "title", "job title", "position", "position title",
        "role name", "job name"
    ],
    "client_project": [
        "client_project", "client project", "client",
        "project name", "account", "business unit"
    ],
    "required_skills": [
        "required_skills", "required skills", "skills required",
        "skills", "key skills", "technical skills"
    ],
    "nice_to_have_skills": [
        "nice_to_have_skills", "nice to have skills",
        "preferred skills", "additional skills",
        "bonus skills"
    ],
    "seniority": [
        "seniority", "experience level", "level",
        "job level", "career level"
    ],
    "location": [
        "location", "work location", "job location",
        "work arrangement", "work type"
    ],
    "start_date": [
        "start_date", "start date", "beginning date",
        "project start", "start"
    ],
    "status": [
        "status", "project status", "role status",
        "availability"
    ],
    "description": [
        "description", "job description",
        "project description", "role description",
        "details", "summary"
    ]
}


def normalize_column_name(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def standardize_csv_row(row):
    standardized = {}

    for database_column, aliases in COLUMN_ALIASES.items():
        accepted_names = {
            normalize_column_name(alias) for alias in aliases
        }

        for csv_column, value in row.items():
            if (
                csv_column
                and normalize_column_name(csv_column) in accepted_names
            ):
                standardized[database_column] = (value or "").strip()
                break

    return standardized


# ==========================================
# REQUEST MODELS
# ==========================================

class ApplicationRequest(BaseModel):
    project_id: int
    name: str
    email: EmailStr
    skills: str = ""
    resume_filename: str = ""
    cover_letter: str = ""


class ApplicationStatusUpdate(BaseModel):
    status: str


# ==========================================
# GENERAL API ROUTES
# ==========================================

@app.get("/")
def home():
    return {
        "message": "Welcome to ProjectHub API",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


# ==========================================
# PROJECT ROUTES
# ==========================================

@app.get("/projects")
def get_projects():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM projects
        WHERE LOWER(TRIM(status)) = 'open'
        ORDER BY created_at DESC
    """)

    projects = [dict(row) for row in cursor.fetchall()]

    connection.close()

    return projects


@app.get("/projects/{project_id}")
def get_project(project_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM projects WHERE id = ?",
        (project_id,)
    )

    project = cursor.fetchone()

    connection.close()

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    return dict(project)


# ==========================================
# CSV PROJECT UPLOAD
# ==========================================

@app.post("/projects/upload-csv")
async def upload_projects_csv(file: UploadFile = File(...)):

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file."
        )

    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file is empty."
        )

    try:
        text = contents.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="The CSV file does not contain column headers."
            )

        recognized_columns = {
            database_column
            for database_column, aliases in COLUMN_ALIASES.items()
            if any(
                normalize_column_name(header) in {
                    normalize_column_name(alias) for alias in aliases
                }
                for header in reader.fieldnames if header
            )
        }

        missing_columns = []

        if "role_id" not in recognized_columns:
            missing_columns.append("Project ID / Role ID")

        if "title" not in recognized_columns:
            missing_columns.append("Job Title / Position")

        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not recognize required columns: "
                    + ", ".join(missing_columns)
                )
            )

        connection = get_connection()
        cursor = connection.cursor()

        imported = 0
        skipped = 0

        for row in reader:
            project = standardize_csv_row(row)

            role_id = project.get("role_id", "")
            title = project.get("title", "")

            if not role_id or not title:
                skipped += 1
                continue

            cursor.execute("""
                INSERT OR IGNORE INTO projects (
                    role_id, title, client_project,
                    required_skills, nice_to_have_skills,
                    seniority, location, start_date,
                    status, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                role_id,
                title,
                project.get("client_project", ""),
                project.get("required_skills", ""),
                project.get("nice_to_have_skills", ""),
                project.get("seniority", ""),
                project.get("location", ""),
                project.get("start_date", ""),
                project.get("status", "Open") or "Open",
                project.get("description", "")
            ))

            if cursor.rowcount == 1:
                imported += 1
            else:
                skipped += 1

        connection.commit()
        connection.close()

        return {
            "message": "CSV upload completed successfully.",
            "imported": imported,
            "skipped": skipped,
            "total_processed": imported + skipped
        }

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Please save your CSV file using UTF-8 encoding."
        )


# ==========================================
# APPLICATION SUBMISSION
# ==========================================

@app.post("/applications")
def submit_application(application: ApplicationRequest):

    name = application.name.strip()
    email = str(application.email).strip().lower()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Please provide your name."
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Find or create the employee profile
        cursor.execute(
            "SELECT id FROM employees WHERE email = ?",
            (email,)
        )

        employee = cursor.fetchone()

        if employee:
            employee_id = employee["id"]

            cursor.execute("""
                UPDATE employees
                SET name = ?, skills = ?, resume_filename = ?
                WHERE id = ?
            """, (
                name,
                application.skills,
                application.resume_filename,
                employee_id
            ))

        else:
            cursor.execute("""
                INSERT INTO employees (
                    name, email, skills, resume_filename
                )
                VALUES (?, ?, ?, ?)
            """, (
                name,
                email,
                application.skills,
                application.resume_filename
            ))

            employee_id = cursor.lastrowid

        # Confirm that the selected project is still open
        cursor.execute("""
            SELECT id
            FROM projects
            WHERE id = ?
            AND LOWER(TRIM(status)) = 'open'
        """, (getattr(application, "project_id", None),))

        project = cursor.fetchone()

        if project is None:
            raise HTTPException(
                status_code=404,
                detail="This project is unavailable."
            )

        # Save the application
        cursor.execute("""
            INSERT INTO applications (
                employee_id,
                project_id,
                application_status,
                resume_filename,
                cover_letter
            )
            VALUES (?, ?, 'Submitted', ?, ?)
        """, (
            employee_id,
            application.project_id,
            application.resume_filename,
            application.cover_letter
        ))

        application_id = cursor.lastrowid

        connection.commit()

        return {
            "message": "Application submitted successfully!",
            "application_id": application_id,
            "status": "Submitted"
        }

    except sqlite3.IntegrityError:
        connection.rollback()

        raise HTTPException(
            status_code=409,
            detail="You have already applied to this project."
        )

    finally:
        connection.close()


# ==========================================
# VIEW INDIVIDUAL APPLICATION
# ==========================================

@app.get("/applications/{application_id}")
def get_application(application_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            applications.*,
            employees.name,
            employees.email,
            projects.title,
            projects.role_id
        FROM applications
        JOIN employees
            ON applications.employee_id = employees.id
        JOIN projects
            ON applications.project_id = projects.id
        WHERE applications.id = ?
    """, (application_id,))

    application = cursor.fetchone()

    connection.close()

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found."
        )

    return dict(application)


# ==========================================
# MANAGER: VIEW PROJECT APPLICANTS
# ==========================================

@app.get("/projects/{project_id}/applications")
def get_project_applications(project_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            applications.*,
            employees.name,
            employees.email,
            employees.skills
        FROM applications
        JOIN employees
            ON applications.employee_id = employees.id
        WHERE applications.project_id = ?
        ORDER BY applications.submitted_at DESC
    """, (project_id,))

    applications = [
        dict(row) for row in cursor.fetchall()
    ]

    connection.close()

    return applications


# ==========================================
# MANAGER: UPDATE APPLICATION STATUS
# ==========================================

@app.patch("/applications/{application_id}/status")
def update_application_status(
    application_id: int,
    update: ApplicationStatusUpdate
):

    allowed_statuses = [
        "Submitted",
        "Under Review",
        "Accepted",
        "Rejected"
    ]

    new_status = update.status.strip()

    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid application status."
        )

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE applications
        SET application_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_status, application_id))

    if cursor.rowcount == 0:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Application not found."
        )

    connection.commit()
    connection.close()

    return {
        "message": "Application status updated.",
        "application_id": application_id,
        "status": new_status
    }
