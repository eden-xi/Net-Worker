"""
Move 1 tests: backend/core (settings + database foundation).

What we prove:
  - settings come from environment variables
  - create_tables() can run again and again, and upgrades an old database file
  - get_db() always closes its connection, even when the route fails
  - the database module is loaded once (no sys.path hack, no patching)
  - many threads writing at once do not lose rows or hit "database is locked"
"""

import os
import sqlite3
import subprocess
import sys
import threading

import pytest

from backend.core import config
from backend.core.db import connect, create_tables, get_db, column_names


def test_settings_come_from_environment(tmp_path):
    env = {**os.environ, "DATA_DIR": str(tmp_path / "somewhere")}
    output = subprocess.run(
        [sys.executable, "-c", "from backend.core import config; print(config.DATABASE_PATH)"],
        env=env, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert output == str(tmp_path / "somewhere" / "projecthub.db")


def test_create_tables_is_safe_to_repeat(data_dir):
    for _ in range(3):
        create_tables()

    connection = connect()
    tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    connection.close()

    assert {"projects", "employees", "applications", "matches"} <= tables
    assert journal_mode == "wal"
    assert config.RESUME_DIR.is_dir()


def test_old_database_file_is_upgraded(tmp_path, monkeypatch):
    """A phase-2 database: no resume_text / posted_by columns, poster kept in a side table."""
    old_file = tmp_path / "projecthub.db"
    old = sqlite3.connect(old_file)
    old.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY, role_id TEXT UNIQUE, title TEXT NOT NULL,
            client_project TEXT, required_skills TEXT, nice_to_have_skills TEXT, seniority TEXT,
            location TEXT, start_date TEXT, status TEXT DEFAULT 'Open', description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, skills TEXT,
            resume_filename TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE marketplace_listings (project_id INTEGER PRIMARY KEY, posted_by_email TEXT,
            posted_by_name TEXT, created_at TIMESTAMP);
        INSERT INTO projects (id, role_id, title) VALUES (1, 'OLD-1', 'Old listing');
        INSERT INTO marketplace_listings VALUES (1, 'manager@networker.test', 'Morgan Manager', NULL);
    """)
    old.commit()
    old.close()

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", old_file)
    monkeypatch.setattr(config, "RESUME_DIR", tmp_path / "resumes")
    create_tables()

    connection = connect()
    assert "resume_text" in column_names(connection, "employees")
    assert "posted_by_name" in column_names(connection, "projects")
    row = connection.execute("SELECT title, posted_by_name FROM projects WHERE id = 1").fetchone()
    connection.close()
    assert (row["title"], row["posted_by_name"]) == ("Old listing", "Morgan Manager")


def test_get_db_closes_connection_even_on_error(data_dir):
    dependency = get_db()
    connection = next(dependency)
    connection.execute("SELECT 1")

    with pytest.raises(RuntimeError):
        dependency.throw(RuntimeError("the route crashed"))

    with pytest.raises(sqlite3.ProgrammingError):          # "Cannot operate on a closed database."
        connection.execute("SELECT 1")


def test_database_module_loaded_once():
    import deploy.server  # noqa: F401  (importing the server must not create a second copy)
    assert "database" not in sys.modules
    assert "backend.database.database" not in sys.modules


def test_resume_upload_lands_in_data_dir(client):
    from tests.conftest import login, make_pdf

    login(client, "employee")
    project_id = client.get("/api/projects").json()[0]["id"]
    response = client.post("/api/applications", data={
        "project_id": project_id,
    }, files={"resume": ("cv.pdf", make_pdf(), "application/pdf")})

    assert response.status_code == 201, response.text
    stored = list(config.RESUME_DIR.glob("*.pdf"))
    assert len(stored) == 1


def test_many_writers_at_once(data_dir):
    """Stress: 20 threads x 25 inserts each, all at the same time."""
    errors = []

    def writer(thread_number):
        try:
            for row in range(25):
                connection = connect()
                connection.execute(
                    "INSERT INTO employees (name, email) VALUES (?, ?)",
                    (f"Worker {thread_number}", f"w{thread_number}-{row}@load.test"),
                )
                connection.commit()
                connection.close()
        except Exception as error:                      # collected, then reported below
            errors.append(repr(error))

    threads = [threading.Thread(target=writer, args=(number,)) for number in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    connection = connect()
    total = connection.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    connection.close()

    assert errors == []
    assert total == 500
