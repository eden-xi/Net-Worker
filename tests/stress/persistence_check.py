"""
Demo-level persistence check with the REAL container (the same image Render runs).

Run from the repo root (Docker Desktop must be running):
    docker build -f deploy/Dockerfile -t networker:phase3 .
    python tests/stress/persistence_check.py

What it does:
  A. WITH a volume at /data (what a Render persistent disk gives us):
     start -> post a listing + apply -> restart the container -> is everything still there?
  B. WITHOUT a volume (what Render's free tier does today):
     start -> post a listing -> remove + start a new container -> it is gone, 10 demo listings back.
"""

import subprocess
import sys
import time

import httpx

IMAGE = "networker:phase3"
VOLUME = "networker-persistence-check"
AUTH = ("team", "persist-check")
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout.strip()


def start(name, with_volume):
    volume = ["-v", f"{VOLUME}:/data"] if with_volume else []
    docker("run", "-d", "--name", name, "-p", f"{PORT}:8000", "-e", f"APP_PASSWORD={AUTH[1]}", *volume, IMAGE)
    wait_until_up()


def wait_until_up():
    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/healthz", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("container did not start")


def remove(name):
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def signed_in(email, role):
    client = httpx.Client(base_url=BASE, auth=AUTH, timeout=15)
    client.post("/api/auth/login", json={"email": email, "password": "employee-demo" if role == "employee"
                                         else "manager-demo", "role": role}).raise_for_status()
    return client


def titles(client):
    return [listing["title"] for listing in client.get("/api/projects").json()]


def main():
    checks = []
    remove("nw-persist")
    subprocess.run(["docker", "volume", "rm", "-f", VOLUME], capture_output=True)

    # ---- A. with a volume ----
    start("nw-persist", with_volume=True)
    manager = signed_in("manager@networker.test", "manager")
    manager.post("/api/projects", json={"title": "Persistence check listing"}).raise_for_status()
    project_id = next(item["id"] for item in manager.get("/api/projects").json()
                      if item["title"] == "Persistence check listing")
    employee = signed_in("employee@networker.test", "employee")
    employee.post("/api/applications", data={"project_id": project_id}).raise_for_status()
    since_before = manager.get("/api/health").json()["data_since"]

    docker("restart", "nw-persist")
    wait_until_up()

    manager = signed_in("manager@networker.test", "manager")       # sessions live in memory: sign in again
    employee = signed_in("employee@networker.test", "employee")
    health = manager.get("/api/health").json()
    checks.append(("A. listing survives a container restart", "Persistence check listing" in titles(manager)))
    checks.append(("A. application survives too", len(employee.get("/api/applications/mine").json()) == 1))
    checks.append(("A. activity log survives too",
                   any("Persistence check listing" in event["message"]
                       for event in manager.get("/api/insights/activity").json())))
    checks.append(("A. data_since unchanged, older than server_started",
                   health["data_since"] == since_before and health["data_since"] < health["server_started"]))
    remove("nw-persist")

    # ---- B. without a volume ----
    start("nw-persist", with_volume=False)
    manager = signed_in("manager@networker.test", "manager")
    manager.post("/api/projects", json={"title": "Will be lost"}).raise_for_status()
    remove("nw-persist")
    start("nw-persist", with_volume=False)
    manager = signed_in("manager@networker.test", "manager")
    after = titles(manager)
    checks.append(("B. without a volume the listing is gone", "Will be lost" not in after))
    checks.append(("B. ...and the 10 demo listings are back", len(after) == 10))
    remove("nw-persist")
    subprocess.run(["docker", "volume", "rm", "-f", VOLUME], capture_output=True)

    for name, passed in checks:
        print(("PASS " if passed else "FAIL ") + name)
    failed = [name for name, passed in checks if not passed]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} persistence checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
