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
        self.years = extract_years_of_experience(self.resume_text)

    def has(self, skill):
        return normalize_skill(skill) in self.skills or skill_in_text(skill, self.resume_text)


# ==========================================
# EXPERIENCE
# ==========================================

# Minimum years of experience each seniority level usually expects.
SENIORITY_MIN_YEARS = {
    "intern": 0, "entry": 0, "junior": 0, "associate": 1,
    "mid": 3, "intermediate": 3,
    "senior": 5, "staff": 8, "lead": 8, "principal": 10,
}

# Points taken off per year short of a level's minimum, and the most taken off.
EXPERIENCE_PENALTY_PER_YEAR = 5
EXPERIENCE_MAX_PENALTY = 15

YEARS_PATTERN = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)


def extract_years_of_experience(text):
    """Best guess at total years of experience stated in a resume, or None.

    Uses the largest "N years" figure found. This is a heuristic: a resume
    that never states a number gets None, and no experience adjustment.
    """
    years = []

    for match in YEARS_PATTERN.finditer(text or ""):
        value = int(match.group(1))
        if 0 < value <= 45:
            years.append(value)

    return max(years) if years else None


def required_years(seniority):
    words = re.findall(r"[a-z]+", (seniority or "").lower())
    levels = [SENIORITY_MIN_YEARS[word] for word in words if word in SENIORITY_MIN_YEARS]
    return max(levels) if levels else None


def experience_fit(seniority, years):
    needed = required_years(seniority)

    if needed is None or years is None:
        return {"years": years, "required_years": needed, "fit": "unknown", "penalty": 0}

    if years >= needed:
        return {"years": years, "required_years": needed, "fit": "meets", "penalty": 0}

    penalty = min(EXPERIENCE_MAX_PENALTY, EXPERIENCE_PENALTY_PER_YEAR * (needed - years))
    return {"years": years, "required_years": needed, "fit": "below", "penalty": penalty}


# ==========================================
# SCORING
# ==========================================

def score_project(project, candidate):
    required = split_skills(project.get("required_skills"))
    nice_to_have = split_skills(project.get("nice_to_have_skills"))

    matched_required = [skill for skill in required if candidate.has(skill)]
    missing_required = [skill for skill in required if not candidate.has(skill)]
    matched_nice_to_have = [skill for skill in nice_to_have if candidate.has(skill)]

    if required and nice_to_have:
        skill_score = (
            REQUIRED_WEIGHT * len(matched_required) / len(required)
            + NICE_TO_HAVE_WEIGHT * len(matched_nice_to_have) / len(nice_to_have)
        )
    elif required:
        skill_score = len(matched_required) / len(required)
    elif nice_to_have:
        skill_score = len(matched_nice_to_have) / len(nice_to_have)
    else:
        skill_score = 0.0

    skill_score = round(skill_score * 100)
    experience = experience_fit(project.get("seniority"), candidate.years)

    return {
        "score": max(0, skill_score - experience["penalty"]),
        "skill_score": skill_score,
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_nice_to_have": matched_nice_to_have,
        "experience": experience,
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
