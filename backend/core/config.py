"""
Every setting the app needs, in one place.

Each value comes from an environment variable, with a safe default for local runs.
Nothing else in the code reads os.getenv(): import this module instead, e.g.

    from backend.core import config
    config.DATABASE_PATH

Render (or Docker) sets the variables; locally the defaults just work.
"""

import os
from pathlib import Path

# The repo root (this file is backend/core/config.py, so two folders up).
ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------
# Data: where the database and uploaded resumes live
# ------------------------------------------

# Locally: <repo>/.localdata (git-ignored). In the container: /data (set in the Dockerfile).
# Point this at a persistent disk and data survives restarts.
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / ".localdata")))
DATABASE_PATH = DATA_DIR / "projecthub.db"
RESUME_DIR = DATA_DIR / "resumes"

MAX_RESUME_BYTES = 5 * 1024 * 1024        # 5 MB

# ------------------------------------------
# Team password (the browser pop-up in front of the whole site)
# ------------------------------------------

TEAM_USERNAME = os.getenv("APP_USERNAME", "team")
TEAM_PASSWORD = os.getenv("APP_PASSWORD", "")
ALLOW_NO_PASSWORD = os.getenv("ALLOW_NO_AUTH") == "1"      # local testing only

# ------------------------------------------
# Logins (the marketplace login wall)
# ------------------------------------------

# "test": only the test accounts in security.py.  "open": any email + any non-empty password.
LOGIN_MODE = os.getenv("MARKETPLACE_LOGIN_MODE", "test")
SESSION_HOURS = 8
COOKIE_NAME = "mp_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE") == "1"          # set to 1 on HTTPS hosts like Render

# ------------------------------------------
# Demo data
# ------------------------------------------

DEMO_CSV = ROOT / "deploy" / "demo_projects.csv"


def ensure_data_folders():
    """Create DATA_DIR and the resume folder if they are missing."""
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
