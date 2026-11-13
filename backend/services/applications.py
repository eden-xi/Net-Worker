"""
Applications: an employee applying to a listing, and managers reviewing them.

One submit() replaces the two apply endpoints the backend used to have.
"""

import sqlite3

from backend.core.db import transaction
from backend.core.errors import Conflict, NotFound
from backend.matching import skill_match
from backend.schemas.applications import ApplicationStatus
from backend.schemas.insights import ActivityKind
from backend.schemas.projects import ProjectStatus
from backend.services import activity, projects, resumes

# ------------------------------------------
# 1. Applying
# ------------------------------------------

def find_employee(db, email):
    return db.execute("SELECT * FROM employees WHERE email = ?", (email,)).fetchone()


def save_employee(db, existing, name, email, skills, resume_filename, resume_text):
    """Create the employee profile, or update it. Returns the employee id."""
    if existing:
        db.execute("""
            UPDATE employees SET name = ?, skills = ?, resume_filename = ?, resume_text = ?
            WHERE id = ?
        """, (name, skills, resume_filename, resume_text, existing["id"]))
        return existing["id"]

    cursor = db.execute("""
        INSERT INTO employees (name, email, skills, resume_filename, resume_text)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, skills, resume_filename, resume_text))
    return cursor.lastrowid


def submit(db, project_id, applicant, skills, cover_letter, resume=None):
    """applicant (the signed-in User) applies to an Open listing.
    resume is a resumes.ResumeFile or None; without one, the resume on their profile is reused."""
    name, email = applicant.name, applicant.email
    project = projects.get(db, project_id)
    if project["status"] != ProjectStatus.OPEN:
        raise NotFound("This project is no longer open.")

    employee = find_employee(db, email)

    if employee:
        already = db.execute("SELECT id FROM applications WHERE employee_id = ? AND project_id = ?",
                             (employee["id"], project_id)).fetchone()
        if already:
            raise Conflict("You have already applied to this project.")

    # Start from the resume already on the profile (if any), then replace it if a new one came in.
    resume_filename = ""
    resume_text = ""
    if employee:
        resume_filename = employee["resume_filename"] or ""
        resume_text = employee["resume_text"] or ""

    saved_name = None
    if resume is not None:
        saved_name = resumes.save(resume)
        resume_filename = saved_name
        resume_text = resume.text

    try:
        with transaction(db):               # profile + application are saved together, or not at all
            employee_id = save_employee(db, employee, name, email, skills, resume_filename, resume_text)
            cursor = db.execute("""
                INSERT INTO applications (employee_id, project_id, application_status, resume_filename, cover_letter)
                VALUES (?, ?, ?, ?, ?)
            """, (employee_id, project_id, ApplicationStatus.SUBMITTED, resume_filename, cover_letter))
            activity.record(db, ActivityKind.APPLICATION_SUBMITTED, applicant, project_id=project_id,
                            application_id=cursor.lastrowid, to_status=ApplicationStatus.SUBMITTED)

    except sqlite3.IntegrityError:
        # Two clicks at the same moment: the database's UNIQUE rule caught the second one.
        resumes.delete(saved_name)
        raise Conflict("You have already applied to this project.")

    except Exception:
        resumes.delete(saved_name)          # never leave an orphan file behind
        raise

    return {
        "application_id": cursor.lastrowid,
        "status": ApplicationStatus.SUBMITTED,
        "resume_uploaded": saved_name is not None,
        "message": "Application submitted successfully!",
    }


def get_profile(db, user):
    """The person's skills and resume text (empty if they have never applied or saved skills)."""
    employee = find_employee(db, user.email)
    if employee is None:
        return {"skills": "", "resume_text": "", "resume_on_file": False}
    return {"skills": employee["skills"] or "", "resume_text": employee["resume_text"] or "",
            "resume_on_file": bool(employee["resume_filename"])}


def save_profile(db, user, skills):
    """Save the person's skills (creates their profile on first use). Keeps any resume on file."""
    employee = find_employee(db, user.email)
    with transaction(db):
        if employee:
            db.execute("UPDATE employees SET name = ?, skills = ? WHERE id = ?", (user.name, skills, employee["id"]))
        else:
            db.execute("INSERT INTO employees (name, email, skills) VALUES (?, ?, ?)", (user.name, user.email, skills))
    return get_profile(db, user)


# ------------------------------------------
# 2. Reading applications
# ------------------------------------------

def list_for_email(db, email):
    """'My applications' for one person, each with its timeline (Submitted -> ... -> decision)."""
    rows = db.execute("""
        SELECT applications.id AS application_id, projects.id AS project_id,
               projects.title AS project_title, projects.client_project, projects.location,
               applications.application_status AS status,
               applications.submitted_at, applications.updated_at
        FROM applications
        JOIN employees ON applications.employee_id = employees.id
        JOIN projects ON applications.project_id = projects.id
        WHERE employees.email = ?
        ORDER BY applications.submitted_at DESC, applications.id DESC
    """, (email,)).fetchall()

    mine = [dict(row) for row in rows]
    steps = activity.timelines(db, [item["application_id"] for item in mine])
    for item in mine:
        item["timeline"] = steps[item["application_id"]]
    return mine


def list_for_project(db, project_id):
    """Everyone who applied to one listing (manager view), each with their skill match."""
    project = projects.get(db, project_id)               # 404 if the listing does not exist
    rows = db.execute("""
        SELECT applications.id AS application_id, employees.name, employees.email, employees.skills,
               employees.resume_text,
               applications.application_status AS status, applications.submitted_at,
               applications.resume_filename
        FROM applications
        JOIN employees ON applications.employee_id = employees.id
        WHERE applications.project_id = ?
        ORDER BY applications.submitted_at DESC, applications.id DESC
    """, (project_id,)).fetchall()

    applicants = []
    for row in rows:
        applicant = dict(row)
        applicant["has_attachment"] = bool(resumes.attachment_type(applicant.pop("resume_filename")))
        applicant["match"] = skill_match.score(project["required_skills"], project["nice_to_have_skills"],
                                               applicant["skills"], applicant.pop("resume_text"))
        applicants.append(applicant)
    return applicants


def find(db, application_id):
    row = db.execute("""
        SELECT applications.*, employees.name AS applicant_name, employees.email AS applicant_email,
               employees.skills AS applicant_skills, employees.resume_text
        FROM applications
        JOIN employees ON applications.employee_id = employees.id
        WHERE applications.id = ?
    """, (application_id,)).fetchone()
    if row is None:
        raise NotFound("Application not found.")
    return dict(row)


def get_document(db, application_id):
    """Everything the manager's document viewer shows: application + listing + attachment link."""
    application = find(db, application_id)
    kind = resumes.attachment_type(application["resume_filename"])
    project = projects.get(db, application["project_id"])
    return {
        "application_id": application["id"],
        "status": application["application_status"],
        "cover_letter": application["cover_letter"],
        "submitted_at": application["submitted_at"],
        "applicant_name": application["applicant_name"],
        "applicant_email": application["applicant_email"],
        "applicant_skills": application["applicant_skills"],
        "resume_text": application["resume_text"],
        "project": project,
        "attachment_type": kind,
        "attachment_url": f"/api/applications/{application_id}/attachment" if kind else "",
        "match": skill_match.score(project["required_skills"], project["nice_to_have_skills"],
                                   application["applicant_skills"], application["resume_text"]),
    }


def attachment_path(db, application_id):
    """Where the submitted file is on disk. Raises NotFound if there is none."""
    path = resumes.path_for(find(db, application_id)["resume_filename"])
    if path is None:
        raise NotFound("No attachment for this application.")
    if not path.exists():
        raise NotFound("The attachment file is missing (data resets on restart).")
    return path


# ------------------------------------------
# 3. Reviewing
# ------------------------------------------

def set_status(db, application_id, status, actor):
    application = find(db, application_id)               # NotFound if it doesn't exist
    with transaction(db):
        db.execute("""
            UPDATE applications SET application_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (status, application_id))
        activity.record(db, ActivityKind.APPLICATION_STATUS, actor, project_id=application["project_id"],
                        application_id=application_id, from_status=application["application_status"],
                        to_status=status)
    return {"application_id": application_id, "status": status}
