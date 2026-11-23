"""Skill matching between employees and projects.

A project lists required and nice-to-have skills as text separated by
commas, semicolons, or pipes. An employee matches a skill when it appears in
their skill list, or as a whole word or phrase in their resume text.

The score is 0-100: required skills count for 80% and nice-to-have skills for
20%. If a project lists only one kind, that kind counts for 100%.
"""

import re

REQUIRED_WEIGHT = 0.8
NICE_TO_HAVE_WEIGHT = 0.2

# Common spellings mapped to one canonical name, so "k8s" matches
# "Kubernetes" and "Postgres" matches "PostgreSQL".
SKILL_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "node": "node.js",
    "nodejs": "node.js",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "golang": "go",
    "powerbi": "power bi",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "ml": "machine learning",
    "genai": "generative ai",
    "gen ai": "generative ai",
    "cicd": "ci/cd",
    "ci cd": "ci/cd",
    "rest": "rest apis",
    "rest api": "rest apis",
    "restful apis": "rest apis",
    "restful api": "rest apis",
    "aws sagemaker": "sagemaker",
    "spark": "pyspark",
    "adf": "azure data factory",
    "gcp": "google cloud",
    "automated testing": "test automation",
}

# Skills too short or common to look for in free-form resume text
# ("go" appears in ordinary sentences). They still match from a skill list.
NOT_SEARCHABLE_IN_TEXT = {"go", "r", "c", "ml", "js", "ts", "rest"}

SKILL_SEPARATORS = re.compile(r"[,;|\n]")


def normalize_skill(skill):
    skill = re.sub(r"\s+", " ", str(skill).strip().lower())
    return SKILL_ALIASES.get(skill, skill)


def split_skills(text):
    """Split a skills string into display names, dropping blanks and duplicates."""
    seen = set()
    skills = []

    for part in SKILL_SEPARATORS.split(text or ""):
        part = part.strip()
        key = normalize_skill(part)

        if part and key not in seen:
            seen.add(key)
            skills.append(part)

    return skills


def _text_forms(canonical):
    """Every spelling of a canonical skill worth searching for in text."""
    forms = {canonical}
    forms.update(alias for alias, target in SKILL_ALIASES.items() if target == canonical)
    return {form for form in forms if form not in NOT_SEARCHABLE_IN_TEXT}


def skill_in_text(skill, text):
    if not text:
        return False

    lowered = text.lower()

    for form in _text_forms(normalize_skill(skill)):
        pattern = r"(?<![a-z0-9])" + re.escape(form) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            return True

    return False


class Candidate:
    """An employee's skills and optional resume text, ready for matching."""

    def __init__(self, skills="", resume_text=""):
        if isinstance(skills, str):
            skills = split_skills(skills)

        self.skills = {normalize_skill(skill) for skill in skills if str(skill).strip()}
        self.resume_text = resume_text or ""

    def has(self, skill):
        return normalize_skill(skill) in self.skills or skill_in_text(skill, self.resume_text)


def score_project(project, candidate):
    required = split_skills(project.get("required_skills"))
    nice_to_have = split_skills(project.get("nice_to_have_skills"))

    matched_required = [skill for skill in required if candidate.has(skill)]
    missing_required = [skill for skill in required if not candidate.has(skill)]
    matched_nice_to_have = [skill for skill in nice_to_have if candidate.has(skill)]

    if required and nice_to_have:
        score = (
            REQUIRED_WEIGHT * len(matched_required) / len(required)
            + NICE_TO_HAVE_WEIGHT * len(matched_nice_to_have) / len(nice_to_have)
        )
    elif required:
        score = len(matched_required) / len(required)
    elif nice_to_have:
        score = len(matched_nice_to_have) / len(nice_to_have)
    else:
        score = 0.0

    return {
        "score": round(score * 100),
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_nice_to_have": matched_nice_to_have,
    }


def rank_projects(projects, candidate):
    """Score each project and return them best match first."""
    ranked = [
        {**project, "match": score_project(project, candidate)}
        for project in projects
    ]
    ranked.sort(key=lambda project: project["match"]["score"], reverse=True)
    return ranked


def detect_skills(text, vocabulary):
    """Return the skills from `vocabulary` that appear in `text`."""
    found = []
    seen = set()

    for skill in vocabulary:
        key = normalize_skill(skill)
        if key not in seen and skill_in_text(skill, text):
            seen.add(key)
            found.append(skill)

    return found
