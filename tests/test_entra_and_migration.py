"""Entra ID token validation (with locally generated keys) and upgrading a
database from before sign-in existed."""

import sqlite3
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from conftest import FakeJwks, entra_token

TENANT = "11111111-1111-1111-1111-111111111111"
AUDIENCE = "api://localhost/22222222-2222-2222-2222-222222222222"


@pytest.fixture
def entra(make_client):
    from backend import auth

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = make_client(AUTH_MODE="entra", ENTRA_TENANT_ID=TENANT, ENTRA_AUDIENCE=AUDIENCE)
    auth.set_entra_verifier(auth.EntraVerifier(TENANT, [AUDIENCE], FakeJwks(key.public_key())))

    def headers(oid="user-1", signing_key=key, **claims):
        token = entra_token(signing_key, claims.pop("tid", TENANT), claims.pop("aud", AUDIENCE), oid, **claims)
        return {"Authorization": f"Bearer {token}"}

    yield client, headers
    auth.set_entra_verifier(None)


def test_valid_token_signs_in_and_creates_user(entra):
    client, headers = entra
    me = client.get("/me", headers=headers("abc")).json()

    assert me["email"] == "abc@contoso.com"
    assert me["display_name"] == "User abc"
    assert me["role"] == "employee"

    # Same object ID, same user.
    assert client.get("/me", headers=headers("abc")).json()["id"] == me["id"]


def test_v1_token_issuer_accepted(entra):
    client, headers = entra
    response = client.get("/me", headers=headers(iss=f"https://sts.windows.net/{TENANT}/"))
    assert response.status_code == 200


@pytest.mark.parametrize("claims", [
    {"tid": "99999999-9999-9999-9999-999999999999"},
    {"aud": "api://someone-else"},
    {"iss": "https://login.microsoftonline.com/other/v2.0"},
    {"exp": int(time.time()) - 3600},
])
def test_bad_tokens_rejected(entra, claims):
    client, headers = entra
    assert client.get("/me", headers=headers(**claims)).status_code == 401


def test_token_signed_by_another_key_rejected(entra):
    client, headers = entra
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.get("/me", headers=headers(signing_key=other_key)).status_code == 401


def test_dev_token_rejected_in_entra_mode(entra):
    client, _ = entra
    from backend.auth import issue_dev_token

    assert client.get("/me", headers={"Authorization": f"Bearer {issue_dev_token(1)}"}).status_code == 401


def test_entra_app_roles_grant_access(entra):
    client, headers = entra
    pm = headers("pm-user", roles=["ProjectManager"])

    assert client.get("/me", headers=pm).json()["role"] == "pm"
    created = client.post("/pm/projects", json={"role_id": "E-1", "title": "Entra role"}, headers=pm)
    assert created.status_code == 201


LEGACY_SCHEMA = """
CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, role_id TEXT UNIQUE, title TEXT NOT NULL,
  client_project TEXT, required_skills TEXT, nice_to_have_skills TEXT, seniority TEXT, location TEXT,
  start_date TEXT, status TEXT DEFAULT 'Open', description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, skills TEXT,
  resume_filename TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resume_text TEXT DEFAULT '');
CREATE TABLE matches (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER, project_id INTEGER,
  match_score REAL, matched_skills TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
  project_id INTEGER NOT NULL, application_status TEXT DEFAULT 'Submitted', resume_filename TEXT,
  cover_letter TEXT, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(employee_id, project_id));
INSERT INTO projects (role_id, title, required_skills, status) VALUES ('OLD-1', 'Legacy Role', 'SQL', 'Open');
INSERT INTO employees (name, email, skills) VALUES ('Jo Legacy', 'Jo@Example.com', 'SQL');
INSERT INTO applications (employee_id, project_id, cover_letter) VALUES (1, 1, 'hello');
"""


def test_legacy_database_is_upgraded(tmp_path, make_client):
    db_path = tmp_path / "test.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(LEGACY_SCHEMA)
    connection.close()

    from conftest import sign_in

    client = make_client()

    connection = sqlite3.connect(db_path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "employees" not in tables
    assert "user_id" in {row[1] for row in connection.execute("PRAGMA table_info(applications)")}
    connection.close()

    # The old employee can sign in by email and still sees their application.
    jo = sign_in(client, "jo@example.com")
    assert client.get("/me", headers=jo).json()["skills"] == ["SQL"]
    assert [a["project_title"] for a in client.get("/me/applications", headers=jo).json()] == ["Legacy Role"]

    # Ownerless legacy projects now belong to the sample PM.
    priya = sign_in(client, "priya.pm@example.com")
    assert [p["role_id"] for p in client.get("/pm/projects", headers=priya).json()] == ["OLD-1"]
