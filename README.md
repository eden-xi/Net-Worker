# Net-Worker (ProjectHub)

An internal project marketplace, built to run on its own or as a Microsoft
Teams tab. Employees browse open projects, get recommendations from their
skills and resume, and apply. Project managers post projects and review
applicants ranked by match, and see only the projects they own or co-manage.

## Run it locally

Requires Python 3.10+. On Windows, double-click `run.bat` (or run
`.\run.bat` in a terminal): it sets up the environment on first run and
starts the server. Otherwise:

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

uvicorn backend.api.main:app --reload
```

Open http://127.0.0.1:8000. The server hosts both the website and the API
(API docs at http://127.0.0.1:8000/docs).

By default the app runs in **dev sign-in mode**: you pick a test user, or
sign in as any email. The test users are:

| User | Role |
|---|---|
| alex@example.com (Alex Rivera) | Employee |
| priya.pm@example.com (Priya Patel) | PM who owns the 19 sample roles |
| sam.pm@example.com (Sam Chen) | PM with no projects |
| avery.admin@example.com (Avery Brooks) | Admin |

On first start the database is created at `backend/database/projecthub.db`
and filled with the sample roles from `frontend/sample-projects.json`. Delete
the file to start over. Older databases from before sign-in existed are
upgraded in place: their applicants become dev users (by email) and their
projects go to the sample PM.

## Roles and access

- **Employees** browse, keep a skills profile and resume, get
  recommendations, and apply. The applicant is always the signed-in user.
- **Project managers** create, edit, close and reopen projects, import them
  from CSV, review applicants and download resumes, and add co-managers.
  Anyone can turn this on for themselves with **Post a project** (unless
  `PM_SELF_SERVICE=0`).
- **Admins** grant or remove PM access. They get no access to other people's
  projects.

Project access is decided by ownership, not by role. Every PM endpoint loads
projects through `backend/access.py`, which only returns projects the user
owns or co-manages; anything else gets 404, the same as a project that does
not exist. `tests/test_access_control.py` checks every PM route against
another PM and an employee.

## Sign-in modes

`backend/auth.py` turns the request's bearer token into a user. Nothing else
in the app knows which mode is in use.

| `AUTH_MODE` | Who it's for | Tokens |
|---|---|---|
| `dev` (default) | Local development | Issued by `/auth/dev-login`, which only accepts requests from this computer |
| `entra` | Real use, in Teams | Microsoft Entra ID tokens from Teams single sign-on, checked against your tenant |

See [teams/README.md](teams/README.md) for the Entra app registration and
Teams app package.

## How matching works

`backend/matching.py` scores each open project from 0 to 100:

- Required skills count for 80%, nice-to-have skills for 20%. A skill matches
  if it is on the employee's profile, or appears as a whole word in their
  resume. Common spellings count as the same skill (`k8s` and Kubernetes).
- Experience: the largest "N years" found in the resume is compared with the
  role's seniority (Junior 0, Mid 3, Senior 5, Lead 8+ years). Each year short
  takes 5 points off, at most 15. Without a stated number, there's no
  adjustment.
- Very short skill names such as Go and R only match from the profile, never
  from resume text.

Uploading a resume on **My Profile** suggests skills found in it (from
`backend/skills_vocabulary.py` plus every skill any project asks for); the
employee chooses which to add.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `AUTH_MODE` | `dev` | `dev` or `entra` |
| `ENTRA_TENANT_ID` | | Entra tenant ID (required for `entra`) |
| `ENTRA_CLIENT_ID` | | App registration client ID |
| `ENTRA_AUDIENCE` | | Application ID URI, e.g. `api://host/client-id` |
| `PM_SELF_SERVICE` | `1` | Let users turn on PM access themselves |
| `NETWORKER_DB` | `backend/database/projecthub.db` | SQLite database file |
| `NETWORKER_UPLOAD_DIR` | `uploads/resumes` | Where resumes are stored |
| `NETWORKER_AVATAR_DIR` | `uploads/avatars` | Where profile pictures are stored |
| `NETWORKER_SEED_SAMPLES` | `1` | Load sample roles into an empty database |
| `NETWORKER_SECRET` | random per start | Signing key for dev tokens |
| `NETWORKER_DEV_LOGIN_ANY_HOST` | `0` | Allow dev sign-in from other machines |
| `NETWORKER_CORS_ORIGINS` | local Live Server | Other sites allowed to call the API |
| `NETWORKER_FRAME_ANCESTORS` | Teams and Microsoft 365 | Sites allowed to embed the app |

## Profile pictures and icons

People can add a profile picture on **My Profile**. Uploads are re-encoded on
the server as 256x256 WebP, which strips hidden metadata such as GPS location
and rejects anything that isn't a real image. Pictures are visible to anyone
signed in.

The app icon (favicon, Teams icons) is generated by `scripts/make_icons.py`;
the same mark is drawn as inline SVG in `frontend/index.html`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Data and privacy

The database and `uploads/` hold applicants' names, emails and resumes. They
are git-ignored and must not be committed.
