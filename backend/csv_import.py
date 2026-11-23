"""Recognize project CSV columns by their common names."""

import re

COLUMN_ALIASES = {
    "role_id": ["role_id", "role id", "project id", "job id", "position id", "requisition id"],
    "title": ["title", "job title", "position", "position title", "role name", "job name"],
    "client_project": [
        "client_project", "client project", "client", "project name", "account", "business unit",
    ],
    "required_skills": [
        "required_skills", "required skills", "skills required", "skills", "key skills",
        "technical skills",
    ],
    "nice_to_have_skills": [
        "nice_to_have_skills", "nice to have skills", "preferred skills", "additional skills",
        "bonus skills",
    ],
    "seniority": ["seniority", "experience level", "level", "job level", "career level"],
    "location": ["location", "work location", "job location", "work arrangement", "work type"],
    "start_date": ["start_date", "start date", "beginning date", "project start", "start"],
    "status": ["status", "project status", "role status", "availability"],
    "description": [
        "description", "job description", "project description", "role description",
        "details", "summary",
    ],
}


def normalize_column_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


NORMALIZED_ALIASES = {
    column: {normalize_column_name(alias) for alias in aliases}
    for column, aliases in COLUMN_ALIASES.items()
}


def map_csv_headers(headers):
    """Map each database column to the CSV header that supplies it."""
    mapping = {}

    for column, accepted in NORMALIZED_ALIASES.items():
        for header in headers:
            if header and normalize_column_name(header) in accepted:
                mapping[column] = header
                break

    return mapping
