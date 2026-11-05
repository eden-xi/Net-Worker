# Round 1: Containerize, deploy free, gate — design

**Date:** 2026-11-05
**Branch:** `deploy/container-round1` (merged to `main` once verified)

## Intent

At the next team standup, show Net-Worker (ProjectHub) running at a live URL that
teammates can open and test, running in a container, behind a shared test password.
Explain what this does and does not do about the private data currently in git, and
the free-tier "data resets on restart" catch plus its workaround.

## Hard constraint

**Additive only.** No existing file is modified: `backend/**`, `frontend/**`,
`README.md`, and the committed `projecthub.db` / `uploads/resumes/*` stay exactly as
they are. This is a group project. Private data in git is not touched in Round 1. Removing
it needs team sign-off (Round 2).

## Goals

1. One Docker image that runs the whole app (API + frontend) on a single port.
2. A `docker-compose.yml` so any teammate with Docker can run it locally with one command.
3. A free live URL on **Render** (free web service, Docker runtime, auto-deploy from `main`).
4. A shared test password (HTTP Basic auth) on every request, set via host env var.
5. Fake demo data seeded on every startup so a fresh/wiped instance is always testable.
6. Two team-facing docs: a standup brief and a private-data plan.

## Non-goals

- Real logins/roles, Postgres, object storage, scaling to 500k users (later rounds).
- Fixing duplicate endpoints or other code issues in existing files.
- Removing private data from git or history (Round 2, after team sign-off).
- The agent platform.

## Anti-goals (failure even if it "works")

- Any edit to an existing file.
- The committed real `projecthub.db` or real resumes ending up inside the image or on
  the live site.
- The password or any secret committed to git.
- A live URL open to anyone without the password.

## Design

### Single container, Python wrapper (builder's call, recorded here)

Instead of a separate nginx container, a new file `deploy/server.py` builds an outer
FastAPI app that:

- **Mounts the existing app unchanged** at `/api` (`from backend.api.main import app`).
- **Serves `frontend/`** as static files at `/`.
- **Serves `/app.js` with one string swap at response time:**
  `"http://127.0.0.1:8000"` → `"/api"`, so the browser calls the same origin. The file
  on disk is untouched. If the string isn't found, log a loud warning (teammates may
  change it later).
- **Basic-auth middleware** on all paths except `/healthz` (for Render's health check).
  Credentials come from `APP_USERNAME` / `APP_PASSWORD` env vars. If `APP_PASSWORD` is
  unset, auth is disabled only when `ALLOW_NO_AUTH=1` (local dev). Otherwise the server
  refuses to start, so a deploy can't go live open by accident.
- **Lifespan startup:** calls the existing `create_tables()` (Starlette does not run a
  mounted sub-app's startup events), then seeds demo data.

Why: one free Render service = one container. Keeps everything in Python, which the team
already uses.

### Data location override (builder's call)

The existing code hard-codes the DB path (`backend/database/projecthub.db`) and the
resume folder (`uploads/resumes`). Running locally would open the **real committed DB**
and write into tracked files. So `deploy/server.py` repoints both at runtime, before
mounting the app, to `DATA_DIR` (env var; default `./.localdata/`, which is git-ignored;
`/data` in the container):

- Patch `DATABASE_PATH` on **both** module objects: `database` (imported via `sys.path`
  hack in `main.py`) and `backend.database.database` (imported by
  `application_routes.py`).
- Patch `RESUME_FOLDER` on **both** `backend.api.resume_routes` and
  `backend.api.application_routes` (the latter copies the value when imported).

This is runtime configuration from outside. No existing file's text changes. If teammates
later make these paths configurable, the patch can be deleted. Local runs also set
`PYTHONDONTWRITEBYTECODE=1` so the committed `__pycache__/*.pyc` files aren't rewritten.
The container runs as a non-root user that owns `/data`.

### Keeping private data out of the image

- `.dockerignore` excludes `backend/database/*.db`, `uploads/`, `__pycache__/`, `.git/`,
  `docs/`, and `.env`.
- At build time the image has no database, so a fresh one is created on startup.
- `.gitignore` is added for `*.db`, `uploads/`, `__pycache__/`, `.env` so nothing *new*
  gets committed. Note: `.gitignore` doesn't affect already-tracked files. Those remain until
  Round 2's `git rm --cached`.

### Demo data

- `deploy/demo_projects.csv`: ~10 clearly fake projects (fake client names, mixed skills/
  locations, all `Open`), using column headers the existing CSV importer recognizes.
- Seeding: on startup, the importer only runs if the `projects` table is empty. It goes
  through the existing `/api/projects/upload-csv` endpoint logic (via an in-process
  request), so the existing import rules are reused, not copied.
- No fake applications or resumes are seeded.

### Files added

```
Dockerfile                 python:3.13-slim, installs requirements, runs uvicorn deploy.server:app
.dockerignore
.gitignore
requirements.txt           fastapi, uvicorn[standard], python-multipart, pydantic[email],
                           pymupdf, python-docx (pinned versions)
docker-compose.yml         one service, port 8000, ALLOW_NO_AUTH=1 for local
render.yaml                Render blueprint: free plan, docker runtime, healthCheckPath /healthz,
                           APP_PASSWORD marked sync:false (entered in dashboard, not git)
deploy/__init__.py
deploy/server.py
deploy/demo_projects.csv
docs/team/standup-round1.md
docs/team/private-data-plan.md
```

The container listens on `$PORT` (Render sets it) and defaults to 8000.

### Team docs

**`docs/team/standup-round1.md`**: live URL + how to get the password (shared privately,
not in the doc), how to run locally (`docker compose up`), what was added, the catch:
Render free has no persistent disk. Data resets on every redeploy, restart, or spin-down,
and the service sleeps after 15 min idle (first visit ~1 min to wake). Workaround: demo
data reseeds itself. Treat the site as disposable and never upload real resumes to it.

**`docs/team/private-data-plan.md`**: what's in git now (live `projecthub.db` with
employee names/emails, 3 resumes), why containers + `.gitignore` don't remove it, the
proposed steps (`git rm --cached`, and history scrub with `git filter-repo` if the
resumes are real people's, which needs everyone to re-clone). Where data should live:
attached persistent storage now (paid on Render, or a free VM such as an Oracle Cloud
free-tier VM). Later: free Postgres (Neon/Supabase) + free object storage (Cloudflare R2)
for resumes, which requires edits to existing code and so is a team decision. Ends with the
decisions the team needs to make.

## Verification

- Docker isn't installed on the builder's machine, so verify locally by running
  `uvicorn deploy.server:app` in a venv: auth prompt appears, wrong password → 401,
  `/healthz` → 200 without auth, projects list shows demo data, applying with a test
  resume works, the manager CSV upload works, `app.js` served with `/api`.
- `git diff main --stat` shows only added files.
- Docker build is verified by Render's build (and by any teammate with Docker).
- After deploy: the live URL works end to end with the password.

## Branch and merge (builder's call)

Build and verify locally on `deploy/container-round1`, then the user merges to `main`
(they have direct push rights). `render.yaml` deploys from `main`, so the live URL appears
after the merge. Merge well before standup: the first Render build takes several minutes.

## Left to the builder

Exact pinned versions, demo-project contents, Dockerfile details (non-root user etc.),
log wording.

## User steps (can't be done by the builder)

1. Create a free Render account, connect GitHub (`eden-xi/Net-Worker`), "New Blueprint" →
   pick the repo, enter `APP_PASSWORD` when prompted.
2. Share the URL + password with the team privately.
