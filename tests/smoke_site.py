"""Browser smoke test. Opens every screen of the built site and fails on anything a visitor would notice.

    python tests/smoke_site.py            (needs: pip install playwright && python -m playwright install chromium)

Set CHROME_PATH to use an installed Chrome instead of Playwright's own browser.
"""
import functools
import http.server
import json
import os
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parent.parent / "site"
SCREENS = [("#overview", "Overview"), ("#compare", "Compare"), ("#company/hermes", "Company"), ("#data", "Data and sources"), ("#method", "Method")]
WIDTHS = [(1440, 900), (390, 844)]
BAD_TEXT = ["undefined", "NaN", "[object Object]", "null"]


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    data = json.loads((SITE / "data.json").read_text())
    latest = next(iter(sorted(data["model"], reverse=True)))
    companies = data["companies"]
    figures = sum(1 + len((c.get("regions") or {}).get(latest) or {}) + len((c.get("segments") or {}).get(latest) or [])
                  for c in companies if latest in (c.get("series") or {}))
    server, failures, checks = serve(), [], 0
    base = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None, args=["--no-sandbox"])
        for width, height in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": height})
            problems = []
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))
            # Fonts come from Google. The test must pass without them, so they are answered locally.
            page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
            page.route("https://fonts.gstatic.com/**", lambda r: r.fulfill(status=200, body=""))
            for hash_, title in SCREENS:
                where = f"{title} at {width}px"
                page.goto(base + hash_)
                page.reload()
                page.wait_for_selector("#view .ex", timeout=10000)
                checks += 1
                if page.inner_text("#title").strip() != title:
                    failures.append(f"{where}: the heading reads {page.inner_text('#title')!r}.")
                text = page.inner_text("#view")
                for bad in BAD_TEXT:
                    if bad in text:
                        failures.append(f"{where}: the page shows the text {bad!r}.")
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if overflow > 1:
                    failures.append(f"{where}: the page scrolls sideways by {overflow}px.")
                if hash_ == "#overview":
                    for c in companies:
                        if c["name"] not in text:
                            failures.append(f"{where}: {c['name']} is missing.")
                if hash_ == "#data":
                    rows = page.locator("#view table").first.locator("tbody tr").count()
                    if rows != figures:
                        failures.append(f"{where}: the table lists {rows} figures and the dataset has {figures} for {latest}.")
                    page.locator("#view table").first.locator("tbody tr").first.click()
                    page.wait_for_selector("#drawer:not([hidden])", timeout=3000)
                    if "Source" not in page.inner_text("#drawer") and "source" not in page.inner_text("#drawer"):
                        failures.append(f"{where}: the figure drawer shows no source.")
                    page.keyboard.press("Escape")
                if hash_ == "#method" and "Data gate" not in text:
                    failures.append(f"{where}: the quality checks are missing.")
                for p in problems:
                    failures.append(f"{where}: browser error: {p[:200]}")
                problems.clear()
            page.close()
        browser.close()
    server.shutdown()
    for f in failures:
        print("FAIL", f)
    print(f"Site smoke test: {checks} screens opened, {len(failures)} problems.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
