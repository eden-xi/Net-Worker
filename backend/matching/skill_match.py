"""
Skill matching: how well does a person fit a listing?

Plain Python, no AI, every rule visible:
  1. Split the listing's required skills into a list ("Python; FastAPI; SQL").
  2. A skill counts as MATCHED if it is in the person's skills list, or appears as a
     whole word/phrase in the text of their resume.
  3. score = matched required skills / all required skills, as a percentage.
  Nice-to-have skills never lower the score; matched ones are shown as a bonus.

Used for the employee's "% match" on every card, and to rank applicants for managers.
Later, the agent can call the same functions as a tool.
"""

import re

# Different spellings of the same skill. Keys and values are lower case.
ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "powerbi": "power bi",
    "ms excel": "excel",
}


def normalize(skill):
    """' FastAPI ' -> 'fastapi', 'JS' -> 'javascript', 'Power  BI' -> 'power bi'."""
    cleaned = re.sub(r"\s+", " ", skill.strip().lower())
    return ALIASES.get(cleaned, cleaned)


def split_skills(text):
    """'Python; SQL, Docker | CI/CD' -> ['Python', 'SQL', 'Docker', 'CI/CD'] (no duplicates).
    '/' is NOT a separator, so 'CI/CD' stays one skill."""
    skills = []
    seen = set()
    for part in re.split(r"[,;|\n]", text or ""):
        part = part.strip()
        if part and normalize(part) not in seen:
            seen.add(normalize(part))
            skills.append(part)
    return skills


def appears_in(skill, resume_text):
    """Whole-word search, so 'R' does not match inside 'React' and 'Java' not inside 'JavaScript'."""
    pattern = r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])"
    return re.search(pattern, resume_text, flags=re.IGNORECASE) is not None


def has_skill(skill, person_skills, resume_text):
    wanted = normalize(skill)
    if wanted in person_skills:
        return True
    return appears_in(skill, resume_text) or (wanted != skill.lower() and appears_in(wanted, resume_text))


def score(required, nice_to_have, skills_text, resume_text=""):
    """How well a person (skills_text + resume_text) fits a listing (required + nice_to_have).

    Returns {"score": 0-100, "matched": [...], "missing": [...], "bonus": [...]}.
    A listing with no required skills scores 0, so it never looks like a perfect fit by accident.
    """
    person_skills = {normalize(skill) for skill in split_skills(skills_text)}
    resume_text = resume_text or ""

    required_skills = split_skills(required)
    matched = [skill for skill in required_skills if has_skill(skill, person_skills, resume_text)]
    missing = [skill for skill in required_skills if skill not in matched]
    bonus = [skill for skill in split_skills(nice_to_have) if has_skill(skill, person_skills, resume_text)]

    percent = round(100 * len(matched) / len(required_skills)) if required_skills else 0
    return {"score": percent, "matched": matched, "missing": missing, "bonus": bonus}
