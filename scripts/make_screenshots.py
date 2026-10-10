"""Capture the 9 submission screenshots with Playwright (local, no upload).

Prereq:  pip install playwright && python -m playwright install chromium
Run:     python scripts/make_screenshots.py            (app must be running on :8511)
Output:  docs/screenshots/01..09_*.png
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8511"

SHOTS = [
    ("01_command_center", "Command Center", None),
    ("02_extraction_traps", "Inputs & Extraction", "2 · Extract & Validate"),
    ("03_review_highlight", "Review & Approve", None),
    ("04_mds_formula_trace", "MDS Draft", None),
    ("05_vendor_heatmap", "Vendor Compare", "1 · Matrix"),
    ("06_deviation_register", "Vendor Compare", "2 · Deviation register"),
    ("07_clarifications", "Vendor Compare", "3 · Clarifications"),
    ("08_tbe_sliders", "TBE & What-if", None),
    ("09_evidence", "Evidence", "1 · Evaluation"),
]


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000},
                                device_scale_factor=1)

        def running() -> bool:
            try:
                return "Stop" in page.inner_text('[data-testid="stHeader"]')
            except Exception:
                return False

        def wait_idle(timeout: int = 90) -> None:
            """Streamlit fades the app out while a rerun is in flight."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not running():
                    time.sleep(1.5)
                    if not running():
                        return
                time.sleep(0.5)

        def click_nav(label: str) -> bool:
            """option_menu lives inside a component iframe — click it there."""
            for sel in (lambda: page.frame_locator("iframe").locator(f"text={label}"),
                        lambda: page.get_by_text(label, exact=True)):
                try:
                    el = sel()
                    if el.count():
                        el.first.click()
                        return True
                except Exception:
                    continue
            return False

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector("text=Load demo project", timeout=60000)
        wait_idle()

        # load the demo project (retry until the sidebar confirms 8 PDS)
        for attempt in range(3):
            try:
                page.get_by_text("Load demo project").first.click()
            except Exception:
                pass
            try:
                page.wait_for_selector("text=PDS loaded: 8", timeout=45000)
                print("demo project loaded (8 PDS)")
                break
            except Exception:
                print("retry load, attempt", attempt + 1)
                time.sleep(2)
        wait_idle()
        time.sleep(2)

        for name, nav, tab in SHOTS:
            if click_nav(nav):
                wait_idle()
                time.sleep(1)
            else:
                print("WARN nav not found:", nav)
            if tab:
                t = page.get_by_role("tab", name=tab)
                if t.count():
                    t.first.click()
                    wait_idle()
                    time.sleep(1)
                else:
                    print("WARN tab not found:", tab)
            if name == "03_review_highlight":
                # hero shot: the sheet with the seeded conflict + missing field
                try:
                    combo = page.get_by_role("combobox").first
                    combo.click()
                    time.sleep(1)
                    page.get_by_role("option", name="PDS_V-102_L1.xlsx").first.click()
                    wait_idle()
                    time.sleep(2)
                    page.screenshot(path=str(OUT / f"{name}.png"))
                    print("saved", OUT / f"{name}.png", "| (PDS_V-102_L1: conflict + missing CA)")
                    # switch back so the MDS/TBE shots keep the clean golden sheet
                    combo = page.get_by_role("combobox").first
                    combo.click()
                    time.sleep(1)
                    page.get_by_role("option", name="PDS_V-101_L1.xlsx").first.click()
                    wait_idle()
                    time.sleep(2)
                    continue
                except Exception as exc:
                    print("WARN could not switch PDS:", exc)
            wait_idle()
            page.screenshot(path=str(OUT / f"{name}.png"))
            body = page.inner_text('[data-testid="stAppViewContainer"]')
            tail = " / ".join(body.splitlines()[-6:])[:90]
            print("saved", OUT / f"{name}.png", "|", tail)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
