"""End-to-end flow check inside the Streamlit runtime.

Run:  python tests/flow_check.py
Covers: resolve a RED, alias learning, approval, MDS export, vendor reply loop,
        TBE re-ranking.  Restores rules/aliases.yaml afterwards.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

ALIASES = ROOT / "rules" / "aliases.yaml"
TMPL = """import sys, shutil, json
from pathlib import Path
sys.path.insert(0, {root!r})
sys.path.insert(0, {tests!r})
import config, state as S
import json as _json

def main():
    out = {{}}
    S.init_state()
    S.load_sample_project()
    conn = S.get_conn()

    # 1) RED item -> engineer resolves with value + reason (logged)
    f2 = "PDS_V-102_L1.xlsx"
    assert any(i.key == "corrosion_allowance" for i in S.st.session_state["extractions"][f2].issues)
    S.resolve_issue(f2, "corrosion_allowance", "3 mm", "process sheet corrected")
    ext2 = S.st.session_state["extractions"][f2]
    out["ca_resolved"] = not any(i.key == "corrosion_allowance" and i.code == "MISSING"
                                 for i in ext2.issues)
    out["ca_mds"] = next((r.value for r in S.st.session_state["mds_rows"]
                          if r.key == "corrosion_allowance"), None)

    # 2) alias learning: 'Duty Pressure' -> operating_pressure
    f5 = "PDS_V-105_L2.xlsx"
    before = "operating_pressure" in S.st.session_state["extractions"][f5].fields
    S.teach_and_rerun("Duty Pressure", "operating_pressure", f5)
    ext5 = S.st.session_state["extractions"][f5]
    out["alias_before"] = before
    out["alias_after"] = "operating_pressure" in ext5.fields
    out["alias_value"] = getattr(ext5.fields.get("operating_pressure"), "value", None)

    # 3) approval on the clean sheet
    S.st.session_state["active"] = "PDS_V-101_L1.xlsx"
    S.rebuild_mds(); S.run_compare()
    out["approved"] = S.approve_mds()
    out["status"] = S.st.session_state["mds_status"]
    out["version"] = S.st.session_state["mds_version"]

    # 4) export MDS to Excel
    tmp = Path({tmp!r})
    rows = S.st.session_state["mds_rows"]
    path = S.export_with_audit(rows, tmp / "MDS_flowcheck.xlsx")
    out["export_exists"] = Path(path).exists()
    from openpyxl import load_workbook
    wb = load_workbook(path); ws = wb["MDS"]
    vals = {{str(r[1].value): r[2].value for r in ws.iter_rows(min_row=5)}}
    out["export_design_pressure"] = vals.get("Design pressure")
    out["export_comment"] = any(c.comment for r in ws.iter_rows(min_row=5) for c in r)

    # 5) vendor reply loop -> verdict + ranking change
    from engine.tbe import score
    out["rank_before"] = score(S.st.session_state["results"])["ranking"]
    import db
    db.save_reply(conn, "Vendor C", "R07", "Hydrotest at 15 bar(g)")
    db.save_reply(conn, "Vendor C", "R10", "EN 10204 3.1")
    S.run_compare()
    r07 = next(r for r in S.st.session_state["results"]
               if r.vendor == "Vendor C" and r.req_id == "R07")
    out["r07_after_reply"] = r07.verdict
    out["rank_after"] = score(S.st.session_state["results"])["ranking"]
    out["c_total_after"] = score(S.st.session_state["results"])["vendors"]["Vendor C"]["total"]
    db.clear_replies(conn)
    S.run_compare()

    # 6) audit chain still valid
    import db as _db
    out["chain"] = _db.verify_chain(conn)[1]
    globals()["FLOW"] = out
    Path({out_json!r}).write_text(json.dumps(out), encoding="utf-8")

main()
"""

EXPECT = {
    "ca_resolved": True,
    "alias_before": False,
    "alias_after": True,
    "approved": True,
    "status": "APPROVED",
    "version": 1,
    "export_exists": True,
    "export_design_pressure": 1.0,
    "export_comment": True,
    "r07_after_reply": "Compliant",
    "rank_before": ["Vendor A", "Vendor B", "Vendor C"],
    "rank_after": ["Vendor A", "Vendor B", "Vendor C"],
}


def main() -> int:
    backup = ALIASES.read_text(encoding="utf-8")
    tmp = Path(tempfile.gettempdir()) / "specora_flow"
    tmp.mkdir(parents=True, exist_ok=True)
    flow_json = tmp / "flow.json"
    if flow_json.exists():
        flow_json.unlink()
    script = Path(tempfile.gettempdir()) / "specora_flow_script.py"
    script.write_text(TMPL.format(root=str(ROOT), tests=str(ROOT / "tests"),
                                  tmp=str(tmp), out_json=str(flow_json)),
                      encoding="utf-8")
    try:
        at = AppTest.from_file(str(script), default_timeout=180)
        at.run()
        if at.exception:
            print("FAIL exception:", at.exception)
            return 1
        if not flow_json.exists():
            print("FAIL: flow produced no output")
            return 1
        data = json.loads(flow_json.read_text(encoding="utf-8"))
        fails = 0
        for k, v in EXPECT.items():
            got = data.get(k)
            ok = got == v
            fails += 0 if ok else 1
            print(("OK   " if ok else "FAIL "), k, "=", got, ("" if ok else f"(expected {v})"))
        print("chain:", data.get("chain"))
        print(f"\n{'ALL FLOWS PASS' if fails == 0 else str(fails) + ' failures'}")
        return 1 if fails else 0
    finally:
        ALIASES.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
