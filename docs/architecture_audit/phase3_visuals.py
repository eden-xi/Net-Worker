"""Draw the charts and diagrams used by the Phase 3 PDFs.

Usage (from the repo root):
    python docs/architecture_audit/phase3_visuals.py findings     # audit charts (reads branch phase2)
    python docs/architecture_audit/phase3_visuals.py move1        # one move's diagrams
    python docs/architecture_audit/phase3_visuals.py all

Every picture is saved as a PNG in docs/architecture_audit/phase3_visuals/.
Requires: matplotlib. Charts follow one rule: one purple hue for data, red/green only for pass/fail.
"""
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "phase3_visuals"
CODE_SUFFIXES = (".py", ".js", ".css", ".html")

PURPLE, PURPLE_LIGHT = "#7A1FD1", "#D9C2F2"
INK, MUTED, GRID = "#1F1D29", "#6B6879", "#E6E3EC"
GOOD, BAD, WARN = "#1E8E5A", "#C93A3A", "#B7791F"
SURFACE, HIGHLIGHT = "#F6F4FA", "#EFE4FB"

plt.rcParams.update({"font.family": "Segoe UI", "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})


def save(fig, name):
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / name, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / name)


# ------------------------------------------
# 1. File sizes against the 600 / 800 line rules
# ------------------------------------------

def code_line_counts(ref=None):
    """{path: lines} for code files, read from a git branch (ref) or the working tree (None)."""
    if ref:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
    else:
        names = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
    counts = {}
    for name in names:
        if not name.endswith(CODE_SUFFIXES) or name.startswith("docs/"):
            continue
        if ref:
            text = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=ROOT,
                                  capture_output=True, text=True, encoding="utf-8").stdout
        elif (ROOT / name).exists():
            text = (ROOT / name).read_text(encoding="utf-8")
        else:
            continue
        counts[name] = len(text.splitlines())
    return counts


def line_count_chart(counts, title, name):
    items = sorted((item for item in counts.items() if item[1] > 0), key=lambda item: item[1])
    fig, ax = plt.subplots(figsize=(9, 0.28 * len(items) + 1.2))
    colors = [BAD if lines >= 800 else WARN if lines > 600 else PURPLE for _, lines in items]
    ax.barh([path for path, _ in items], [lines for _, lines in items], color=colors, height=0.62)
    for limit, label, color in [(600, "600: split", WARN), (800, "800: hard cap", BAD)]:
        ax.axvline(limit, color=color, linewidth=1, linestyle="--")
        ax.text(limit + 6, len(items) - 0.35, label, color=color, fontsize=8, va="bottom")
    ax.set_ylim(-0.6, len(items) + 0.3)
    for row, (_, lines) in enumerate(items):
        ax.text(lines + 6, row, str(lines), va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, max(880, max(counts.values()) + 80))
    ax.set_xlabel("lines")
    ax.tick_params(axis="y", labelsize=7.5)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title(title, loc="left", fontsize=12, color=INK, fontweight="bold")
    save(fig, name)


# ------------------------------------------
# 2. Findings by area (single-series bar chart, labelled directly)
# ------------------------------------------

FINDINGS = {
    "Backend structure (B1-B3, B8, B13)": 5,
    "Validation & data shapes (B4-B7, B9-B11)": 7,
    "Security (spoofed email, CORS, path rules)": 3,
    "Deploy / marketplace workarounds (D1-D4)": 4,
    "Frontend (811-line app.js, dead UI, alerts)": 5,
    "Repo hygiene (tracked .db, resumes, .pyc)": 3,
    "Testing & logging (B14, B15)": 2,
}


def findings_chart():
    items = sorted(FINDINGS.items(), key=lambda item: item[1])
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.barh([label for label, _ in items], [count for _, count in items], color=PURPLE, height=0.6)
    for row, (_, count) in enumerate(items):
        ax.text(count + 0.1, row, str(count), va="center", fontsize=9, color=INK)
    ax.set_xlabel("number of findings")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title("Audit findings by area (29 total)", loc="left", fontsize=12, color=INK, fontweight="bold")
    save(fig, "findings_by_area.png")


# ------------------------------------------
# 3. Layer diagrams: boxes stacked top to bottom, with notes on the right
# ------------------------------------------

def box(ax, x, y, w, h, title, subtitle="", fill=SURFACE, edge=GRID, title_color=INK, title_size=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.12",
                                facecolor=fill, edgecolor=edge, linewidth=1.3))
    ax.text(x + 0.18, y + h - 0.2, title, fontsize=title_size, fontweight="bold", color=title_color, va="top")
    if subtitle:
        ax.text(x + 0.18, y + h - 0.55, subtitle, fontsize=8.3, color=MUTED, va="top", linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, color=MUTED, text=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, linewidth=1.2, shrinkA=0, shrinkB=0))
    if text:
        ax.text((x1 + x2) / 2 + 0.12, (y1 + y2) / 2, text, fontsize=7.5, color=color, va="center")


def stack_diagram(name, title, rows, highlight=(), note_color=BAD, width=7.2):
    """rows: [(key, title, subtitle, note)]. Highlighted keys get a purple border."""
    height = 1.15
    gap = 0.45
    total = len(rows) * (height + gap)
    fig, ax = plt.subplots(figsize=(12, total * 0.62 + 0.8))
    ax.set_xlim(0, 13)
    ax.set_ylim(-0.2, total + 0.2)
    ax.axis("off")
    for index, (key, label, subtitle, note) in enumerate(rows):
        y = total - (index + 1) * (height + gap) + gap
        lit = key in highlight
        box(ax, 0.2, y, width, height, label, subtitle, fill=HIGHLIGHT if lit else SURFACE,
            edge=PURPLE if lit else GRID, title_color=PURPLE if lit else INK)
        if note:
            ax.text(width + 0.55, y + height / 2, note, fontsize=8.6, color=note_color, va="center",
                    linespacing=1.35)
            ax.plot([width + 0.25, width + 0.45], [y + height / 2] * 2, color=note_color, linewidth=1)
        if index < len(rows) - 1:
            arrow(ax, 0.2 + width / 2, y, 0.2 + width / 2, y - gap)
    ax.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
    save(fig, name)


BEFORE_ROWS = [
    ("browser", "Browser: two frontends", "frontend/app.js (811 lines, old UI)  +  marketplace/frontend/ (login wall)",
     "Two UIs, two stylesheets, no shared API helper"),
    ("deploy", "deploy/server.py: outer wrapper", "team password, serves frontend, rewrites app.js text at serve time",
     "Monkeypatches DATABASE_PATH / RESUME_FOLDER on\ntwo copies of the database module (hidden magic)"),
    ("mp", "marketplace/server.py + auth.py", "login cookie, regex rule table on URL paths, /mp/manager routes",
     "Rules only see URLs: anything that skips /api/...\n(e.g. a future MCP tool) skips the rules"),
    ("api", "backend/api/*.py: route handlers", "HTTP + validation + SQL + file handling mixed in each function",
     "Duplicate apply endpoints, free-text statuses,\nmanual open/close (leaks), email taken from the form"),
    ("db", "backend/database/database.py", "imported twice (sys.path hack); ALTER TABLE inside a request",
     "Paths hard-coded to the repo folder"),
    ("store", "SQLite file + uploads/ folder", "on Render: inside the container (wiped on sleep / deploy)",
     "Listings vanish; real data also committed to git"),
]

AFTER_ROWS = [
    ("frontend", "frontend/: one UI", "js/core (api, state, ui) + js/views (browse, applications, manage, review) + css/", ""),
    ("server", "deploy/server.py: one server", "team password, static files, mounts the API at /api. No patching.", ""),
    ("routes", "backend/routes/: HTTP only", "thin endpoints; Depends(current_user / require_manager / get_db)", ""),
    ("schemas", "backend/schemas/: data shapes", "Pydantic models + StrEnum statuses (also future MCP tool schemas)", ""),
    ("services", "backend/services/ + backend/matching/: the logic", "plain functions holding all SQL; reused by routes, tests, and later the agent", ""),
    ("core", "backend/core/: foundation", "config (env settings), db (connections + schema), errors, security", ""),
    ("store", "SQLite in DATA_DIR", "DATA_DIR=/data -> Render persistent disk (or Postgres later)", ""),
]

MOVE_NOTES = {
    "move1": (("core", "server"), {"core": "Move 1: config.py + db.py replace hard-coded\npaths, sys.path hack and monkeypatching",
                                   "server": "Move 1: no more patching module globals"}),
    "move2": (("schemas", "services", "routes", "frontend"),
              {"schemas": "Move 2: one list of statuses, typed in/out models",
               "services": "Move 2: SQL lives here, once",
               "routes": "Move 2: handlers shrink to 'validate -> service -> schema'",
               "frontend": "Move 2: marketplace UI becomes the only UI"}),
    "move3": (("core", "routes"), {"core": "Move 3: security.py: current_user, require_manager",
                                   "routes": "Move 3: every router is login-protected by default;\nidentity comes from the session, not the form"}),
    "move4": (("store", "services"), {"store": "Move 4: DATA_DIR on a persistent disk survives restarts",
                                      "services": "Move 4: activity.py records every change (activity_events)"}),
    "move5": (("frontend", "services"), {"frontend": "Move 5: tokens, badges, skeletons, toasts, 3-pane review",
                                         "services": "Move 5: matching/skill_match.py scores people vs listings"}),
}


def architecture_before():
    stack_diagram("architecture_before.png", "Before (phase2): how a request travels today", BEFORE_ROWS)


def architecture_after(move=None):
    if move is None:
        stack_diagram("architecture_after.png", "After (phase3): one clear path, one job per layer", AFTER_ROWS)
        return
    keys, notes = MOVE_NOTES[move]
    rows = [(key, label, sub, notes.get(key, "")) for key, label, sub, _ in AFTER_ROWS]
    stack_diagram(f"{move}_layers.png", f"{move.replace('move', 'Move ')}: what changed (purple)", rows,
                  highlight=keys, note_color=PURPLE)


def flow_diagram(name, title, steps, per_row=4):
    """steps: [(title, subtitle)]. Numbered boxes, left to right, wrapping into rows."""
    rows = (len(steps) + per_row - 1) // per_row
    fig, ax = plt.subplots(figsize=(12, 2.1 * rows + 0.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 2.4 * rows)
    ax.axis("off")
    width, height = 2.75, 1.55
    positions = []
    for index, (label, subtitle) in enumerate(steps):
        row, column = divmod(index, per_row)
        x = 0.2 + column * 3.2
        y = 2.4 * (rows - row - 1) + 0.4
        positions.append((x, y))
        box(ax, x, y, width, height, f"{index + 1}. {label}", subtitle, fill=HIGHLIGHT if index in (0, len(steps) - 1)
            else SURFACE, edge=PURPLE if index in (0, len(steps) - 1) else GRID, title_size=9.2)
    for (x1, y1), (x2, y2) in zip(positions, positions[1:]):
        if abs(y1 - y2) < 0.01:
            arrow(ax, x1 + width, y1 + height / 2, x2, y2 + height / 2)
        else:
            arrow(ax, x1 + width / 2, y1, x2 + width / 2, y2 + height)
    ax.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
    save(fig, name)


FLOWS = {
    "move2": ("One request, layer by layer: POST /api/applications", [
        ("Browser", "employee.js sends the form\n+ PDF as FormData"),
        ("routes/applications.py", "apply(): Form fields\nvalidated by FastAPI"),
        ("services/resumes.py", "read_valid_resume():\ntype, size, real PDF?, text"),
        ("services/applications.py", "submit(): listing open?\nalready applied?"),
        ("core/db.py transaction()", "one writer at a time;\nprofile + application\nsaved together"),
        ("SQLite + resume file", "rows in DATA_DIR;\nfile under a random name"),
        ("schemas ApplicationReceipt", "response_model decides\nexactly what goes back"),
        ("Browser", "201 + receipt JSON\n(errors: 400/404/409/413)"),
    ]),
    "move3": ("One request, layer by layer: PATCH /api/applications/7/status", [
        ("Browser", "manager clicks Accept;\ncookie goes with it"),
        ("deploy/server.py", "team password check\n(the browser pop-up)"),
        ("Depends(current_user)", "cookie -> session -> User\nnone? 401 'Please log in'"),
        ("Depends(require_manager)", "User.role == manager?\nno? 403"),
        ("routes/applications.py", "change_status(): body\nvalidated by the schema"),
        ("services/applications.py", "set_status(): UPDATE in\na transaction"),
        ("schemas ApplicationStatusOut", "the response shape"),
        ("Browser", "200: the new status\nshows on screen"),
    ]),
}


# ------------------------------------------
# 4. Database tables (Move 4)
# ------------------------------------------

TABLES = {
    "projects": (0.3, 4.1, ["id", "role_id (unique)", "title", "required_skills", "status: Open|Closed|Filled",
                            "posted_by_email / _name", "created_at"]),
    "applications": (4.6, 4.1, ["id", "employee_id -> employees", "project_id -> projects",
                                "application_status", "resume_filename", "cover_letter", "submitted_at / updated_at"]),
    "employees": (8.9, 4.1, ["id", "email (unique)", "name", "skills", "resume_filename", "resume_text"]),
    "activity_events  (new)": (4.6, 0.5, ["id", "kind", "actor_email / actor_name", "project_id", "application_id",
                                          "from_status -> to_status", "created_at"]),
}
LINE = 0.205          # height of one text line in this figure's units


def tables_diagram():
    fig, ax = plt.subplots(figsize=(12, 6.4))
    ax.set_xlim(0, 13)
    ax.set_ylim(0.2, 6.4)
    ax.axis("off")
    for name, (x, y, columns) in TABLES.items():
        is_new = "new" in name
        box(ax, x, y, 3.8, LINE * len(columns) + 0.85, name, "\n".join(columns),
            fill=HIGHLIGHT if is_new else SURFACE, edge=PURPLE if is_new else GRID,
            title_color=PURPLE if is_new else INK)
    arrow(ax, 4.6, 5.3, 4.1, 5.3)
    arrow(ax, 8.4, 5.3, 8.9, 5.3)
    arrow(ax, 6.5, 0.5 + LINE * 7 + 0.85, 6.5, 4.1, color=PURPLE)
    ax.text(6.65, 3.2, "every post / submit / status change\nwrites one event row (same transaction)",
            fontsize=8.5, color=PURPLE, va="center")
    ax.text(8.9, 1.4, "Powers:\n - the manager's live activity feed\n - each application's timeline\n"
            " - later: an audit trail of agent actions", fontsize=8.5, color=MUTED, va="center")
    ax.set_title("Database tables after Move 4 (arrows = foreign keys / writes)", loc="left",
                 fontsize=13, color=INK, fontweight="bold")
    save(fig, "move4_tables.png")


# ------------------------------------------
# 5. Stress-test results (written by tests/stress/load_test.py --out ...)
# ------------------------------------------

def results_chart(move):
    path = OUT / f"{move}_load.json"
    if not path.exists():
        print("skip: no", path)
        return
    results = json.loads(path.read_text())["scenarios"]
    names = [item["name"] for item in results]
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(names) + 1.4))
    rows = range(len(names))
    ax.barh([row + 0.18 for row in rows], [item["p50_ms"] for item in results], height=0.34,
            color=PURPLE_LIGHT, label="median (p50)")
    ax.barh([row - 0.18 for row in rows], [item["p95_ms"] for item in results], height=0.34,
            color=PURPLE, label="slowest 5% (p95)")
    for row, item in enumerate(results):
        ok = item["errors"] == 0
        ax.text(item["p95_ms"] * 1.02 + 1, row - 0.18,
                f"{item['p95_ms']:.0f} ms   {item['requests']} req, {item['errors']} errors",
                va="center", fontsize=8, color=GOOD if ok else BAD)
    ax.set_yticks(list(rows), names, fontsize=8.5)
    ax.set_xlabel("response time (ms)")
    ax.set_xlim(0, max(item["p95_ms"] for item in results) * 1.6 + 5)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title(f"{move.replace('move', 'Move ')} stress test: concurrent requests", loc="left",
                 fontsize=12, color=INK, fontweight="bold")
    save(fig, f"{move}_load.png")


def trend_chart():
    """Apply-with-PDF latency across the moves (one measure, one axis)."""
    moves, p50, p95 = [], [], []
    for move in MOVE_NOTES:
        path = OUT / f"{move}_load.json"
        if path.exists():
            apply = next(item for item in json.loads(path.read_text())["scenarios"] if item["name"].startswith("apply"))
            moves.append(move.replace("move", "Move "))
            p50.append(apply["p50_ms"])
            p95.append(apply["p95_ms"])
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(moves, p95, color=PURPLE, linewidth=2, marker="o", markersize=8, label="slowest 5% (p95)")
    ax.plot(moves, p50, color=PURPLE_LIGHT, linewidth=2, marker="o", markersize=8, label="median (p50)")
    for x, value in zip(moves, p95):
        ax.annotate(f"{value:.0f} ms", (x, value), textcoords="offset points", xytext=(0, 9), ha="center",
                    fontsize=8.5, color=INK)
    ax.set_ylabel("ms (25 applies at once)")
    ax.set_ylim(0, max(p95) * 1.3)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title("Apply with a PDF: response time after each move", loc="left", fontsize=12, color=INK,
                 fontweight="bold")
    save(fig, "trend_apply.png")


# ------------------------------------------
# 6. Agent + MCP plan (diagram only, nothing is built)
# ------------------------------------------

def agent_plan():
    fig, ax = plt.subplots(figsize=(12, 6.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7)
    ax.axis("off")
    box(ax, 0.2, 5.3, 3.0, 1.2, "Browser", "frontend/js/views/assistant.js\n(chat panel, confirm buttons)")
    box(ax, 4.2, 5.3, 4.2, 1.2, "routes/agent.py  (/api/agent/chat)", "Depends(current_user): the agent\nalways acts AS the signed-in person")
    box(ax, 4.2, 3.1, 4.2, 1.5, "backend/agent/", "agent.py   - tool loop (LLM call -> tool -> repeat)\nprompts.py - instructions + guardrails\npolicy.py  - which tools each role may use",
        fill=HIGHLIGHT, edge=PURPLE, title_color=PURPLE)
    box(ax, 9.3, 3.1, 3.5, 1.5, "backend/mcp/server.py", "MCP tools = thin wrappers\nover services (read first,\nwrite tools need confirm)",
        fill=HIGHLIGHT, edge=PURPLE, title_color=PURPLE)
    box(ax, 4.2, 0.7, 4.2, 1.5, "backend/services/ + matching/", "the SAME functions the REST routes use\n(projects, applications, activity, skill_match)")
    box(ax, 9.3, 0.7, 3.5, 1.5, "activity_events", "every agent action logged with\nactor = 'agent for <person>'")
    box(ax, 0.2, 2.9, 3.0, 1.7, "LLM API", "key in Render env vars\n(never in git)\nmodel chosen in config.py")
    arrow(ax, 3.2, 5.9, 4.2, 5.9, text="")
    arrow(ax, 6.3, 5.3, 6.3, 4.6)
    arrow(ax, 4.2, 3.8, 3.2, 3.8, text="")
    arrow(ax, 8.4, 3.85, 9.3, 3.85)
    arrow(ax, 11.0, 3.1, 8.4, 1.5)
    arrow(ax, 8.4, 1.45, 9.3, 1.45)
    ax.plot([3.75, 3.75], [0.4, 6.8], color=BAD, linestyle=":", linewidth=1.2)
    ax.text(3.82, 6.75, "trust boundary: model output is a suggestion,\nservices + policy decide what actually happens",
            fontsize=7.8, color=BAD, va="top")
    ax.set_title("Planned: agent + MCP server (not built yet)", loc="left", fontsize=13, color=INK, fontweight="bold")
    save(fig, "agent_plan.png")


# ------------------------------------------
# Command line
# ------------------------------------------

def main(target):
    if target in ("findings", "all"):
        findings_chart()
        line_count_chart(code_line_counts("phase2"), "Code file sizes on phase2 (before)", "line_counts_before.png")
        architecture_before()
        architecture_after()
    for move in MOVE_NOTES:
        if target in (move, "all"):
            architecture_after(move)
            results_chart(move)
            if move in FLOWS:
                flow_diagram(f"{move}_flow.png", *FLOWS[move])
            if move == "move4":
                tables_diagram()
    if target in ("after", "all"):
        line_count_chart(code_line_counts(), "Code file sizes on phase3 (after)", "line_counts_after.png")
        trend_chart()
    if target in ("agent", "all"):
        agent_plan()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
