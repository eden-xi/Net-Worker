"""
Move 3 tests: identity as dependencies.

What we prove:
  - DEFAULT DENY: every API route (found automatically, so new ones are covered too)
    refuses a visitor who is not signed in, except login itself and /health
  - every manager route refuses an employee
  - nobody can apply, or read applications, as someone else
  - sessions end on logout and on expiry
  - no other website is allowed to call the API from a browser
"""

import re
import time

import pytest
from fastapi.routing import APIRoute

from backend.app import api
from backend.core import config, security
from tests.conftest import login, make_pdf

PUBLIC = {"/auth/login", "/auth/me", "/auth/mode", "/auth/logout", "/health"}

MANAGER_ROUTES = [
    ("GET", "/api/projects/manage"),
    ("POST", "/api/projects"),
    ("POST", "/api/projects/upload-csv"),
    ("PATCH", "/api/projects/1/status"),
    ("GET", "/api/projects/1/applications"),
    ("GET", "/api/applications/1/document"),
    ("GET", "/api/applications/1/attachment"),
    ("PATCH", "/api/applications/1/status"),
    ("GET", "/api/insights/activity"),
]


def every_api_route():
    """(method, path) for every route in backend/app.py, with {ids} filled in as 1."""
    for route in api.routes:
        if isinstance(route, APIRoute) and route.path not in PUBLIC:
            for method in route.methods:
                yield method, "/api" + re.sub(r"\{[^}]+\}", "1", route.path)


def test_every_route_needs_sign_in(client):
    routes = list(every_api_route())
    assert len(routes) >= 11                       # if routes vanish, this test must notice

    for method, path in routes:
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code} without a login"


@pytest.mark.parametrize("method, path", MANAGER_ROUTES)
def test_employees_cannot_use_manager_routes(client, method, path):
    login(client, "employee")
    assert client.request(method, path).status_code == 403


def test_every_manager_only_route_is_in_the_list_above(client):
    """If someone adds a manager route, it must be added to MANAGER_ROUTES (and so get tested)."""
    login(client, "employee")
    refused = {(method, path) for method, path in every_api_route()
               if client.request(method, path).status_code == 403}
    assert refused == set(MANAGER_ROUTES)


def test_managers_cannot_apply(client):
    login(client, "manager")
    response = client.post("/api/applications", data={"project_id": 1})
    assert response.status_code == 403


def test_nobody_can_apply_as_someone_else(client):
    login(client, "employee")                                             # Erin
    project_id = client.get("/api/projects").json()[0]["id"]
    response = client.post("/api/applications", data={
        "project_id": project_id,
        "name": "Mallory", "email": "employee2@networker.test",          # spoof attempt: ignored
    }, files={"resume": ("cv.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 201

    login(client, "manager")
    applicant = client.get(f"/api/projects/{project_id}/applications").json()[0]
    assert (applicant["name"], applicant["email"]) == ("Erin Employee", "employee@networker.test")


def test_my_applications_only_shows_my_own(client):
    login(client, "employee")
    project_id = client.get("/api/projects").json()[0]["id"]
    client.post("/api/applications", data={"project_id": project_id})

    login(client, "employee", email="employee2@networker.test", password="employee-demo")
    assert client.get("/api/applications/mine?email=employee@networker.test").json() == []   # query ignored


def test_logout_ends_the_session_on_the_server(client):
    login(client, "employee")
    token = client.cookies.get(config.COOKIE_NAME)
    client.post("/api/auth/logout")

    client.cookies.set(config.COOKIE_NAME, token)                 # replay the old cookie
    assert client.get("/api/projects").status_code == 401


def test_expired_session_is_refused(client):
    login(client, "employee")
    token = client.cookies.get(config.COOKIE_NAME)
    security.SESSIONS[token]["expires_at"] = time.time() - 1
    assert client.get("/api/projects").status_code == 401
    assert token not in security.SESSIONS


@pytest.mark.parametrize("email, password, role", [
    ("employee@networker.test", "employee-demo", "manager"),          # right person, wrong role
    ("employee@networker.test", "wrong", "employee"),
    ("nobody@networker.test", "employee-demo", "employee"),
])
def test_bad_logins_are_refused(client, email, password, role):
    response = client.post("/api/auth/login", json={"email": email, "password": password, "role": role})
    assert response.status_code == 401


def test_open_login_mode_accepts_anyone(client, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_MODE", "open")
    user = login(client, "manager", email="new.person@company.test", password="anything")
    assert (user["name"], user["role"]) == ("New Person", "manager")


def test_other_websites_get_no_cors_permission(client):
    response = client.get("/api/auth/mode", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
