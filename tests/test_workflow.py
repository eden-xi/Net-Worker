"""Openings, application statuses, withdrawing, deleting projects, and the
counts that drive the PM dashboard."""

import sqlite3

from conftest import sign_in

ALEX = "alex@example.com"
PRIYA = "priya.pm@example.com"
SAM = "sam.pm@example.com"


def pm_project(client, headers, role_id):
    return next(p for p in client.get("/pm/projects", headers=headers).json() if p["role_id"] == role_id)


def apply(client, headers, project_id):
    response = client.post("/applications", data={"project_id": project_id}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["application_id"]


def test_new_applications_start_as_new_and_statuses_are_validated(client, as_user):
    alex, priya = as_user(ALEX), as_user(PRIYA)
    project = pm_project(client, priya, "SMP-001")
    application_id = apply(client, alex, project["id"])

    assert client.get("/me/applications", headers=alex).json()[0]["status"] == "New"

    for status in ("Shortlisted", "Accepted", "Rejected", "New"):
        response = client.patch(
            f"/pm/applications/{application_id}/status", json={"status": status}, headers=priya
        )
        assert response.status_code == 200, status

    for old_name in ("Submitted", "Under Review", "Withdrawn", ""):
        response = client.patch(
            f"/pm/applications/{application_id}/status", json={"status": old_name}, headers=priya
        )
        assert response.status_code == 400, old_name


def test_counts_for_dashboard_and_nav_badge(client, as_user):
    alex, priya = as_user(ALEX), as_user(PRIYA)
    sam = as_user(SAM)
    project = pm_project(client, priya, "SMP-001")

    first = apply(client, alex, project["id"])
    apply(client, sam, project["id"])

    assert client.get("/me", headers=priya).json()["new_applicants"] == 2
    assert client.get("/me", headers=alex).json()["new_applicants"] == 0

    client.patch(f"/pm/applications/{first}/status", json={"status": "Accepted"}, headers=priya)

    listed = pm_project(client, priya, "SMP-001")
    assert (listed["applicant_count"], listed["new_applicant_count"], listed["accepted_count"]) == (2, 1, 1)
    assert listed["openings"] == 1
    assert client.get("/me", headers=priya).json()["new_applicants"] == 1


def test_openings_on_create_edit_and_validation(client, as_user):
    priya = as_user(PRIYA)

    created = client.post("/pm/projects", json={"role_id": "P-9", "title": "Team", "openings": 3}, headers=priya)
    assert created.status_code == 201 and created.json()["openings"] == 3

    default = client.post("/pm/projects", json={"role_id": "P-10", "title": "Solo"}, headers=priya).json()
    assert default["openings"] == 1

    edited = client.patch(f"/pm/projects/{default['id']}", json={"openings": 4}, headers=priya)
    assert edited.json()["openings"] == 4

    for bad in (0, -1, 501, "many"):
        response = client.patch(f"/pm/projects/{default['id']}", json={"openings": bad}, headers=priya)
        assert response.status_code == 422, bad


def test_csv_sets_openings_and_closed_date(client, as_user):
    priya = as_user(PRIYA)
    csv_text = (
        "Role ID,Title,Headcount,Status\n"
        "SMP-001,Data Analyst,3,Closed\n"
        "NEW-5,Fresh Role,abc,Open\n"
    )

    result = client.post(
        "/pm/projects/upload-csv",
        files={"file": ("roles.csv", csv_text.encode(), "text/csv")},
        headers=priya,
    ).json()
    assert (result["imported"], result["updated"]) == (1, 1)

    analyst = pm_project(client, priya, "SMP-001")
    assert analyst["openings"] == 3
    assert analyst["status"] == "Closed" and analyst["closed_at"]

    fresh = pm_project(client, priya, "NEW-5")
    assert fresh["openings"] == 1  # "abc" ignored
    assert fresh["closed_at"] is None


def test_withdraw_application(client, as_user):
    alex, priya, sam = as_user(ALEX), as_user(PRIYA), as_user(SAM)
    project = pm_project(client, priya, "SMP-001")
    application_id = apply(client, alex, project["id"])

    # Only the applicant can withdraw it.
    assert client.delete(f"/me/applications/{application_id}", headers=sam).status_code == 404
    assert client.delete(f"/me/applications/{application_id}", headers=priya).status_code == 404

    assert client.delete(f"/me/applications/{application_id}", headers=alex).status_code == 200
    assert client.get("/me/applications", headers=alex).json() == []
    assert client.get(f"/pm/projects/{project['id']}/applications", headers=priya).json() == []

    # They can apply again, and a decided application can't be withdrawn.
    again = apply(client, alex, project["id"])
    client.patch(f"/pm/applications/{again}/status", json={"status": "Rejected"}, headers=priya)
    assert client.delete(f"/me/applications/{again}", headers=alex).status_code == 409


def test_delete_project_rules(client, as_user):
    priya, sam, alex = as_user(PRIYA), as_user(SAM), as_user(ALEX)

    mistake = client.post("/pm/projects", json={"role_id": "OOPS-1", "title": "Typo"}, headers=priya).json()
    busy = pm_project(client, priya, "SMP-001")
    apply(client, alex, busy["id"])

    # Someone else's project: 404, as for every PM route.
    assert client.delete(f"/pm/projects/{mistake['id']}", headers=sam).status_code == 404

    # Co-managers can't delete.
    client.post(f"/pm/projects/{mistake['id']}/managers", json={"email": SAM}, headers=priya)
    assert client.delete(f"/pm/projects/{mistake['id']}", headers=sam).status_code == 403

    # Projects with applicants can't be deleted.
    assert client.delete(f"/pm/projects/{busy['id']}", headers=priya).status_code == 409

    assert client.delete(f"/pm/projects/{mistake['id']}", headers=priya).status_code == 200
    assert client.get(f"/pm/projects/{mistake['id']}", headers=priya).status_code == 404
    assert client.get(f"/pm/projects/{mistake['id']}", headers=sam).status_code == 404

    # The Role ID is free again.
    again = client.post("/pm/projects", json={"role_id": "OOPS-1", "title": "Fixed"}, headers=priya)
    assert again.status_code == 201


def test_old_status_names_are_migrated(tmp_path, make_client):
    client = make_client()
    alex = sign_in(client, ALEX)
    priya = sign_in(client, PRIYA)
    project = pm_project(client, priya, "SMP-001")
    application_id = apply(client, alex, project["id"])

    connection = sqlite3.connect(tmp_path / "test.db")
    connection.execute("UPDATE applications SET application_status = 'Under Review' WHERE id = ?", (application_id,))
    connection.commit()
    connection.close()

    from backend.database.database import create_tables
    create_tables()

    assert client.get("/me/applications", headers=alex).json()[0]["status"] == "Shortlisted"
