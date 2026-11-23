import time
from io import BytesIO

import jwt
import pytest
from docx import Document
from fastapi.testclient import TestClient


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Build a TestClient on a fresh database with the given env settings."""
    monkeypatch.setenv("NETWORKER_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("NETWORKER_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("NETWORKER_AVATAR_DIR", str(tmp_path / "avatars"))
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("PM_SELF_SERVICE", raising=False)

    clients = []

    def build(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        from backend.api.main import app

        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield build

    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def sign_in(client, email, name=""):
    """Return auth headers for a dev-mode user (created on first sign-in)."""
    response = client.post("/auth/dev-login", json={"email": email, "display_name": name})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def as_user(client):
    def headers(email, name=""):
        return sign_in(client, email, name)
    return headers


def make_docx(text):
    buffer = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def docx_upload(field, text, name="resume.docx"):
    return {field: (name, make_docx(text), "application/octet-stream")}


class FakeJwks:
    """Stands in for Microsoft's key endpoint in Entra token tests."""

    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": self.public_key})()


def entra_token(private_key, tenant, audience, oid, **claims):
    now = int(time.time())
    payload = {
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "aud": audience,
        "tid": tenant,
        "oid": oid,
        "iat": now,
        "exp": now + 3600,
        "preferred_username": f"{oid}@contoso.com",
        "name": f"User {oid}",
        **claims,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")
