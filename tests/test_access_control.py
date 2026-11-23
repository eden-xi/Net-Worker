"""PMs reach only projects they own or co-manage, whatever IDs they try."""

import pytest

from conftest import docx_upload

ALEX = "alex@example.com"
PRIYA = "priya.pm@example.com"   # owns the sample roles
SAM = "sam.pm@example.com"       # PM with no projects


@pytest.fixture
def setup(client, as_user):
    alex, priya, sam = as_user(ALEX), as_user(PRIYA), as_user(SAM)

    project = client.get("/pm/projects", headers=priya).json()[0]
    application = client.post(
        "/applications",
        data={"project_id": project["id"], "cover_letter": "Pick me"},
        files=docx_upload("resume", "SQL and Excel"),
        headers=alex,
    ).json()

    return {
        "client": client, "alex": alex, "priya": priya, "sam": sam,
        "project_id": project["id"], "application_id": application["application_id"],
    }


def test_pm_dashboard_lists_only_own_projects(setup):
    client = setup["client"]
    assert len(client.get("/pm/projects", headers=setup["priya"]).json()) == 19
    assert client.get("/pm/projects", headers=setup["sam"]).json() == []


@pytest.mark.parametrize("method, path, body", [
    ("get", "/pm/projects/{p}", None),
    ("patch", "/pm/projects/{p}", {"title": "Taken over"}),
    ("post", "/pm/projects/{p}/close", None),
    ("post", "/pm/projects/{p}/reopen", None),
    ("get", "/pm/projects/{p}/managers", None),
    ("post", "/pm/projects/{p}/managers", {"email": SAM}),
    ("delete", "/pm/projects/{p}/managers/1", None),
    ("get", "/pm/projects/{p}/applications", None),
    ("patch", "/pm/applications/{a}/status", {"status": "Accepted"}),
    ("get", "/pm/applications/{a}/resume", None),
])
def test_other_pms_get_404_for_every_project_route(setup, method, path, body):
    client = setup["client"]
    url = path.format(p=setup["project_id"], a=setup["application_id"])
    kwargs = {"json": body} if body is not None else {}

    for headers in (setup["sam"], setup["alex"]):
        response = getattr(client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 404, (url, response.text)

    # Same answer as a project that does not exist, so IDs reveal nothing.
    missing = path.format(p=999999, a=999999)
    assert getattr(client, method)(missing, headers=setup["sam"], **kwargs).status_code == 404

    # And nothing changed.
    project = client.get(f"/pm/projects/{setup['project_id']}", headers=setup["priya"]).json()
    assert project["title"] != "Taken over"


def test_owner_can_manage_applicants(setup):
    client, priya = setup["client"], setup["priya"]

    applicants = client.get(f"/pm/projects/{setup['project_id']}/applications", headers=priya).json()
    assert [a["email"] for a in applicants] == [ALEX]
    assert applicants[0]["has_resume"] is True
    assert "resume_text" not in applicants[0]

    listed = next(p for p in client.get("/pm/projects", headers=priya).json() if p["id"] == setup["project_id"])
    assert (listed["applicant_count"], listed["new_applicant_count"]) == (1, 1)

    response = client.patch(
        f"/pm/applications/{setup['application_id']}/status", json={"status": "Accepted"}, headers=priya
    )
    assert response.status_code == 200

    listed = next(p for p in client.get("/pm/projects", headers=priya).json() if p["id"] == setup["project_id"])
    assert listed["new_applicant_count"] == 0

    resume = client.get(f"/pm/applications/{setup['application_id']}/resume", headers=priya)
    assert resume.status_code == 200
    assert resume.content.startswith(b"PK")

    tracked = client.get("/me/applications", headers=setup["alex"]).json()
    assert tracked[0]["status"] == "Accepted"


def test_co_manager_access_and_limits(setup):
    client, priya, sam = setup["client"], setup["priya"], setup["sam"]
    project_id = setup["project_id"]

    managers = client.post(
        f"/pm/projects/{project_id}/managers", json={"email": SAM}, headers=priya
    ).json()
    assert {m["email"] for m in managers} == {PRIYA, SAM}

    # Sam now sees exactly that one project, and its applicants.
    assert [p["id"] for p in client.get("/pm/projects", headers=sam).json()] == [project_id]
    assert client.get(f"/pm/projects/{project_id}/applications", headers=sam).status_code == 200
    assert client.patch(f"/pm/projects/{project_id}", json={"location": "Remote"}, headers=sam).status_code == 200

    # Co-managers cannot add managers or remove the owner.
    assert client.post(
        f"/pm/projects/{project_id}/managers", json={"email": ALEX}, headers=sam
    ).status_code == 403

    priya_id = client.get("/me", headers=priya).json()["id"]
    sam_id = client.get("/me", headers=sam).json()["id"]
    assert client.delete(f"/pm/projects/{project_id}/managers/{priya_id}", headers=sam).status_code == 403

    # Owner removes Sam; access is gone.
    assert client.delete(f"/pm/projects/{project_id}/managers/{sam_id}", headers=priya).status_code == 200
    assert client.get(f"/pm/projects/{project_id}", headers=sam).status_code == 404


def test_create_edit_close_project(setup):
    client, sam = setup["client"], setup["sam"]

    created = client.post("/pm/projects", json={
        "role_id": "SAM-100", "title": "Platform Engineer", "required_skills": "Go; Kubernetes",
        "seniority": "Senior", "location": "Remote",
    }, headers=sam)
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["my_role"] == "owner"

    assert client.post("/pm/projects", json={"role_id": "SAM-100", "title": "Dup"}, headers=sam).status_code == 409

    edited = client.patch(f"/pm/projects/{project['id']}", json={"title": "Staff Platform Engineer"}, headers=sam)
    assert edited.json()["title"] == "Staff Platform Engineer"

    closed = client.post(f"/pm/projects/{project['id']}/close", headers=sam).json()
    assert closed["status"] == "Closed" and closed["closed_at"]

    open_ids = [p["id"] for p in client.get("/projects", headers=setup["alex"]).json()]
    assert project["id"] not in open_ids

    reopened = client.post(f"/pm/projects/{project['id']}/reopen", headers=sam).json()
    assert reopened["status"] == "Open" and reopened["closed_at"] is None


def test_employee_cannot_create_projects_until_they_become_pm(setup):
    client, alex = setup["client"], setup["alex"]
    body = {"role_id": "ALEX-1", "title": "Side project"}

    assert client.post("/pm/projects", json=body, headers=alex).status_code == 403
    assert client.get("/me", headers=alex).json()["can_become_pm"] is True

    promoted = client.post("/me/become-pm", headers=alex).json()
    assert promoted["role"] == "pm" and promoted["can_become_pm"] is False

    assert client.post("/pm/projects", json=body, headers=alex).status_code == 201
    # A new PM sees only their own project, not anyone else's.
    assert [p["role_id"] for p in client.get("/pm/projects", headers=alex).json()] == ["ALEX-1"]


def test_self_service_can_be_turned_off(make_client):
    from conftest import sign_in

    client = make_client(PM_SELF_SERVICE="0")
    alex = sign_in(client, ALEX)

    assert client.get("/me", headers=alex).json()["can_become_pm"] is False
    assert client.post("/me/become-pm", headers=alex).status_code == 403


def test_admin_manages_roles_but_not_projects(client, as_user):
    admin, alex = as_user("avery.admin@example.com"), as_user(ALEX)

    assert client.get("/admin/users", headers=alex).status_code == 403

    users = {u["email"]: u for u in client.get("/admin/users", headers=admin).json()}
    assert users[PRIYA]["managed_projects"] == 19

    alex_id = users[ALEX]["id"]
    assert client.patch(f"/admin/users/{alex_id}/role", json={"role": "pm"}, headers=admin).status_code == 200
    assert client.get("/me", headers=alex).json()["role"] == "pm"

    own_id = users["avery.admin@example.com"]["id"]
    assert client.patch(f"/admin/users/{own_id}/role", json={"role": "employee"}, headers=admin).status_code == 400

    # Admin is not a back door into other people's projects.
    project_id = client.get("/pm/projects", headers=as_user(PRIYA)).json()[0]["id"]
    assert client.get(f"/pm/projects/{project_id}", headers=admin).status_code == 404
