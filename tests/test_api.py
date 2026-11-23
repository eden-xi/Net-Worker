"""Employee flows, sign-in, headers, and CSV import."""

from conftest import docx_upload

ALEX = "alex@example.com"          # seeded employee
PRIYA = "priya.pm@example.com"     # seeded PM who owns the sample roles


def first_project(client, headers, title="Data Analyst"):
    return next(p for p in client.get("/projects", headers=headers).json() if p["title"] == title)


def set_skills(client, headers, *skills):
    response = client.put("/me", json={"skills": list(skills)}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_api_requires_sign_in(client):
    for method, path in [
        ("get", "/projects"), ("get", "/me"), ("get", "/me/applications"),
        ("get", "/pm/projects"), ("get", "/admin/users"), ("post", "/applications"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path

    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/me", headers=bad).status_code == 401


def test_sample_roles_seeded_and_only_open_ones_listed(client, as_user):
    projects = client.get("/projects", headers=as_user(ALEX)).json()
    assert len(projects) == 15
    assert all(p["status"] == "Open" for p in projects)


def test_dev_sign_in_keeps_existing_name(client, as_user):
    assert client.get("/me", headers=as_user(ALEX)).json()["display_name"] == "Alex Rivera"
    renamed = as_user(ALEX, "Alex R.")
    assert client.get("/me", headers=renamed).json()["display_name"] == "Alex R."


def test_dev_config_lists_test_users(client):
    config = client.get("/auth/config").json()
    assert config["mode"] == "dev"
    assert {u["email"] for u in config["dev_users"]} >= {ALEX, PRIYA}


def test_website_served_with_teams_friendly_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "ProjectHub" in response.text

    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'self' https://teams.microsoft.com" in csp
    assert "script-src 'self'" in csp
    assert "x-frame-options" not in response.headers


def test_recommendations_rank_by_profile_skills(client, as_user):
    alex = as_user(ALEX)
    set_skills(client, alex, "Power BI", "DAX", "SQL", "Excel", "Data Cleaning")

    ranked = client.get("/me/recommendations", headers=alex).json()

    assert ranked[0]["title"] == "Data Analyst"
    assert ranked[0]["match"]["score"] == 80
    scores = [p["match"]["score"] for p in ranked]
    assert scores == sorted(scores, reverse=True)
    assert min(scores) >= 1

    filtered = client.get("/me/recommendations", params={"location": "Remote"}, headers=alex).json()
    assert filtered and all(p["location"] == "Remote" for p in filtered)


def test_resume_upload_suggests_skills_and_years(client, as_user):
    alex = as_user(ALEX)
    set_skills(client, alex, "Python")

    response = client.post(
        "/me/resume",
        files=docx_upload("file", "7 years of experience with Python, Terraform and Kubernetes."),
        headers=alex,
    )
    result = response.json()

    assert response.status_code == 200, response.text
    assert {"Terraform", "Kubernetes"} <= set(result["new_skills"])
    assert "Python" not in result["new_skills"]
    assert result["years_of_experience"] == 7
    assert client.get("/me", headers=alex).json()["has_resume"] is True


def test_apply_uses_profile_and_records_match(client, as_user):
    alex = as_user(ALEX)
    set_skills(client, alex, "SQL", "Excel", "Power BI", "Data Cleaning")
    project = first_project(client, alex)

    response = client.post("/applications", data={"project_id": project["id"]}, headers=alex)

    assert response.status_code == 200, response.text
    assert response.json()["match_score"] == 80
    assert first_project(client, alex)["applied"] == 1

    mine = client.get("/me/applications", headers=alex).json()
    assert [a["project_title"] for a in mine] == ["Data Analyst"]


def test_cannot_apply_as_someone_else(client, as_user):
    """The applicant is the signed-in user; form fields cannot change that."""
    alex, priya = as_user(ALEX), as_user(PRIYA)
    set_skills(client, priya, "Leadership")
    project = first_project(client, alex)

    client.post(
        "/applications",
        data={"project_id": project["id"], "email": PRIYA, "name": "Not Priya"},
        headers=alex,
    )

    assert client.get("/me", headers=priya).json()["skills"] == ["Leadership"]
    assert client.get("/me/applications", headers=priya).json() == []


def test_duplicate_and_closed_project_applications(client, as_user):
    alex = as_user(ALEX)
    project = first_project(client, alex)

    assert client.post("/applications", data={"project_id": project["id"]}, headers=alex).status_code == 200
    assert client.post("/applications", data={"project_id": project["id"]}, headers=alex).status_code == 409

    filled = next(
        p for p in client.get("/pm/projects", headers=as_user(PRIYA)).json() if p["status"] == "Filled"
    )
    assert client.post("/applications", data={"project_id": filled["id"]}, headers=alex).status_code == 404
    assert client.get(f"/projects/{filled['id']}", headers=alex).status_code == 404


def test_invalid_resume_uploads(client, as_user):
    alex = as_user(ALEX)
    project = first_project(client, alex)

    fake_pdf = {"resume": ("resume.pdf", b"not a pdf", "application/pdf")}
    exe = {"resume": ("resume.exe", b"MZ", "application/octet-stream")}

    for files in (fake_pdf, exe):
        response = client.post(
            "/applications", data={"project_id": project["id"]}, files=files, headers=alex
        )
        assert response.status_code == 400


def test_dev_login_disabled_in_entra_mode(make_client):
    client = make_client(AUTH_MODE="entra", ENTRA_TENANT_ID="t", ENTRA_CLIENT_ID="c")
    response = client.post("/auth/dev-login", json={"email": ALEX})
    assert response.status_code == 404
    assert "dev_users" not in client.get("/auth/config").json()


def test_csv_import_owned_by_uploader_and_never_overwrites_others(client, as_user):
    sam = as_user("sam.pm@example.com")
    csv_text = (
        "Job ID,Job Title,Skills,Status\n"
        "SAM-1,Rust Developer,Rust; Linux,Open\n"
        "SMP-001,Hijacked Title,Nothing,Filled\n"
        ",Missing ID,,Open\n"
    )

    result = client.post(
        "/pm/projects/upload-csv",
        files={"file": ("roles.csv", csv_text.encode(), "text/csv")},
        headers=sam,
    ).json()

    assert (result["imported"], result["updated"], result["skipped"]) == (1, 0, 2)
    assert result["conflict_rows"] == [3]

    assert [p["role_id"] for p in client.get("/pm/projects", headers=sam).json()] == ["SAM-1"]

    priya_titles = [p["title"] for p in client.get("/pm/projects", headers=as_user(PRIYA)).json()]
    assert "Hijacked Title" not in priya_titles


def test_csv_reupload_updates_own_projects(client, as_user):
    priya = as_user(PRIYA)
    csv_text = "Role ID,Title,Status\nSMP-001,Data Analyst,Filled\n"

    result = client.post(
        "/pm/projects/upload-csv",
        files={"file": ("roles.csv", csv_text.encode(), "text/csv")},
        headers=priya,
    ).json()

    assert result["updated"] == 1
    analyst = next(p for p in client.get("/pm/projects", headers=priya).json() if p["role_id"] == "SMP-001")
    assert analyst["status"] == "Filled"
    assert analyst["client_project"] == "Summit Retail Group - Sales Reporting"
