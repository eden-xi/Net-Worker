"""
Demo-level UI check: drive the real site in Microsoft Edge, the way a person would.

Run from the repo root:
    python tests/stress/ui_walkthrough.py --move move2

Flow:  login wall -> employee signs in -> applies with a PDF -> sees it in "My applications"
       -> signs out -> manager signs in -> opens the applicant -> PDF shows inline -> changes status
       -> employee signs back in and sees the new status.
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
    "employee_option": "[data-role-option=employee]",
    "manager_option": "[data-role-option=manager]",
    "fill_demo": "#fill-demo",
    "email": "#login-email",
    "password": "#login-password",
    "submit_login": "#login-form button[type=submit]",
    "card": ".listing-card",
    "apply_button": ".listing-card [data-action=apply]",
    "apply_form": "#apply-form",
    "apply_status": "#apply-status",
    "logout": "#logout-button",
    "my_applications_status": "#my-applications .pill",
    "review_picker": "#review-listing",
    "applicant": ".applicant",
    "pdf_frame": ".pdf-frame",
    "status_select": "#application-status-select",
    "status_note": "#application-status-note",
}


class Walkthrough:
    def __init__(self, page, move):
        self.page = page
        self.move = move
        self.checks = []

    def check(self, name, passed):
        self.checks.append((name, bool(passed)))
        print(("PASS " if passed else "FAIL ") + name)

    def shot(self, name):
        path = RESULTS / f"{self.move}_ui_{name}.png"
        self.page.screenshot(path=str(path))
        return path

    def sign_in(self, role, email, password):
        page = self.page
        page.click(PAGE[f"{role}_option"])
        page.fill(PAGE["email"], email)
        page.fill(PAGE["password"], password)
        page.click(PAGE["submit_login"])
        page.wait_for_selector("#app-shell:not(.hidden)")

    def sign_out(self):
        self.page.click(PAGE["logout"])
        self.page.wait_for_selector("#login-wall:not(.hidden)")


def run(move, base):
    pdf_path = Path(tempfile.mkdtemp()) / "erin-resume.pdf"
    pdf_path.write_bytes(make_pdf())

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context(http_credentials={"username": TEAM_PASSWORD[0], "password": TEAM_PASSWORD[1]},
                                      viewport={"width": 1440, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        walk = Walkthrough(page, move)

        page.goto(base)
        page.wait_for_selector("#login-wall:not(.hidden)")
        walk.check("login wall shows two role options", page.locator("[data-role-option]").count() == 2)
        walk.shot("1_login")

        # ---- employee applies ----
        walk.sign_in("employee", "employee@networker.test", "employee-demo")
        page.wait_for_selector(PAGE["card"])
        walk.check("employee sees the listing feed", page.locator(PAGE["card"]).count() >= 10)
        walk.shot("2_feed")

        page.locator(PAGE["apply_button"]).first.click()
        page.wait_for_selector(PAGE["apply_form"])
        page.fill(f"{PAGE['apply_form']} [name=skills]", "Python, FastAPI, SQL")
        page.fill(f"{PAGE['apply_form']} [name=cover_letter]", "I built payment APIs before.")
        page.set_input_files(f"{PAGE['apply_form']} [name=resume]", str(pdf_path))
        page.click(f"{PAGE['apply_form']} button[type=submit]")
        page.wait_for_function(f"document.querySelector('{PAGE['apply_status']}').textContent.includes('successfully')")
        walk.check("application submitted with a PDF", True)

        page.goto(f"{base}/#/employee/applications")
        page.wait_for_selector(PAGE["my_applications_status"])
        walk.check("it appears in My applications as Submitted",
                   page.locator(PAGE["my_applications_status"]).first.inner_text().strip() == "Submitted")
        walk.sign_out()

        # ---- manager reviews ----
        walk.sign_in("manager", "manager@networker.test", "manager-demo")
        page.goto(f"{base}/#/manager/review")
        page.wait_for_selector(f"{PAGE['review_picker']} option:nth-child(2)", state="attached")
        with_applicant = page.locator(f"{PAGE['review_picker']} option", has_text="1 applicant").first
        page.select_option(PAGE["review_picker"], with_applicant.get_attribute("value"))
        page.wait_for_selector(PAGE["applicant"])
        page.locator(PAGE["applicant"]).first.click()
        page.wait_for_selector(PAGE["pdf_frame"])
        page.wait_for_timeout(1200)                                  # let the PDF render for the screenshot
        walk.check("the PDF opens inline beside the listing", page.locator(PAGE["pdf_frame"]).count() == 1)
        walk.shot("3_review")

        page.select_option(PAGE["status_select"], "Accepted")
        page.wait_for_function(f"document.querySelector('{PAGE['status_note']}').textContent.includes('Accepted')")
        walk.check("manager accepts the applicant", True)
        walk.sign_out()

        # ---- employee sees the decision ----
        walk.sign_in("employee", "employee@networker.test", "employee-demo")
        page.goto(f"{base}/#/employee/applications")
        page.wait_for_selector(PAGE["my_applications_status"])
        walk.check("employee sees Accepted",
                   page.locator(PAGE["my_applications_status"]).first.inner_text().strip() == "Accepted")

        walk.check("no JavaScript errors on any page", not errors)
        browser.close()
    return walk.checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--move", required=True)
    args = parser.parse_args()

    port = free_port()
    server = start_server(port)
    try:
        checks = run(args.move, f"http://127.0.0.1:{port}")
    finally:
        server.terminate()
        server.wait(timeout=10)

    failed = [name for name, passed in checks if not passed]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} UI checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
