
import sqlite3
from pathlib import Path

# Find the main ProjectHub folder
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Location of the SQLite database
DATABASE_PATH = PROJECT_ROOT / "backend" / "database" / "projecthub.db"


# Connect to the database
def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    # Enable relationships between database tables
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# Create all database tables
def create_tables():

    connection = get_connection()
    cursor = connection.cursor()

    # ==========================================
    # TABLE 1: PROJECTS
    # Stores available projects and job roles
    # ==========================================

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

    # ==========================================
    # TABLE 2: EMPLOYEES
    # Stores employee profile information
    # ==========================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            skills TEXT,
            resume_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ==========================================
    # TABLE 3: MATCHES
    # Stores project recommendation results
    # ==========================================

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

    # ==========================================
    # TABLE 4: APPLICATIONS
    # Stores employee project applications
    # ==========================================

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

    # Make application searches faster
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

    print("ProjectHub database tables created successfully!")


# Run database setup when this file is executed directly
if __name__ == "__main__":
    create_tables()
