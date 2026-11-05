# deploy/ — container + hosting add-on

Everything for running Net-Worker in a container lives here. No group files are changed.
(The one exception is `/.gitignore` at the repo root: git only applies it there.)

| File | What it does |
|---|---|
| `server.py` | Wraps the existing app: serves frontend + API (`/api`), password gate, keeps data in `DATA_DIR`, loads demo projects |
| `demo_projects.csv` | 10 fake projects loaded when the database is empty |
| `Dockerfile` | Builds the container (copies only code, never the real DB or resumes) |
| `Dockerfile.dockerignore` | Extra safety net for the build |
| `docker-compose.yml` | One-command local run |
| `render.yaml` | Render settings, for later use as a Blueprint |
| `requirements.txt` | Python libraries |
| `docs/` | Design notes |

## Run it (from the repo root)

**With Docker:** `docker compose -f deploy/docker-compose.yml up --build`
then open http://localhost:8000 (user `team`, password `localtest`).

**Without Docker:**
```
pip install -r deploy/requirements.txt
$env:ALLOW_NO_AUTH="1"; $env:PYTHONDONTWRITEBYTECODE="1"; uvicorn deploy.server:app --reload
```

## Live site (Render, free)

Free tier: no saved files. Data resets to the demo projects on every redeploy, restart or
sleep. It sleeps after 15 min idle (first visit takes about a minute). Don't upload real resumes.
