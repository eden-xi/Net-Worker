from backend.matching import Candidate, detect_skills, rank_projects, score_project, split_skills

PROJECT = {
    "required_skills": "Python; SQL; Docker; PostgreSQL",
    "nice_to_have_skills": "FastAPI; AWS",
}


def test_split_skills_handles_separators_and_duplicates():
    assert split_skills("SQL; Excel, Power BI | sql\nPython") == [
        "SQL", "Excel", "Power BI", "Python",
    ]
    assert split_skills("") == []
    assert split_skills(None) == []


def test_full_match_scores_100():
    candidate = Candidate("python, sql, docker, postgresql, fastapi, aws")
    assert score_project(PROJECT, candidate)["score"] == 100


def test_required_skills_weigh_more_than_nice_to_have():
    only_required = score_project(PROJECT, Candidate("Python, SQL, Docker, PostgreSQL"))
    only_nice = score_project(PROJECT, Candidate("FastAPI, AWS"))

    assert only_required["score"] == 80
    assert only_nice["score"] == 20
    assert only_nice["missing_required"] == ["Python", "SQL", "Docker", "PostgreSQL"]


def test_aliases_match():
    match = score_project(PROJECT, Candidate("postgres, py, sql"))
    assert "PostgreSQL" in match["matched_required"]


def test_resume_text_counts_as_evidence():
    resume = "Built REST services in Python and deployed them with Docker on AWS."
    match = score_project(PROJECT, Candidate("SQL", resume))

    assert match["matched_required"] == ["Python", "SQL", "Docker"]
    assert match["matched_nice_to_have"] == ["AWS"]


def test_short_ambiguous_skills_are_not_found_in_prose():
    project = {"required_skills": "Go; Kubernetes", "nice_to_have_skills": ""}
    resume = "Ready to go the extra mile. Ran workloads on k8s."

    match = score_project(project, Candidate("", resume))
    assert match["matched_required"] == ["Kubernetes"]

    # Listed explicitly as a skill, Go still matches.
    assert score_project(project, Candidate("golang, kubernetes"))["score"] == 100


def test_whole_word_matching():
    project = {"required_skills": "Java", "nice_to_have_skills": ""}
    assert score_project(project, Candidate("", "Wrote JavaScript apps"))["score"] == 0


def test_project_without_skills_scores_zero():
    assert score_project({}, Candidate("Python"))["score"] == 0


def test_rank_projects_orders_best_first():
    projects = [
        {"id": 1, "required_skills": "Java", "nice_to_have_skills": ""},
        {"id": 2, "required_skills": "Python", "nice_to_have_skills": ""},
    ]
    ranked = rank_projects(projects, Candidate("python"))
    assert [project["id"] for project in ranked] == [2, 1]


def test_detect_skills():
    text = "Experienced with Power BI, DAX and Excel dashboards."
    assert detect_skills(text, ["SQL", "Power BI", "DAX", "Excel", "excel"]) == [
        "Power BI", "DAX", "Excel",
    ]
