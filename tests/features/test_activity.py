"""
Move 4 tests: data that survives restarts + the activity log.

What we prove:
  - every change writes exactly one activity row, with WHO made it
  - a change that fails writes NO activity row (same transaction)
  - the feed reads like sentences, and polling with after_id returns only what is new
  - each application has a timeline, oldest step first
  - a restart on the SAME data folder keeps everything; a NEW folder starts fresh
"""

import pytest
from fastapi.testclient import TestClient

from backend.core import config
from backend.core.db import connect
from backend.core.errors import Conflict
from backend.schemas.projects import ProjectIn
from backend.schemas.users import User
from backend.services import activity, applications, projects
from deploy.server import app as server_app
from tests.conftest import login

ERIN = User(email="erin@x.test", name="Erin Employee", role="employee")
MORGAN = User(email="morgan@x.test", name="Morgan Manager", role="manager")


@pytest.fixture
def db(data_dir):
    connection = connect()
    yield connection
    connection.close()


def count_events(db):
    return db.execute("SELECT COUNT(*) FROM activity_events").fetchone()[0]


def test_every_change_is_logged_with_its_author(db):
    listing = projects.create(db, ProjectIn(title="QA Tester"), MORGAN)
    receipt = applications.submit(db, listing["id"], ERIN, "Testing", "", None)
    applications.set_status(db, receipt["application_id"], "Accepted", MORGAN)
    projects.set_status(db, listing["id"], "Filled", MORGAN)

    messages = [event["message"] for event in activity.recent(db)]
    assert messages == [
        "Morgan Manager marked QA Tester as Filled",
        "Morgan Manager moved Erin Employee on QA Tester to Accepted",
        "Erin Employee applied to QA Tester",
        "Morgan Manager posted QA Tester",
    ]


def test_a_failed_change_leaves_no_log_line(db):
    listing = projects.create(db, ProjectIn(title="QA Tester"), MORGAN)
    applications.submit(db, listing["id"], ERIN, "", "", None)
    before = count_events(db)

    with pytest.raises(Conflict):
        applications.submit(db, listing["id"], ERIN, "", "", None)        # duplicate: refused

    assert count_events(db) == before


def test_polling_only_returns_new_events(db):
    listing = projects.create(db, ProjectIn(title="One"), MORGAN)
    newest_seen = activity.recent(db)[0]["id"]
    assert activity.recent(db, after_id=newest_seen) == []                 # nothing new yet

    projects.set_status(db, listing["id"], "Closed", MORGAN)
    new = activity.recent(db, after_id=newest_seen)
    assert [event["kind"] for event in new] == ["listing_status"]


def test_application_timeline_oldest_first(db):
    listing = projects.create(db, ProjectIn(title="Data Analyst"), MORGAN)
    receipt = applications.submit(db, listing["id"], ERIN, "SQL", "", None)
    for status in ["Under Review", "Accepted"]:
        applications.set_status(db, receipt["application_id"], status, MORGAN)

    mine = applications.list_for_email(db, ERIN.email)[0]
    assert [step["status"] for step in mine["timeline"]] == ["Submitted", "Under Review", "Accepted"]
    assert mine["timeline"][-1]["actor_name"] == "Morgan Manager"


def test_feed_endpoint_for_managers_only(client):
    login(client, "manager")
    created = client.post("/api/projects", json={"title": "Teams bot developer"}).json()
    feed = client.get("/api/insights/activity").json()
    assert feed[0]["message"] == f"Morgan Manager posted {created['title']}"

    login(client, "employee")
    assert client.get("/api/insights/activity").status_code == 403


def test_restart_on_the_same_data_folder_keeps_everything(data_dir):
    """What a Render persistent disk gives us: stop the server, start it again, data is still there."""
    with TestClient(server_app) as first_run:
        login(first_run, "manager")
        first_run.post("/api/projects", json={"title": "Survives restarts"})
        since = first_run.get("/api/health").json()["data_since"]

    with TestClient(server_app) as second_run:                     # same DATA_DIR = same disk
        login(second_run, "manager")
        titles = [listing["title"] for listing in second_run.get("/api/projects").json()]
        assert "Survives restarts" in titles
        assert second_run.get("/api/health").json()["data_since"] == since
        assert second_run.get("/api/insights/activity").json()[0]["message"].endswith("Survives restarts")


def test_a_new_data_folder_starts_fresh(data_dir, tmp_path_factory, monkeypatch):
    """What Render's free tier does on every restart: an empty folder, so only the 10 demo listings."""
    with TestClient(server_app) as first_run:
        login(first_run, "manager")
        first_run.post("/api/projects", json={"title": "Will be lost"})

    fresh = tmp_path_factory.mktemp("fresh-disk")
    monkeypatch.setattr(config, "DATA_DIR", fresh)
    monkeypatch.setattr(config, "DATABASE_PATH", fresh / "projecthub.db")
    monkeypatch.setattr(config, "RESUME_DIR", fresh / "resumes")

    with TestClient(server_app) as after_reset:
        login(after_reset, "manager")
        titles = [listing["title"] for listing in after_reset.get("/api/projects").json()]
        assert "Will be lost" not in titles and len(titles) == 10
