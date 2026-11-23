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

PROJECT_STATUSES = ["Open", "On Hold", "Filled", "Closed"]


def get_database_path():
    # NETWORKER_DB lets tests and deployments point at a different file.
    return Path(os.environ.get("NETWORKER_DB", DEFAULT_DATABASE_PATH))


def get_connection():
    # Each connection serves one request, but FastAPI may open it in a worker
    # thread and use it from the event loop, so allow cross-thread use.
    connection = sqlite3.connect(get_database_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _tables(cursor):
    return {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _columns(cursor, table):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}


USERS_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auth_provider TEXT NOT NULL,
        external_id TEXT NOT NULL,
        email TEXT COLLATE NOCASE,
        display_name TEXT,
        role TEXT NOT NULL DEFAULT 'employee'
            CHECK (role IN ('employee', 'pm', 'admin')),
        skills TEXT DEFAULT '',
        resume_filename TEXT DEFAULT '',
        resume_text TEXT DEFAULT '',
        avatar_filename TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (auth_provider, external_id)
    )
"""

PROJECTS_SQL = """
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
        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        closed_at TIMESTAMP
    )
"""

# Who may manage a project. Every PM query joins through this table.
PROJECT_MANAGERS_SQL = """
    CREATE TABLE IF NOT EXISTS project_managers (
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('owner', 'co_manager')),
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (project_id, user_id)
    )
"""

APPLICATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS {name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        project_id INTEGER NOT NULL REFERENCES projects(id),
        application_status TEXT DEFAULT 'Submitted',
        resume_filename TEXT,
        cover_letter TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, project_id)
    )
"""

# The match score recorded when a user applied to a project.
MATCHES_SQL = """
    CREATE TABLE IF NOT EXISTS {name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        project_id INTEGER NOT NULL REFERENCES projects(id),
        match_score REAL,
        matched_skills TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, project_id)
    )
"""


def _migrate_legacy_schema(cursor):
    """Upgrade databases from before sign-in existed.

    employees becomes users (as dev sign-in users keyed by email), and
    applications/matches are rebuilt to reference users. Returns True if
    projects predate ownership and need an owner assigned.
    """
    tables = _tables(cursor)
    projects_need_owner = False

    if "projects" in tables:
        columns = _columns(cursor, "projects")
        for column, definition in [
            ("created_by", "INTEGER REFERENCES users(id)"),
            ("updated_at", "TIMESTAMP"),
            ("closed_at", "TIMESTAMP"),
        ]:
            if column not in columns:
                cursor.execute(f"ALTER TABLE projects ADD COLUMN {column} {definition}")
                projects_need_owner = True

    if "employees" in tables:
        employee_columns = _columns(cursor, "employees")
        resume_text = "COALESCE(resume_text, '')" if "resume_text" in employee_columns else "''"

        cursor.execute(f"""
            INSERT OR IGNORE INTO users (
                id, auth_provider, external_id, email, display_name,
                skills, resume_filename, resume_text, created_at
            )
            SELECT id, 'dev', LOWER(email), LOWER(email), name,
                COALESCE(skills, ''), COALESCE(resume_filename, ''), {resume_text},
                created_at
            FROM employees
            WHERE email IS NOT NULL
        """)

    for table, sql, columns in [
        ("applications", APPLICATIONS_SQL,
         "id, user_id, project_id, application_status, resume_filename, "
         "cover_letter, submitted_at, updated_at"),
        ("matches", MATCHES_SQL,
         "id, user_id, project_id, match_score, matched_skills, created_at"),
    ]:
        if table in tables and "employee_id" in _columns(cursor, table):
            cursor.execute(sql.format(name=f"{table}_new"))
            cursor.execute(f"""
                INSERT OR IGNORE INTO {table}_new ({columns})
                SELECT {columns.replace("user_id", "employee_id")} FROM {table}
                WHERE employee_id IN (SELECT id FROM users)
            """)
            cursor.execute(f"DROP TABLE {table}")
            cursor.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

    if "employees" in tables:
        cursor.execute("DROP TABLE employees")

    return projects_need_owner


def create_tables():
    connection = get_connection()
    # Table rebuilds during migration must not trip foreign key checks.
    connection.execute("PRAGMA foreign_keys = OFF")
    cursor = connection.cursor()

    try:
        cursor.execute("BEGIN")
        cursor.execute(USERS_SQL)
        if "avatar_filename" not in _columns(cursor, "users"):
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_filename TEXT DEFAULT ''")
        cursor.execute(PROJECTS_SQL)
        cursor.execute(PROJECT_MANAGERS_SQL)

        projects_need_owner = _migrate_legacy_schema(cursor)

        cursor.execute(APPLICATIONS_SQL.format(name="applications"))
        cursor.execute(MATCHES_SQL.format(name="matches"))

        for statement in [
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_project_managers_user ON project_managers(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_applications_project ON applications(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id)",
        ]:
            cursor.execute(statement)

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    if projects_need_owner:
        assign_unowned_projects_to_sample_owner()


def _sample_owner_id(connection):
    from backend.users import SAMPLE_OWNER, ensure_dev_user

    return ensure_dev_user(
        connection, SAMPLE_OWNER["email"], SAMPLE_OWNER["display_name"], SAMPLE_OWNER["role"]
    )["id"]


def assign_unowned_projects_to_sample_owner():
    """Projects created before ownership existed go to the sample PM."""
    connection = get_connection()

    try:
        owner_id = _sample_owner_id(connection)
        connection.execute(
            "UPDATE projects SET created_by = ? WHERE created_by IS NULL", (owner_id,)
        )
        connection.execute("""
            INSERT OR IGNORE INTO project_managers (project_id, user_id, role)
            SELECT id, created_by, 'owner' FROM projects
            WHERE id NOT IN (SELECT project_id FROM project_managers)
        """)
        connection.commit()
    finally:
        connection.close()


def seed_dev_users():
    from backend.users import DEV_USERS, ensure_dev_user

    connection = get_connection()
    try:
        for user in DEV_USERS:
            ensure_dev_user(connection, user["email"], user["display_name"], user["role"])
    finally:
        connection.close()


def seed_sample_projects():
    """Load the sample roles into an empty projects table, owned by the
    sample PM. Returns the number of roles inserted."""
    connection = get_connection()

    try:
        existing = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

        if existing or not SAMPLE_PROJECTS_PATH.exists():
            return 0

        owner_id = _sample_owner_id(connection)
        projects = json.loads(SAMPLE_PROJECTS_PATH.read_text(encoding="utf-8"))

        for project in projects:
            project_id = connection.execute(
                f"""
                INSERT INTO projects ({", ".join(PROJECT_COLUMNS)}, created_by)
                VALUES ({", ".join("?" for _ in PROJECT_COLUMNS)}, ?)
                """,
                [project.get(column, "") for column in PROJECT_COLUMNS] + [owner_id],
            ).lastrowid

            connection.execute(
                "INSERT INTO project_managers (project_id, user_id, role) VALUES (?, ?, 'owner')",
                (project_id, owner_id),
            )

        connection.commit()
        return len(projects)

    finally:
        connection.close()


if __name__ == "__main__":
    create_tables()
    print(f"Database ready at {get_database_path()}")
    print(f"Sample roles added: {seed_sample_projects()}")
