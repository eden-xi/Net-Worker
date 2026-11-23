# Net-Worker (ProjectHub)

An internal project marketplace. Managers publish open roles; employees browse
them, get recommendations based on their skills, and apply with a resume.
Managers then review applicants ranked by how well they match the role.

## Run it

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

uvicorn backend.api.main:app --reload
```

Open http://127.0.0.1:8000. The server hosts both the website and the API
(interactive API docs are at http://127.0.0.1:8000/docs).

On first start the database is created at `backend/database/projecthub.db`
and filled with 19 sample roles from `frontend/sample-projects.json`. Delete
the database file to start over.

If you open `frontend/index.html` without the API running (for example from
GitHub Pages), the site shows the sample roles in a read-only demo mode.

## How matching works

`backend/matching.py` scores each open project from 0 to 100 for a candidate:

- Required skills count for 80% of the score, nice-to-have skills for 20%.
- A skill matches if it is in the candidate's skill list, or appears as a
  whole word in their resume text. Common spellings are treated as the same
  skill (`k8s` and Kubernetes, `Postgres` and PostgreSQL).
- Very short skill names such as Go and R only match from the skill list,
  never from resume prose, to avoid false positives.

Employees see ranked recommendations under **Recommended Projects**, and can
fill in their skills from a resume on **My Profile**. When someone applies, the
score is saved, and managers see applicants sorted best match first.

## Adding roles from a CSV

On the Manager Dashboard, upload a UTF-8 CSV. Columns are recognized by common
names (`Job ID`, `Role ID`, `Job Title`, `Skills`, `Preferred Skills`,
`Location`, `Status`, ...). Role ID and title are required. A row whose Role ID
already exists updates that role, which is how you mark a role `Filled`.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `NETWORKER_DB` | `backend/database/projecthub.db` | SQLite database file |
| `NETWORKER_UPLOAD_DIR` | `uploads/resumes` | Where uploaded resumes are stored |
| `NETWORKER_CORS_ORIGINS` | local Live Server and GitHub Pages | Comma-separated sites allowed to call the API from a browser |
| `NETWORKER_SEED_SAMPLES` | `1` | Set to `0` to skip loading sample roles |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Data and privacy

The database and `uploads/` hold applicants' names, emails, and resumes. They
are git-ignored and must not be committed.

There is no login yet: anyone who can reach the server can see applicants and
change application statuses. Run it only on a trusted network until
authentication is added.
