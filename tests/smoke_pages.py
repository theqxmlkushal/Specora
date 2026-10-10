"""Headless smoke test: every page must render without an exception.

Run:  python tests/smoke_pages.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

PAGES = ["command_center", "inputs_extract", "review", "mds_draft",
         "vendor_compare", "tbe", "evidence"]

TMPL = """import sys
sys.path.insert(0, {root!r})
sys.path.insert(0, {tests!r})
from page_runner import run
run({page!r})
"""


def main() -> int:
    tmp = Path(tempfile.gettempdir()) / "specforge_smoke"
    tmp.mkdir(parents=True, exist_ok=True)
    fails = 0
    for page in PAGES:
        f = tmp / f"{page}.py"
        f.write_text(TMPL.format(root=str(ROOT), tests=str(ROOT / "tests"), page=page),
                     encoding="utf-8")
        try:
            at = AppTest.from_file(str(f), default_timeout=180)
            at.run()
            if at.exception:
                fails += 1
                print(f"FAIL {page}: {at.exception}")
            else:
                print(f"OK   {page}")
        except Exception as exc:
            fails += 1
            print(f"FAIL {page}: {type(exc).__name__}: {exc}")
    print(f"\n{len(PAGES) - fails}/{len(PAGES)} pages render")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
