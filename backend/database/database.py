import json
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_PATH = PROJECT_ROOT / "backend" / "database" / "projecthub.db"
SAMPLE_PROJECTS_PATH = PROJECT_ROOT / "frontend" / "sample-projects.json"

PROJECT_COLUMNS = [
    "role_id", "title", "client_project", "required_skills",
    "nice_to_have_skills", "seniority", "location", "start_date",
    "status", "description",
]


def get_database_path():
    # NETWORKER_DB lets tests and deployments point at a different file.
    return Path(os.environ.get("NETWORKER_DB", DEFAULT_DATABASE_PATH))


def get_connection():
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id TEXT UNIQUE,
            title TEXT NOT NULL,
            client_project TEXT,
            required_skills TEXT,
            nice_to_have_skills TEXT,
            seniority TEXT,
            location TEXT,
            start_date TEXT,
            status TEXT DEFAULT 'Open',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            skills TEXT,
            resume_filename TEXT,
            resume_text TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Databases created before resume_text was part of the schema.
    employee_columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(employees)")
    }
    if "resume_text" not in employee_columns:
        cursor.execute(
            "ALTER TABLE employees ADD COLUMN resume_text TEXT DEFAULT ''"
        )

    # One row per (employee, project): the match score computed when the
    # employee applied.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            project_id INTEGER,
            match_score REAL,
            matched_skills TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    cursor.execute("""
        DELETE FROM matches WHERE id NOT IN (
            SELECT MAX(id) FROM matches GROUP BY employee_id, project_id
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_employee_project
        ON matches(employee_id, project_id)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            employee_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,

            application_status TEXT DEFAULT 'Submitted',

            resume_filename TEXT,
            cover_letter TEXT,

            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (project_id) REFERENCES projects(id),

            UNIQUE(employee_id, project_id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_applications_project
        ON applications(project_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_applications_employee
        ON applications(employee_id)
    """)

    connection.commit()
    connection.close()


def seed_sample_projects():
    """Load the sample roles into an empty projects table.

    Returns the number of roles inserted (0 if the table already had data).
    """
    connection = get_connection()

    try:
        existing = connection.execute(
            "SELECT COUNT(*) FROM projects"
        ).fetchone()[0]

        if existing or not SAMPLE_PROJECTS_PATH.exists():
            return 0

        projects = json.loads(SAMPLE_PROJECTS_PATH.read_text(encoding="utf-8"))

        connection.executemany(
            f"""
            INSERT OR IGNORE INTO projects ({", ".join(PROJECT_COLUMNS)})
            VALUES ({", ".join("?" for _ in PROJECT_COLUMNS)})
            """,
            [
                tuple(project.get(column, "") for column in PROJECT_COLUMNS)
                for project in projects
            ],
        )
        connection.commit()
        return len(projects)

    finally:
        connection.close()


if __name__ == "__main__":
    create_tables()
    print(f"Database ready at {get_database_path()}")
    print(f"Sample roles added: {seed_sample_projects()}")
