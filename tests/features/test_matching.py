"""
Move 5 tests: skill matching + the profile that powers it.

The scoring rules are small enough to test case by case, which is exactly what a
team member should be able to explain out loud: "why did Erin get 67%?"
"""

import pytest

from backend.matching.skill_match import score, split_skills
from tests.conftest import login, make_pdf


def test_split_keeps_ci_cd_together_and_drops_duplicates():
    assert split_skills("Python; SQL, docker | CI/CD; python") == ["Python", "SQL", "docker", "CI/CD"]


@pytest.mark.parametrize("required, skills, resume, expected", [
    ("Python; FastAPI; SQL", "python, sql", "", 67),                 # 2 of 3, case does not matter
    ("Python; FastAPI; SQL", "", "Built FastAPI services in Python", 67),   # found in resume text
    ("JavaScript; HTML", "JS, html", "", 100),                        # alias: JS = JavaScript
    ("Java", "", "Senior JavaScript developer", 0),                  # whole words: Java is not JavaScript
    ("R; SQL", "", "Used React and SQL", 50),                         # 'R' does not match inside 'React'
    ("C++", "", "Wrote C++ and C# tools", 100),                       # symbols in skill names work
    ("", "Python", "", 0),                                            # no requirements: never a fake 100%
])
def test_score_rules(required, skills, resume, expected):
    assert score(required, "", skills, resume)["score"] == expected


def test_nice_to_have_is_a_bonus_not_a_penalty():
    result = score("Python", "Docker; Kubernetes", "Python, k8s", "")
    assert result["score"] == 100
    assert result["bonus"] == ["Kubernetes"]
    assert result["missing"] == []


def test_profile_drives_matches_through_the_api(client):
    login(client, "employee")
    before = client.get("/api/insights/matches").json()
    assert before and all(item["score"] == 0 for item in before)        # no skills saved yet

    saved = client.put("/api/applications/profile", json={"skills": "Python, FastAPI, SQL"}).json()
    assert saved == {"skills": "Python, FastAPI, SQL", "resume_on_file": False}

    after = {item["project_id"]: item for item in client.get("/api/insights/matches").json()}
    backend = next(project for project in client.get("/api/projects").json() if project["title"] == "Backend Engineer")
    assert after[backend["id"]]["score"] == 100


def test_resume_text_counts_after_applying(client):
    login(client, "employee")
    project = next(project for project in client.get("/api/projects").json() if project["title"] == "Data Analyst")
    client.post("/api/applications", data={"project_id": project["id"]},
                files={"resume": ("cv.pdf", make_pdf("Experienced with SQL and Excel"), "application/pdf")})

    assert client.get("/api/applications/profile").json()["resume_on_file"] is True
    match = {item["project_id"]: item for item in client.get("/api/insights/matches").json()}[project["id"]]
    assert set(match["matched"]) >= {"SQL", "Excel"}


def test_managers_see_applicants_ranked_by_match(client):
    login(client, "employee")
    project = next(project for project in client.get("/api/projects").json() if project["title"] == "Backend Engineer")
    client.put("/api/applications/profile", json={"skills": "Python, SQL"})
    client.post("/api/applications", data={"project_id": project["id"], "skills": "Python, SQL"})

    login(client, "manager")
    applicant = client.get(f"/api/projects/{project['id']}/applications").json()[0]
    assert applicant["match"]["score"] == 67 and applicant["match"]["missing"] == ["FastAPI"]

    pipeline = next(item for item in client.get("/api/projects/manage").json() if item["id"] == project["id"])
    assert (pipeline["applicant_count"], pipeline["new_count"], pipeline["accepted_count"]) == (1, 1, 0)


def test_profile_and_matches_are_employee_only(client):
    login(client, "manager")
    assert client.get("/api/insights/matches").status_code == 403
    assert client.put("/api/applications/profile", json={"skills": "x"}).status_code == 403
