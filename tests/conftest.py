"""
Shared test setup. Run all tests from the repo root:

    python -m pytest -q

Every test gets its OWN empty data folder (database + resumes), so tests never
touch the real database and never affect each other.
"""

import os
import tempfile

# Settings must be in place BEFORE the app is imported.
os.environ.setdefault("ALLOW_NO_AUTH", "1")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="networker-tests-"))

import fitz
import pytest
from fastapi.testclient import TestClient

from backend.core import config
from backend.core.db import create_tables

# The full server (login wall + API + frontend), exactly what runs on Render.
from marketplace.server import app as server_app

TEST_PASSWORDS = {"employee": "employee-demo", "manager": "manager-demo"}
TEST_EMAILS = {"employee": "employee@networker.test", "manager": "manager@networker.test"}
AUTH = "/mp/auth"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point the app at a brand-new, empty data folder for this one test."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "projecthub.db")
    monkeypatch.setattr(config, "RESUME_DIR", tmp_path / "resumes")
    create_tables()
    return tmp_path


@pytest.fixture
def client(data_dir):
    """A browser-like client. Startup runs, so the 10 demo projects are loaded."""
    with TestClient(server_app) as test_client:
        yield test_client


def login(test_client, role="employee", email=None, password=None):
    response = test_client.post(f"{AUTH}/login", json={
        "email": email or TEST_EMAILS[role],
        "password": password or TEST_PASSWORDS[role],
        "role": role,
    })
    assert response.status_code == 200, response.text
    return response.json()["user"]


def make_pdf(text="Test resume: Python, FastAPI, SQL"):
    """A small, real PDF file (bytes) for upload tests."""
    document = fitz.open()
    document.new_page().insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data
