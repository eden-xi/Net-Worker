"""
Demo-level UI check: drive the real site in Microsoft Edge, the way people would.

Run from the repo root:
    python tests/stress/ui_walkthrough.py --move move5

Two browser windows, like a live demo with two laptops:
  employee window: sign in -> save skills -> feed shows "% match" -> open a listing -> apply with a PDF
                   -> stays on "My applications"
  manager window:  sign in -> Overview shows the new application live -> Review applicants ->
                   PDF inline, ranked by match -> keyboard "U" -> click Accept
  employee window: the tracker turns to "Accepted" BY ITSELF (no reload), within one refresh.
Every step is a check. Screenshots go to docs/architecture_audit/phase3_visuals/<move>_ui_*.png.

Requires: playwright (with Edge installed), pymupdf, httpx.
"""

import argparse
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_test import RESULTS, TEAM_PASSWORD, free_port, make_pdf, start_server  # noqa: E402

# Selectors in one place: if the page layout changes, only this block changes.
PAGE = {
    "card": ".listing-card:not(.skeleton)",
    "match_pill": ".listing-card .match",
    "drawer_apply": "#drawer-apply",
    "apply_form": "#apply-form",
    "apply_status": "#apply-status",
    "tracker_badge": "#tracker .tracker-card .badge",
    "activity_item": "#activity-list .activity-item",
    "listing_with_one": "[data-listing-id]:has(.numeric:text-is('1'))",
    "pdf_frame": ".pdf-frame",
    "decision_status": "#decision-status",
    "accept": "[data-decide=Accepted]",
}


class Checks:
    def __init__(self, move):
        self.move = move
        self.results = []

    def check(self, name, passed):
        self.results.append((name, bool(passed)))
        print(("PASS " if passed else "FAIL ") + name)

    def shot(self, page, name):
        page.screenshot(path=str(RESULTS / f"{self.move}_ui_{name}.png"))


def window(browser, errors, width=1440, height=900):
    context = browser.new_context(http_credentials={"username": TEAM_PASSWORD[0], "password": TEAM_PASSWORD[1]},
                                  viewport={"width": width, "height": height})
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    return page


def sign_in(page, base, role, email, password):
    page.goto(base)
    page.wait_for_selector("#login-wall:not(.hidden)")
    page.click(f"[data-role-option={role}]")
    page.fill("#login-email", email)
    page.fill("#login-password", password)
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#app-shell:not(.hidden)")


def text_of(page, selector):
    return page.locator(selector).first.inner_text().strip()


def run(move, base):
    checks = Checks(move)
    pdf_path = Path(tempfile.mkdtemp()) / "erin-resume.pdf"
    pdf_path.write_bytes(make_pdf("Erin Employee. Python, FastAPI and SQL. Built payment APIs."))
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        employee = window(browser, errors)
        manager = window(browser, errors)

        # ---------- login wall ----------
        employee.goto(base)
        employee.wait_for_selector("#login-wall:not(.hidden)")
        checks.check("login wall offers Employee and Project Manager", employee.locator("[data-role-option]").count() == 2)
        checks.shot(employee, "1_login")

        # ---------- employee: skills -> matches -> apply ----------
        sign_in(employee, base, "employee", "employee@networker.test", "employee-demo")
        employee.goto(f"{base}/#/employee/profile")
        employee.fill("#profile-form [name=skills]", "Python, FastAPI, SQL, Docker")
        employee.click("#profile-form button[type=submit]")
        employee.wait_for_selector(".toast")

        employee.goto(f"{base}/#/employee/browse")
        employee.wait_for_selector(PAGE["match_pill"])
        first_card = employee.locator(PAGE["card"]).first
        checks.check("feed shows a % match on every card", employee.locator(PAGE["match_pill"]).count() == 10)
        checks.check("best match is sorted first (100%)", first_card.locator(".match").inner_text() == "100% match")
        checks.shot(employee, "2_feed_matches")

        first_card.click()
        employee.wait_for_selector(PAGE["drawer_apply"])
        checks.check("listing drawer explains the fit", employee.locator("#modal .chip.matched").count() >= 3)
        employee.wait_for_timeout(400)                                   # let the drawer finish sliding in
        checks.shot(employee, "3_drawer")
        employee.click(PAGE["drawer_apply"])
        employee.wait_for_selector(PAGE["apply_form"])
        employee.fill(f"{PAGE['apply_form']} [name=cover_letter]", "I built payment APIs before and would love this.")
        employee.set_input_files(f"{PAGE['apply_form']} [name=resume]", str(pdf_path))
        employee.click(f"{PAGE['apply_form']} button[type=submit]")
        employee.wait_for_function(
            f"document.querySelector('{PAGE['apply_status']}')?.textContent.includes('successfully')")
        checks.check("application submitted with a PDF", True)

        employee.goto(f"{base}/#/employee/applications")
        employee.wait_for_selector(PAGE["tracker_badge"])
        checks.check("tracker shows Submitted", text_of(employee, PAGE["tracker_badge"]) == "Submitted")

        # ---------- manager: overview -> review -> decide ----------
        sign_in(manager, base, "manager", "manager@networker.test", "manager-demo")
        manager.wait_for_selector(PAGE["activity_item"])
        checks.check("overview feed shows the new application",
                     "applied to" in manager.locator("#activity-list").inner_text())
        checks.shot(manager, "4_overview")

        manager.goto(f"{base}/#/manager/review")
        manager.wait_for_selector(PAGE["listing_with_one"])
        manager.click(PAGE["listing_with_one"])
        manager.wait_for_selector(PAGE["pdf_frame"])
        manager.wait_for_timeout(3500)                                   # let Edge render the PDF for the screenshot
        checks.check("PDF opens inline next to the listing", manager.locator(PAGE["pdf_frame"]).count() == 1)
        checks.check("applicant ranked with a % match", "% match" in manager.locator("#review-left").inner_text())
        checks.shot(manager, "5_review")

        manager.locator("body").press("u")
        manager.wait_for_function(f"document.querySelector('{PAGE['decision_status']}').textContent.includes('Under Review')")
        checks.check("keyboard U marks Under Review", True)
        manager.click(PAGE["accept"])
        manager.wait_for_function(f"document.querySelector('{PAGE['decision_status']}').textContent.includes('Accepted')")
        manager.wait_for_function("[...document.querySelectorAll('.toast')].some(t => t.textContent.includes('Accepted'))")
        checks.check("Accept saved (toast shown)", True)

        # ---------- employee: live update without reloading ----------
        employee.wait_for_function(
            f"document.querySelector('{PAGE['tracker_badge']}').textContent.trim() === 'Accepted'", timeout=15000)
        checks.check("employee tracker turned Accepted by itself (no reload)", True)
        employee.wait_for_timeout(400)
        checks.check("stepper shows all three steps reached", employee.locator(".step.done, .step.good").count() == 3)
        checks.shot(employee, "6_tracker")

        # ---------- dark mode + phone width ----------
        manager.click("#theme-toggle")
        manager.reload()                                                 # theme is remembered; reopen the page
        manager.wait_for_selector(PAGE["listing_with_one"])
        manager.click(PAGE["listing_with_one"])
        manager.wait_for_selector(PAGE["pdf_frame"])
        manager.wait_for_timeout(3500)
        checks.check("dark mode switches the theme",
                     manager.evaluate("document.documentElement.dataset.theme") == "dark")
        checks.shot(manager, "7_review_dark")

        phone = window(browser, errors, width=390, height=844)
        sign_in(phone, base, "employee", "employee@networker.test", "employee-demo")
        phone.wait_for_selector(PAGE["card"])
        no_sideways_scroll = phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        checks.check("phone width: no sideways scrolling", no_sideways_scroll)
        checks.shot(phone, "8_phone")

        checks.check("no JavaScript errors in any window", not errors)
        if errors:
            print("   first error:", errors[0])
        browser.close()
    return checks.results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--move", required=True)
    args = parser.parse_args()

    port = free_port()
    server = start_server(port, login_mode="test")          # the real test accounts, real names
    try:
        results = run(args.move, f"http://127.0.0.1:{port}")
    finally:
        server.terminate()
        server.wait(timeout=10)

    failed = [name for name, passed in results if not passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} UI checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
