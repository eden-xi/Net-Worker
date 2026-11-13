"""
Demo-level stress test: start the real server, then hit it with many requests at once.

Run from the repo root:
    python tests/stress/load_test.py --move move1

What it does:
  1. Starts uvicorn on a free port with an EMPTY temporary data folder, the team password ON,
     and open login mode (so we can sign in as many different employees).
  2. Signs in N employees and one manager (real cookies, real password header).
  3. Runs each scenario: `requests` calls, `concurrency` at the same time.
  4. Prints a table and saves docs/architecture_audit/phase3_visuals/<move>_load.json
     (phase3_visuals.py turns that into a chart for the PDF).

Requires: httpx, pymupdf (for the test PDF).
"""

import argparse
import asyncio
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import fitz
import httpx

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs" / "architecture_audit" / "phase3_visuals"

# These two lines change when the server's layout changes (see each move's PDF).
SERVER_APP = "marketplace.server:app"
AUTH = "/mp/auth"
MANAGER_LISTINGS = "/mp/manager/projects"

TEAM_PASSWORD = ("team", "stress-test")


# ------------------------------------------
# 1. Start / stop the server
# ------------------------------------------

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port):
    env = {
        **os.environ,
        "DATA_DIR": tempfile.mkdtemp(prefix="networker-stress-"),
        "APP_USERNAME": TEAM_PASSWORD[0],
        "APP_PASSWORD": TEAM_PASSWORD[1],
        "MARKETPLACE_LOGIN_MODE": "open",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.pop("ALLOW_NO_AUTH", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", SERVER_APP, "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
    )
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.2)
    process.kill()
    raise RuntimeError("The server did not start.")


# ------------------------------------------
# 2. Helpers
# ------------------------------------------

def make_pdf():
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Stress resume: Python, FastAPI, SQL, Docker")
    data = document.tobytes()
    document.close()
    return data


async def signed_in_client(base, email, role):
    client = httpx.AsyncClient(base_url=base, auth=TEAM_PASSWORD, timeout=30)
    response = await client.post(f"{AUTH}/login", json={"email": email, "password": "x", "role": role})
    response.raise_for_status()
    return client


def summary(name, latencies, errors, seconds):
    ordered = sorted(latencies)
    p95_index = max(0, int(len(ordered) * 0.95) - 1)
    return {
        "name": name,
        "requests": len(latencies),
        "errors": errors,
        "p50_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(ordered[p95_index], 1),
        "max_ms": round(ordered[-1], 1),
        "per_second": round(len(latencies) / seconds, 1),
    }


async def run(name, total, concurrency, send):
    """Call send(i) `total` times, `concurrency` at once. send returns an httpx response."""
    gate = asyncio.Semaphore(concurrency)
    latencies, failures = [], []

    async def one(i):
        async with gate:
            started = time.perf_counter()
            try:
                response = await send(i)
                if response.status_code >= 400:
                    failures.append(f"{response.status_code}: {response.text[:80]}")
            except httpx.HTTPError as error:
                failures.append(repr(error))
            latencies.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(total)))
    result = summary(name, latencies, len(failures), time.perf_counter() - started)
    if failures:
        result["first_error"] = failures[0]
    return result


# ------------------------------------------
# 3. Scenarios
# ------------------------------------------

async def scenarios(base, employees_count, concurrency):
    pdf = make_pdf()
    results = []

    # Sign-ins are a scenario too: every employee is a different person.
    # Clients are created first, so the timing measures the server, not client set-up.
    employees = [httpx.AsyncClient(base_url=base, auth=TEAM_PASSWORD, timeout=30)
                 for _ in range(employees_count)]

    async def sign_in(i):
        return await employees[i].post(f"{AUTH}/login", json={
            "email": f"stress{i}@load.test", "password": "x", "role": "employee"})

    results.append(await run("sign in (distinct employees)", employees_count, concurrency, sign_in))
    manager = await signed_in_client(base, "lead@load.test", "manager")
    projects = (await employees[0].get("/api/projects")).json()

    results.append(await run("browse open listings", 400, concurrency,
                             lambda i: employees[i % len(employees)].get("/api/projects")))
    results.append(await run("open one listing", 400, concurrency,
                             lambda i: employees[i % len(employees)].get(f"/api/projects/{projects[i % len(projects)]['id']}")))

    async def apply(i):
        client = employees[i]
        email = f"stress{i}@load.test"
        return await client.post("/api/applications/submit-with-resume", data={
            "project_id": projects[i % len(projects)]["id"], "name": f"Stress {i}", "email": email,
            "skills": "Python, SQL", "cover_letter": "Load test",
        }, files={"resume": ("cv.pdf", pdf, "application/pdf")})

    results.append(await run("apply with PDF (writes)", employees_count, concurrency, apply))
    results.append(await run("manager: all listings + counts", 200, concurrency,
                             lambda i: manager.get(MANAGER_LISTINGS)))

    for client in employees + [manager]:
        await client.aclose()
    return results


# ------------------------------------------
# 4. Command line
# ------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--move", required=True, help="label for the results file, e.g. move1")
    parser.add_argument("--employees", type=int, default=150)
    parser.add_argument("--concurrency", type=int, default=25)
    args = parser.parse_args()

    port = free_port()
    server = start_server(port)
    try:
        results = asyncio.run(scenarios(f"http://127.0.0.1:{port}", args.employees, args.concurrency))
    finally:
        server.terminate()
        server.wait(timeout=10)

    print(f"\n{'scenario':38} {'req':>5} {'err':>4} {'p50 ms':>8} {'p95 ms':>8} {'req/s':>7}")
    for item in results:
        print(f"{item['name']:38} {item['requests']:>5} {item['errors']:>4} "
              f"{item['p50_ms']:>8} {item['p95_ms']:>8} {item['per_second']:>7}")
        if item.get("first_error"):
            print("   first error:", item["first_error"])

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{args.move}_load.json"
    out.write_text(json.dumps({"move": args.move, "concurrency": args.concurrency, "scenarios": results}, indent=2))
    print("saved", out)
    sys.exit(1 if any(item["errors"] for item in results) else 0)


if __name__ == "__main__":
    main()
