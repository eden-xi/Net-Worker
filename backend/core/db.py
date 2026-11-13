"""
The database: how to connect, and what the tables look like.

Two ways to get a connection:
  - connect()  for scripts and startup code. You close it yourself.
  - get_db()   for routes:  def route(db = Depends(get_db))
               FastAPI opens it before the route runs and ALWAYS closes it after,
               even if the route raises an error. No route ever calls close().

create_tables() runs once at startup. It builds missing tables and adds
missing columns, so an older database file keeps working.
"""

import sqlite3
import threading
from contextlib import contextmanager

from backend.core import config
from backend.schemas.applications import ApplicationStatus
from backend.schemas.projects import ProjectStatus


def connect():
    # check_same_thread=False: FastAPI may open the connection in one worker thread
    # and run the route in another. Each request still gets its OWN connection.
    # timeout=10: if another request is writing, wait up to 10 s instead of failing.
    connection = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False, timeout=10)
    connection.row_factory = sqlite3.Row           # rows behave like dicts: row["title"]
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db():
    """FastAPI dependency: one connection per request, always closed afterwards."""
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()


# SQLite lets only ONE request write at a time. Without this lock, requests that collide
# sleep and retry on a timer, and a busy moment turns into multi-second waits.
# With it, writers simply queue in order. (One lock per server process; we run one.)
WRITE_LOCK = threading.Lock()


@contextmanager
def transaction(connection):
    """Group writes:  with transaction(db): ...   One writer at a time, commit at the end,
    and roll back everything inside the block if any error happens."""
    with WRITE_LOCK:
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


# ------------------------------------------
# Schema
# ------------------------------------------

TABLES = [
    """
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
        posted_by_email TEXT,
        posted_by_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        skills TEXT,
        resume_filename TEXT,
        resume_text TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
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
    """,
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS idx_applications_project ON applications(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_applications_employee ON applications(employee_id)",
]

# Columns added after the first version. Older database files get them on startup.
# (table, column, definition)
ADDED_COLUMNS = [
    ("employees", "resume_text", "TEXT DEFAULT ''"),
    ("projects", "posted_by_email", "TEXT"),
    ("projects", "posted_by_name", "TEXT"),
]


def column_names(connection, table):
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def add_missing_columns(connection):
    for table, column, definition in ADDED_COLUMNS:
        if column not in column_names(connection, table):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def copy_old_marketplace_posters(connection):
    """Phase 2 kept 'who posted this listing' in a side table. Copy it onto projects."""
    old_table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'marketplace_listings'"
    ).fetchone()

    if old_table:
        connection.execute("""
            UPDATE projects
            SET posted_by_email = (SELECT posted_by_email FROM marketplace_listings
                                   WHERE marketplace_listings.project_id = projects.id),
                posted_by_name = (SELECT posted_by_name FROM marketplace_listings
                                  WHERE marketplace_listings.project_id = projects.id)
            WHERE posted_by_email IS NULL
        """)


def normalize_statuses(connection):
    """Older rows hold free text like 'open ' or 'OPEN'. Rewrite them to the exact enum values,
    so the rest of the code can compare with  status = 'Open'  instead of LOWER(TRIM(status))."""
    for status in ProjectStatus:
        connection.execute("UPDATE projects SET status = ? WHERE LOWER(TRIM(status)) = LOWER(?)",
                           (status, status))
    # Blank means Open (the old default); anything unrecognised is hidden as Closed.
    connection.execute("UPDATE projects SET status = 'Open' WHERE status IS NULL OR TRIM(status) = ''")
    connection.execute("UPDATE projects SET status = 'Closed' WHERE status NOT IN (?, ?, ?)", tuple(ProjectStatus))

    for status in ApplicationStatus:
        connection.execute("UPDATE applications SET application_status = ? "
                           "WHERE LOWER(TRIM(application_status)) = LOWER(?)", (status, status))
    connection.execute("UPDATE applications SET application_status = 'Submitted' "
                       "WHERE application_status IS NULL OR application_status NOT IN (?, ?, ?, ?)",
                       tuple(ApplicationStatus))


def create_tables():
    """Build or upgrade the database. Safe to run any number of times."""
    config.ensure_data_folders()
    connection = connect()

    try:
        # WAL mode lets readers keep reading while one request writes.
        connection.execute("PRAGMA journal_mode = WAL")

        for statement in TABLES:
            connection.execute(statement)

        add_missing_columns(connection)
        copy_old_marketplace_posters(connection)
        normalize_statuses(connection)
        connection.commit()
    finally:
        connection.close()
