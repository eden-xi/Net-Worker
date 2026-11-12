"""Net-Worker architecture audit: builds two companion PDFs from a live read of the repo.

  01_Technical_Architecture_and_Syntax.pdf  - graph, file-by-file syntax, routes, models, state
  02_Plain_English_Walkthrough.pdf          - the same sections and node IDs, in plain English

Read-only: it parses the source (Python AST, JS/HTML regex, SQL DDL) and never edits it.
Requires: matplotlib, fpdf2.   Run from anywhere:  python docs/architecture_audit/generate_docs.py
"""
import ast
import re
import subprocess
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from fpdf import FPDF
from fpdf.fonts import FontFace

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
LINE_LIMIT = 800
HTTP = {"get", "post", "put", "patch", "delete"}
SKIP = ("__pycache__", ".pyc", ".db", "uploads/", "docs/architecture_audit/", ".docx")

# ---------------------------------------------------------------- 1. ANALYSIS
def repo_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
        names = out.stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        names = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return sorted(n for n in names if not any(s in n for s in SKIP))


def analyze_python(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    info = {"imports": [], "functions": [], "models": [], "routes": [], "hooks": [], "wiring": [], "aliases": {}}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            info["imports"].append(node.module or "")
            for a in node.names:
                info["aliases"][a.asname or a.name] = node.module
        elif isinstance(node, ast.Import):
            info["imports"] += [a.name for a in node.names]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            info["functions"].append(f"{kind} {node.name}()")
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                    arg = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else ""
                    if d.func.attr in HTTP:
                        info["routes"].append((d.func.attr.upper(), arg, node.name))
                    else:
                        info["hooks"].append(f"@{ast.unparse(d.func)}({arg!r}) -> {node.name}")
        elif isinstance(node, ast.ClassDef):
            fields = [f"{t.target.id}: {ast.unparse(t.annotation)}" for t in node.body
                      if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)]
            info["models"].append((node.name, ", ".join(ast.unparse(b) for b in node.bases), fields))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr in ("include_router", "mount", "add_middleware"):
                info["wiring"].append(call)
    return info


def router_prefixes(py):
    """Map each module to the URL prefix it is served under (through server.py's /api mount)."""
    prefixes = {"backend/api/main.py": "/api", "deploy/server.py": ""}
    main = py.get("backend/api/main.py", {})
    for call in main.get("wiring", []):
        if call.func.attr == "include_router" and isinstance(call.args[0], ast.Name):
            module = main["aliases"].get(call.args[0].id, "")
            kw = {k.arg: k.value.value for k in call.keywords if isinstance(k.value, ast.Constant)}
            prefixes[module.replace(".", "/") + ".py"] = "/api" + kw.get("prefix", "")
    return prefixes


def analyze_js(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    calls = []
    for m in re.finditer(r"fetch\(\s*`([^`]+)`(.{0,120})", src, re.S):
        url = re.sub(r"\$\{API_URL\}", "", m.group(1)).split("?")[0]
        url = re.sub(r"\$\{[^}]+\}", "{id}", url)
        method = re.search(r'method:\s*"(\w+)"', m.group(2))
        calls.append((method.group(1) if method else "GET", url))
    return {"functions": re.findall(r"^(?:async )?function (\w+)", src, re.M),
            "globals": re.findall(r"^(?:let|const) (\w+)", src, re.M),
            "fetches": calls, "listeners": len(re.findall(r"addEventListener\(", src))}


def analyze_html(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    return {"views": re.findall(r'<section id="([\w-]+)"', src),
            "modals": re.findall(r'<div id="([\w-]+-modal)"', src),
            "forms": re.findall(r'<form id="([\w-]+)"', src)}


def analyze_sql(py_sources):
    db_src = (ROOT / "backend/database/database.py").read_text(encoding="utf-8")
    tables = {}
    for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\s*\)\s*\"\"\"", db_src, re.S):
        cols = [ln.strip().rstrip(",") for ln in body.splitlines() if ln.strip()]
        tables[name] = [c for c in cols if not c.startswith(("FOREIGN", "UNIQUE"))]
        tables[name] += [f"(constraint) {c}" for c in cols if c.startswith(("FOREIGN", "UNIQUE"))]
    for src in py_sources:
        for t, col in re.findall(r"ALTER TABLE (\w+) ADD COLUMN (\w+ \w+)", src):
            tables[t].append(f"{col}  (added at runtime by ALTER TABLE)")
    usage = {t: sum(len(re.findall(rf"(?:FROM|JOIN|INTO|UPDATE)\s+{t}\b", s)) for s in py_sources) for t in tables}
    return tables, usage


def analyze():
    files = repo_files()
    py = {f: analyze_python(f) for f in files if f.endswith(".py") and (ROOT / f).stat().st_size}
    sizes = {f: len((ROOT / f).read_text(encoding="utf-8", errors="ignore").splitlines()) for f in files}
    prefixes = router_prefixes(py)
    js = analyze_js("frontend/app.js")
    called = [(m, "/api" + u) for m, u in js["fetches"]]
    routes = [{"method": m, "url": prefixes.get(f, "") + p, "handler": h, "file": f, "used": False}
              for f, info in py.items() for m, p, h in info["routes"]]
    for method, url in called:  # most specific match wins (fewest {params}), mirroring how literal routes shadow params
        hits = [r for r in routes if r["method"] == method
                and re.match("^" + re.sub(r"\{[^}]+\}", "[^/]+", r["url"]) + "$", url)]
        if hits:
            min(hits, key=lambda r: r["url"].count("{"))["used"] = True
    srcs = [(ROOT / f).read_text(encoding="utf-8") for f in py]
    tables, usage = analyze_sql(srcs)
    return {"files": files, "sizes": sizes, "py": py, "js": js, "html": analyze_html("frontend/index.html"),
            "routes": routes, "tables": tables, "usage": usage,
            "oversize": [f for f, n in sizes.items() if n > LINE_LIMIT]}

# ---------------------------------------------------------------- 2. KNOWLEDGE (shared node IDs)
# id: (x, y, zone, technical label, plain label, plain-English explanation)
NODES = {
    "N1": (1.5, 7.8, "client", "Browser\n(user agent)", "The person's\nweb browser", "Where everything starts and ends: someone types the Render address and sees the ProjectHub screens."),
    "N2": (1.5, 6.1, "client", "frontend/index.html\n(5 views, 2 modals)", "The page\nlayout", "The skeleton of the screen: five tabs (Browse, Profile, Recommended, My Applications, Manager) and two pop-ups."),
    "N3": (1.5, 4.4, "client", "frontend/app.js\n(state + fetch)", "The page's\nbrain", "Runs inside the browser. It reacts to clicks, asks the server for data, and redraws the screen with the answer."),
    "N4": (1.5, 2.7, "client", "frontend/styles.css", "The page's\nlook", "Colours, spacing and layout. It changes nothing about data; it only makes the screens look right."),
    "N5": (4.35, 7.8, "edge", "Render web service\nHTTPS :443 -> $PORT", "The public\nweb address", "Render owns the public URL and the security certificate. It forwards each request into our container."),
    "N6": (7.5, 7.8, "container", "require_password\n(HTTP middleware)", "The front-door\npassword check", "Every request must carry the shared team password, or the visitor gets a login prompt instead of the app."),
    "N7": (7.5, 6.6, "container", "GET /healthz", "The 'are you\nalive?' check", "The one door with no password, so Render can ping it to confirm the app is up."),
    "N8": (7.5, 5.4, "container", "GET /app.js\n(URL rewriter)", "The address\ntranslator", "Hands the browser app.js with the laptop-only address swapped for '/api', so the page talks to this same site."),
    "N9": (7.5, 4.2, "container", "StaticFiles mount '/'", "The file\nhandout desk", "Gives the browser the page files (HTML, CSS) exactly as they are in the repo."),
    "N10": (7.5, 3.0, "container", "Mount '/api'\n-> ProjectHub app", "The hallway to\nthe back office", "Anything whose address starts with /api is passed through, unchanged, to the team's original backend."),
    "N11": (7.5, 9.0, "container", "lifespan(): create_tables\n+ load_demo_projects", "Opening-time\nroutine", "When the container starts it creates any missing tables and loads 10 fake projects if the database is empty."),
    "N12": (11.5, 9.0, "backend", "backend/api/main.py\nFastAPI 'ProjectHub API'", "The back office\nreception", "The team's main server file: lists projects, imports CSV files, records applications, updates statuses."),
    "N13": (12.5, 7.0, "backend", "application_routes.py\nAPIRouter /applications", "The application\ndesk", "Handles 'apply with a resume' and 'show me my applications' requests."),
    "N14": (10.5, 5.2, "backend", "resume_routes.py\nAPIRouter /resumes", "The resume\nreader", "Checks that an uploaded resume is a real PDF/Word file and pulls the text out of it."),
    "N15": (11.5, 2.6, "backend", "backend/database/\ndatabase.py", "The filing-cabinet\nkey", "Opens the database and knows how to build the four tables on first run."),
    "N16": (14.9, 2.6, "data", "SQLite projecthub.db\n($DATA_DIR)", "The filing\ncabinet", "One file holding all projects, people and applications. On Render free tier it is wiped on every restart."),
    "N17": (14.9, 5.8, "data", "$DATA_DIR/resumes/\n(<uuid>.pdf|.docx)", "The resume\ndrawer", "Uploaded resume files, renamed to random IDs so names can't clash or be guessed."),
    "N18": (14.9, 9.0, "data", "deploy/\ndemo_projects.csv", "The sample\nprojects list", "Ten clearly fake projects so a fresh site is never empty."),
    "N19": (7.5, 0.85, "build", "deploy/Dockerfile\npython:3.13-slim", "The packing\nlist", "Recipe that packs only the code (never the real database or resumes) into one container image."),
    "N20": (3.0, 0.85, "build", "deploy/docker-compose.yml", "Run-it-locally\nshortcut", "Lets any teammate start the same container on a laptop with one command."),
    "N21": (12.0, 0.85, "build", "deploy/render.yaml\n(blueprint)", "Hosting\nsettings", "Written-down Render settings for later; today the service was set up by hand."),
}
EDGES = [  # (src, dst, technical label, plain label, arc curvature, label position along edge)
    ("N1", "N5", "HTTPS request", "visit URL", 0, .5), ("N5", "N6", "proxied to $PORT", "forwards", 0, .5),
    ("N6", "N7", "exempt path", "no password", 0, .5), ("N6", "N8", "auth OK", "allowed in", -.83, .5),
    ("N6", "N9", "auth OK", "allowed in", -.67, .5), ("N6", "N10", "auth OK", "allowed in", -.56, .5),
    ("N9", "N2", "serves HTML", "sends page", 0, .7), ("N9", "N4", "serves CSS", "sends style", 0, .7),
    ("N8", "N3", "API_URL -> /api", "sends brain", 0, .3), ("N3", "N5", "fetch /api/*", "asks for data", 0, .5),
    ("N10", "N12", "ASGI sub-app", "passes along", 0, .3), ("N12", "N13", "include_router", "delegates", 0, .5),
    ("N12", "N14", "include_router", "delegates", 0, .5), ("N13", "N14", "import extract_*", "borrows reader", 0, .5),
    ("N12", "N15", "get_connection", "opens cabinet", 0, .62), ("N13", "N15", "get_connection", "opens cabinet", 0, .6),
    ("N15", "N16", "sqlite3 SQL", "reads/writes", 0, .5), ("N13", "N17", "write_bytes", "saves file", 0, .5),
    ("N14", "N17", "write_bytes", "saves file", 0, .75), ("N18", "N12", "CSV rows", "sample data", 0, .5),
    ("N11", "N12", "create_tables() + upload_projects_csv()", "builds tables + loads samples", 0, .5),
    ("N20", "N19", "build", "uses recipe", 0, .5), ("N21", "N19", "dockerfilePath", "uses recipe", 0, .5),
    ("N19", "N10", "CMD uvicorn deploy.server:app", "starts the wrapper", 0, .42),
]
ZONES = {"client": ((0.15, 1.7, 2.7, 8.1), "#e8f0fe", "CLIENT (browser)", "YOUR BROWSER"),
         "edge": ((3.25, 1.7, 2.2, 8.1), "#fdf2e3", "RENDER EDGE", "THE WEB HOST"),
         "container": ((5.85, 1.7, 3.3, 8.1), "#e7f6ec", "CONTAINER: deploy/server.py", "OUR CONTAINER WRAPPER"),
         "backend": ((9.55, 1.7, 4.0, 8.1), "#f3e8fd", "BACKEND: ProjectHub (unchanged)", "THE TEAM'S BACKEND"),
         "data": ((13.95, 1.7, 1.9, 8.1), "#fdeaea", "DATA FILES", "STORED DATA"),
         "build": ((0.15, 0.1, 15.7, 1.45), "#eeeeee", "BUILD & DEPLOY CONFIG", "PACKAGING & HOSTING")}

LIFECYCLE = [  # (technical hop, plain-English hop)
    ("DNS resolves <service>.onrender.com; TLS terminates at Render's edge proxy.", "The browser finds Render and opens a secure, encrypted line."),
    ("Proxy forwards HTTP to the container on $PORT; uvicorn hands it to deploy.server:app (ASGI).", "Render passes the request into our container, where the web server picks it up."),
    ("require_password middleware: no/invalid 'Authorization: Basic' -> 401 + WWW-Authenticate.", "The front door asks for the team password. Wrong or missing: the browser shows a login box."),
    ("Browser caches the credentials for the origin and resends them on every same-origin request.", "Once typed, the browser remembers the password for this site, so later clicks just work."),
    ("GET / -> StaticFiles(html=True) returns index.html; GET /app.js -> rewritten script (API_URL='/api').", "The page and its 'brain' are handed out; the brain is told to call this same site for data."),
    ("app.js DOMContentLoaded -> loadProjects() -> fetch('/api/projects').", "As soon as the page opens, the brain asks the back office for the list of open projects."),
    ("Mount('/api') strips the prefix; ProjectHub router matches GET /projects -> get_projects().", "The hallway passes the request to the team's backend, which knows what 'projects' means."),
    ("get_connection() opens SQLite at DATA_DIR/projecthub.db (path patched by server.py); SELECT ... status='open'.", "The backend opens the filing cabinet and pulls out every project still marked Open."),
    ("Rows -> list[dict] -> JSON 200; middleware passes response back through Render to the browser.", "The answer travels back the same way it came, as a simple data list."),
    ("app.js stores it in availableProjects and re-renders cards with escapeHTML(); filters run client-side.", "The brain keeps the list in memory and draws a card per project; searching filters that list without asking the server again."),
    ("Apply: multipart POST /api/applications/submit-with-resume -> validate, write <uuid>.ext, INSERT employee+application, COMMIT (rollback + unlink on error).", "Applying sends the form and resume together. The server checks it, saves the file, records the application, and undoes everything if any step fails."),
]
STATE = [
    ("Client globals in app.js: employeeSkills[], availableProjects[], selectedProject - in-memory only, lost on reload.", "The page remembers your skills, the project list and the project you picked only until you refresh."),
    ("Recommendation score = |required ∩ employeeSkills| / |required| computed in the browser (calculateMatch); the 'matches' table is never written.", "Match percentages are worked out on your own computer; the server's 'matches' table sits empty."),
    ("Server is stateless per request: each handler opens and closes its own sqlite3 connection.", "The server forgets you between requests; everything worth keeping goes into the database."),
    ("Durable state: SQLite file + resume files under DATA_DIR. Render free tier has an ephemeral disk -> reset on deploy/restart/sleep.", "Saved data lives in one database file and a resume folder. On the free plan both are wiped whenever the site restarts."),
    ("Identity: none in the app; 'My Applications' trusts any email in the query string. Basic-auth is one shared team credential.", "There are no personal logins yet. Anyone with the team password can look up applications by typing an email."),
]
FINDINGS = [
    ("Two application write paths: POST /applications (JSON, main.py) and POST /applications/submit-with-resume (multipart). Only the latter is called; logic is duplicated.", "There are two ways to apply in the code; the page uses only one. Keeping both doubles the upkeep."),
    ("database.py is imported twice (as 'database' via sys.path and as 'backend.database.database'): two module objects; server.py must patch both.", "The cabinet key is loaded twice under two names, so the wrapper has to update both copies."),
    ("CORSMiddleware allow_origins=['*'] with allow_credentials=True; harmless behind same-origin /api but permissive if main.py is run alone.", "The backend says 'any website may call me', which is loose if it's ever run without the wrapper."),
    ("@app.on_event('startup') is deprecated in FastAPI; it is also skipped when mounted, which is why server.py has its own lifespan.", "The backend uses an old start-up hook; that's why our wrapper does the start-up job itself."),
    ("Profile 'resume-file' input is never uploaded; POST /resumes/upload stores a file but nothing links it to an employee.", "Picking a resume on the Profile tab doesn't send it anywhere, and the separate upload endpoint saves orphan files."),
    ("GET /applications/{application_id} relies on the router being included first so /my-applications wins the match.", "One address only works because of the order lines appear in; moving them would break it."),
    ("Real projecthub.db and resumes are committed to git (outside the image thanks to the Dockerfile's explicit COPY list).", "Private data is still in the shared code history; it never reaches the live site, but it should be removed (Round 2)."),
]
FILE_PLAIN = {
    "backend/api/main.py": "The team's main server file. It sets up the backend, teaches it to read messy CSV column names, and answers the requests for projects and applications.",
    "backend/api/application_routes.py": "The 'apply with resume' desk. It checks the person, project and file, saves the resume, records the application, and lists a person's past applications.",
    "backend/api/resume_routes.py": "The resume reader. It knows how to pull plain text out of PDF and Word files and enforces the 5 MB, PDF/DOCX-only rule.",
    "backend/database/database.py": "The filing-cabinet key: where the database file lives, how to open it, and the blueprint for its four drawers (tables).",
    "deploy/server.py": "Our wrapper. It puts the page and the backend on one web address, adds the team password, moves saved data to a safe folder, and loads sample projects.",
    "frontend/app.js": "Everything the page does when you click: switching tabs, loading projects, scoring matches, sending applications, and the manager's CSV upload.",
    "frontend/index.html": "The page structure: the header, the five tabs, and the two pop-up windows.",
    "frontend/styles.css": "The visual design only. Safe to ignore when tracing data.",
    "deploy/Dockerfile": "The packing list for the container. It deliberately copies code file by file so private data can't sneak in, and runs as a non-admin user.",
    "deploy/docker-compose.yml": "A one-line way to run the container on a laptop with a local test password.",
    "deploy/render.yaml": "Render's settings written down (Docker, free plan, health check, password asked at setup). Not wired up yet.",
    "deploy/requirements.txt": "The list of Python add-ons the container installs, with exact versions so every build is identical.",
    "deploy/demo_projects.csv": "Ten fake projects used to fill an empty database.",
}
ROUTE_PLAIN = {  # keyed by handler function name
    "home": "Says hello - proves the backend is running.", "health": "Backend's own 'I'm fine' check.",
    "get_projects": "Lists every project still open.", "get_project": "Shows one project in full.",
    "upload_projects_csv": "Manager uploads a spreadsheet of new projects.",
    "submit_application": "Older way to apply (no resume file). Not used by the page.",
    "get_application": "Looks up one application by number. Not used by the page.",
    "get_project_applications": "Lists who applied to a project. Not used by the page yet.",
    "update_application_status": "Manager changes an application's status. Not used by the page yet.",
    "submit_application_with_resume": "Apply to a project, with an optional resume file.",
    "get_my_applications": "Shows everything one email address has applied to.",
    "upload_resume": "Uploads a resume on its own. Not used by the page.",
    "healthz": "Render's alive check - the only route without a password.",
    "frontend_script": "Hands out the page's brain with the address fixed up.",
}

# ---------------------------------------------------------------- 3. GRAPH
def draw_graph(path, plain=False):
    fig, ax = plt.subplots(figsize=(16, 10), dpi=300)
    ax.set_xlim(0, 16); ax.set_ylim(0, 10); ax.axis("off")
    for (x, y, w, h), color, tech, simple in ZONES.values():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=color, ec="#999", lw=1))
        tx, ha = (x + 0.25, "left") if y < 1 else (x + w / 2, "center")
        ax.text(tx, y + h - 0.12, simple if plain else tech, ha=ha, va="top", fontsize=9, weight="bold", color="#333")
    boxes = {nid: ax.text(x, y, f"{nid}\n{simple if plain else tech}", ha="center", va="center", fontsize=7.4,
                          zorder=3, family="sans-serif" if plain else "monospace",
                          bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#2b4a7a", lw=1.2))
             for nid, (x, y, _z, tech, simple, _d) in NODES.items()}
    title = "How Net-Worker fits together" if plain else "Net-Worker: dependency & data-flow graph"
    ax.set_title(title, fontsize=13, weight="bold")
    fig.tight_layout(); fig.canvas.draw()  # sizes the boxes so arrows can be clipped to their borders
    for src, dst, tech, simple, rad, t in EDGES:
        (x1, y1), (x2, y2) = NODES[src][:2], NODES[dst][:2]
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
                                     mutation_scale=13, lw=1.1, color="#41618f", zorder=4, shrinkA=1, shrinkB=2,
                                     patchA=boxes[src].get_bbox_patch(), patchB=boxes[dst].get_bbox_patch()))
        cx, cy = (x1 + x2) / 2 + rad * (y2 - y1), (y1 + y2) / 2 - rad * (x2 - x1)  # arc3 control point
        lx, ly = [(1 - t) ** 2 * a + 2 * (1 - t) * t * c + t ** 2 * b for a, c, b in ((x1, cx, x2), (y1, cy, y2))]
        ax.text(lx, ly, simple if plain else tech, fontsize=6, ha="center", va="center", color="#7a2b2b", zorder=5,
                bbox=dict(boxstyle="round,pad=0.15", fc="#fffbe6", ec="#e0d8b0", lw=0.4))
    fig.savefig(path, dpi=300); plt.close(fig)

# ---------------------------------------------------------------- 4. PDF HELPERS
def clean(text):
    swaps = {"—": "-", "–": "-", "→": "->", "∩": "n", "‘": "'", "’": "'", "“": '"', "”": '"'}
    for a, b in swaps.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


class Report(FPDF):
    def __init__(self, title):
        super().__init__(format="A4"); self.doc_title = title
        self.set_auto_page_break(True, 15); self.set_margins(15, 15, 15)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8); self.set_text_color(120)
            self.cell(0, 6, clean(self.doc_title), align="R", new_x="LMARGIN", new_y="NEXT"); self.set_text_color(0)

    def footer(self):
        self.set_y(-12); self.set_font("Helvetica", "", 8); self.set_text_color(120)
        self.cell(0, 6, f"Page {self.page_no()}/{{nb}}", align="C"); self.set_text_color(0)

    def h1(self, text):
        self.ln(3); self.set_font("Helvetica", "B", 16); self.set_text_color(30, 60, 110)
        self.multi_cell(0, 8, clean(text), new_x="LMARGIN", new_y="NEXT"); self.set_text_color(0); self.ln(1)

    def h2(self, text):
        self.ln(2); self.set_font("Helvetica", "B", 12)
        self.multi_cell(0, 6, clean(text), new_x="LMARGIN", new_y="NEXT")

    def para(self, text, size=10, style=""):
        self.set_font("Helvetica", style, size)
        self.multi_cell(0, 5, clean(text), markdown=True, new_x="LMARGIN", new_y="NEXT"); self.ln(1)

    def bullets(self, items, size=9.5, markdown=True):
        for item in items:
            self.set_font("Helvetica", "", size); self.cell(5, 5, "-")
            self.multi_cell(0, 5, clean(item), markdown=markdown, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def grid(self, head, rows, widths, size=8):
        self.set_font("Helvetica", "", size)
        with self.table(col_widths=widths, text_align="LEFT", line_height=4.4, padding=1.2,
                        headings_style=FontFace(emphasis="BOLD", fill_color=(220, 228, 242))) as t:
            for row in [head] + rows:
                r = t.row()
                for cell in row:
                    r.cell(clean(str(cell)))
        self.ln(2)

    def graph_page(self, image, caption):
        self.add_page(orientation="L"); self.h1(caption)
        self.image(str(image), x=(self.w - 255) / 2, w=255); self.add_page(orientation="P")

    def cover(self, title, subtitle, lines):
        self.add_page(); self.ln(50); self.set_font("Helvetica", "B", 24); self.set_text_color(30, 60, 110)
        self.multi_cell(0, 11, clean(title), align="C", new_x="LMARGIN", new_y="NEXT"); self.set_text_color(0)
        self.set_font("Helvetica", "", 13); self.multi_cell(0, 7, clean(subtitle), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(12)
        for ln in lines:
            self.para(ln, 10)


# ---------------------------------------------------------------- 5. REPORTS
SECTIONS = ["1. System graph", "2. Request lifecycle: Render URL -> container -> backend", "3. File-by-file breakdown",
            "4. Endpoint catalogue", "5. Data models", "6. State management", f"7. Files over {LINE_LIMIT} lines",
            "8. Risks & observations"]


def used_label(route, no):
    return "infra" if route["file"] == "deploy/server.py" else "yes" if route["used"] else no


def stats_line(a):
    code = [f for f in a["files"] if f.endswith((".py", ".js", ".html", ".css"))]
    return (f"Scanned {len(a['files'])} tracked files ({sum(a['sizes'][f] for f in code)} lines of code), "
            f"{len(a['routes'])} HTTP routes, {len(a['tables'])} tables. Generated {date.today().isoformat()}.")


def technical_pdf(a, graph):
    pdf = Report("01 - Technical Architecture & Syntax")
    pdf.cover("Net-Worker (ProjectHub)", "01 - Technical Architecture & Syntax",
              [stats_line(a), "Stack: FastAPI + Starlette on uvicorn (Python 3.13), SQLite via sqlite3, vanilla JS SPA, "
               "PyMuPDF + python-docx for resume parsing, Docker image on Render free tier.",
               "Companion: 02_Plain_English_Walkthrough.pdf uses identical section numbers and node IDs (N1-N21)."])
    pdf.graph_page(graph, SECTIONS[0])
    pdf.h1(SECTIONS[0] + " - node legend")
    pdf.grid(["ID", "Zone", "Component"], [[k, v[2], v[3].replace("\n", " ")] for k, v in NODES.items()], (12, 25, 143))
    pdf.h1(SECTIONS[1])
    pdf.bullets([f"**Hop {i}.** {t}" for i, (t, _p) in enumerate(LIFECYCLE, 1)])
    pdf.h1(SECTIONS[2])
    for f in a["files"]:
        if f.endswith((".md", ".dockerignore", "__init__.py", ".gitignore")) or not a["sizes"].get(f):
            continue
        flag = "  [OVER LIMIT]" if f in a["oversize"] else ""
        pdf.h2(f"{f}  ({a['sizes'][f]} lines){flag}")
        info = a["py"].get(f)
        if info:
            items = [f"**Imports:** {', '.join(sorted(set(info['imports'])))}",
                     f"**Top-level functions ({len(info['functions'])}):** {', '.join(info['functions'])}"]
            items += [f"**Model** {n}({b}): {'; '.join(fl) or '-'}" for n, b, fl in info["models"]]
            items += [f"**Route** {m} {p} -> {h}()" for m, p, h in info["routes"]]
            items += [f"**Hook** {h}" for h in info["hooks"]]
            items += [f"**Wiring** {ast.unparse(c)[:150]}" for c in info["wiring"]]
            pdf.bullets(items, 8.5)
        elif f == "frontend/app.js":
            js = a["js"]
            pdf.bullets([f"**Module state (globals):** {', '.join(js['globals'])}",
                         f"**Functions ({len(js['functions'])}):** {', '.join(js['functions'])}",
                         f"**fetch() calls:** {'; '.join(f'{m} {u}' for m, u in js['fetches'])}",
                         f"**DOM listeners:** {js['listeners']} addEventListener calls; event delegation via [data-action]."], 8.5)
        elif f == "frontend/index.html":
            h = a["html"]
            pdf.bullets([f"**Views (<section>):** {', '.join(h['views'])}", f"**Modals:** {', '.join(h['modals'])}",
                         f"**Forms:** {', '.join(h['forms'])}", "Loads styles.css and app.js (defer)."], 8.5)
        else:
            body = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
            keys = [ln.strip() for ln in body.splitlines() if re.match(r"^\s*(FROM|ENV|COPY|RUN|USER|CMD|EXPOSE|type|runtime|plan|dockerfilePath|healthCheckPath|[a-z-]+==)", ln)]
            pdf.bullets(keys[:14] or ["Data/config file."], 8.5, markdown=False)
    pdf.h1(SECTIONS[3])
    pdf.para("Public URL = what the browser calls on Render. Called = a matching fetch() exists in app.js; infra = served to the browser/Render directly.", 9, "I")
    pdf.grid(["Method", "Public URL", "Handler", "File", "Called"],
             [[r["method"], r["url"], r["handler"], r["file"].split("/")[-1], used_label(r, "NO")] for r in a["routes"]],
             (16, 64, 45, 37, 18))
    pdf.h1(SECTIONS[4])
    for t, cols in a["tables"].items():
        pdf.h2(f"Table {t}  (referenced in {a['usage'][t]} query/queries outside the DDL)")
        pdf.bullets(cols, 8.5)
    pdf.h2("Pydantic request models")
    pdf.bullets([f"{n}({b}): {'; '.join(fl)}" for info in a["py"].values() for n, b, fl in info["models"]], 8.5)
    pdf.h1(SECTIONS[5]); pdf.bullets([t for t, _ in STATE])
    pdf.h1(SECTIONS[6])
    pdf.grid(["File", "Lines", "Status"], [[f, n, "OVER - plan refactor" if n > LINE_LIMIT else "ok"]
             for f, n in sorted(a["sizes"].items(), key=lambda kv: -kv[1]) if n], (110, 25, 45))
    if "frontend/app.js" in a["oversize"]:
        pdf.para("**Refactor proposal for app.js:** split into ES modules - api.js (fetch wrappers + API_URL), state.js "
                 "(the three globals), views/browse.js, views/recommend.js, views/applications.js, views/manager.js, ui.js "
                 "(escapeHTML, showMessage, modals). Keep the API_URL literal in one place so deploy/server.py's swap keeps working.", 9)
    pdf.h1(SECTIONS[7]); pdf.bullets([t for t, _ in FINDINGS])
    return pdf


def plain_pdf(a, graph):
    pdf = Report("02 - Plain-English Walkthrough")
    pdf.cover("Net-Worker (ProjectHub)", "02 - Plain-English Walkthrough",
              ["This is the companion to 01_Technical_Architecture_and_Syntax.pdf. Every section number and every box label "
               "(N1-N21) matches that document, so you can read them side by side.",
               "**In one sentence:** ProjectHub is a small website where project leads post open roles and engineers find "
               "matches and apply; our container puts it online behind a team password without changing the team's code."])
    pdf.graph_page(graph, SECTIONS[0])
    pdf.h1(SECTIONS[0] + " - what each box means")
    pdf.grid(["ID", "Box", "What it does"], [[k, v[4].replace("\n", " "), v[5]] for k, v in NODES.items()], (12, 38, 130))
    pdf.h2("Why the arrows go this way")
    pdf.bullets(["Everything goes through **one web address**. The browser sends the password once and then reuses it, and "
                 "there are no cross-site permission problems, because the page and its data come from the same place.",
                 "The **password check sits before everything else** (except the health check), so nothing - not even the "
                 "page layout - leaks to someone without the password.",
                 "The team's backend is **plugged in, not edited**. The wrapper hands it requests under /api and redirects "
                 "where it saves files, so teammates' code stays exactly as they wrote it.",
                 "Data only **flows down** to the filing cabinet through one door (database.py), so there's a single place "
                 "that decides where the data lives."])
    pdf.h1(SECTIONS[1])
    pdf.bullets([f"**Step {i}.** {p}" for i, (_t, p) in enumerate(LIFECYCLE, 1)])
    pdf.h1(SECTIONS[2])
    for f in a["files"]:
        if f in FILE_PLAIN:
            flag = "  - too long, see section 7" if f in a["oversize"] else ""
            pdf.h2(f"{f}{flag}"); pdf.para(FILE_PLAIN[f], 9.5)
    pdf.h1(SECTIONS[3])
    pdf.grid(["Address (on the live site)", "What it's for", "Used by page?"],
             [[f"{r['method']} {r['url']}", ROUTE_PLAIN.get(r["handler"], "-"),
               used_label(r, "no")] for r in a["routes"]], (62, 96, 22))
    pdf.h1(SECTIONS[4])
    pdf.bullets(["**projects** - one row per open role: title, client, skills needed, level, location, start date, status.",
                 "**employees** - one row per person who has applied, found by email. Holds their skills and resume text.",
                 "**applications** - links a person to a project, with a status (Submitted, Under Review, Accepted, "
                 "Rejected). The same person can apply to the same project only once.",
                 "**matches** - meant to store match scores, but nothing writes to it yet; scores are worked out in the browser.",
                 "**Request forms** - the backend checks incoming forms against a fixed shape (name, valid email, etc.) "
                 "and rejects anything that doesn't fit before it touches the database."])
    pdf.h1(SECTIONS[5]); pdf.bullets([p for _, p in STATE])
    pdf.h1(SECTIONS[6])
    if a["oversize"]:
        pdf.para(f"{', '.join(a['oversize'])} is longer than our {LINE_LIMIT}-line limit. It works, but it does five jobs in "
                 "one file (talking to the server, remembering state, and drawing four different tabs), which makes it hard "
                 "for several people to edit at once. The plan is to split it into one small file per job.", 10)
    else:
        pdf.para(f"No file is over {LINE_LIMIT} lines.")
    pdf.h1(SECTIONS[7]); pdf.bullets([p for _, p in FINDINGS])
    pdf.h2("Explaining the system in 30 seconds")
    pdf.para("A visitor opens the Render link and is asked for the team password. Our container then hands them the page. "
             "The page asks the team's backend, through the /api hallway, for open projects, which come out of a single "
             "database file. Applying sends the form and resume back the same way; the backend checks it, files it, and "
             "replies. On the free plan, all saved data resets to ten sample projects whenever the site restarts.", 10)
    return pdf

# ---------------------------------------------------------------- 6. MAIN
def main():
    analysis = analyze()
    graphs = {"tech": OUT / "graph_technical.png", "plain": OUT / "graph_plain.png"}
    draw_graph(graphs["tech"]); draw_graph(graphs["plain"], plain=True)
    for name, builder, g in [("01_Technical_Architecture_and_Syntax.pdf", technical_pdf, graphs["tech"]),
                             ("02_Plain_English_Walkthrough.pdf", plain_pdf, graphs["plain"])]:
        builder(analysis, g).output(str(OUT / name))
        print(f"wrote {OUT / name}")
    print("oversize:", analysis["oversize"] or "none")


if __name__ == "__main__":
    main()
