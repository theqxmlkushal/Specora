"""Evidence: live evaluation, audit chain, time study, architecture, real feedback."""
from __future__ import annotations

import json
import time

import pandas as pd
import streamlit as st

import config
import db
import state as S
import styles
from engine.evaluate import evaluate, load_gt


def render():
    t = st.tabs(["1 · Evaluation", "2 · Audit trail", "3 · Time study",
                 "4 · Architecture", "5 · Feedback"])
    with t[0]:
        _evaluation()
    with t[1]:
        _audit()
    with t[2]:
        _time_study()
    with t[3]:
        _architecture()
    with t[4]:
        _feedback()


# --------------------------------------------------------------- evaluation
def _evaluation():
    st.markdown("#### Evaluation panel (computed live vs `data/ground_truth.json`)")
    if not st.session_state["extractions"]:
        st.info("Load the demo project to compute metrics.")
        return
    conn = S.get_conn()
    ev = evaluate(st.session_state["extractions"],
                  st.session_state.get("results", []), load_gt(),
                  db.get_time_study(conn),
                  baseline=st.session_state.get("baseline"))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Field extraction accuracy", f"{ev['field_accuracy']*100:.1f}%",
              f"{ev['field_n']} canonical fields")
    k2.metric("Unit normalisation accuracy", f"{ev['unit_accuracy']*100:.1f}%",
              "traps T1 · T2 · T6 · T7")
    k3.metric("Trap detection recall / precision",
              f"{ev['trap_recall']*100:.0f}% / {ev['trap_precision']*100:.0f}%",
              f"false flags: {ev['false_flags']}")
    k4.metric("Ungrounded values", ev["ungrounded"],
              help="Fields without a source pointer — must be 0")

    st.markdown("**Trap-by-trap status**")
    gt = load_gt()
    rows = []
    for tid, t in gt["traps"].items():
        if t["kind"] == "issue":
            ok = tid in ev["traps_found"]
            detail = f"expect {t['expect_code']} ({t['expect_severity']})"
        elif t["kind"] == "unit_conversion":
            ok = tid not in ev["unit_bad"]
            detail = f"expect {t['expect_value']} {t['expect_unit']}"
        else:
            ok = _check_material(t)
            detail = f"expect material {t['expect_material']}, PWHT {t['expect_pwht']}"
        rows.append({"trap": tid, "file": t["file"], "key": t["key"],
                     "expected behaviour": detail, "result": "✅" if ok else "❌",
                     "detail": t["detail"]})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=260)
    if ev["field_misses"]:
        with st.expander(f"Field misses · {len(ev['field_misses'])}"):
            st.code("\n".join(ev["field_misses"]))

    st.markdown("**Compliance classification** (vendor offers)")
    cm = pd.DataFrame(ev["matrix"], index=["true: " + c for c in
                                           ["Compliant", "Deviating", "Unclear", "Missing"]],
                      columns=["pred: " + c for c in ["Compliant", "Deviating", "Unclear",
                                                      "Missing"]])
    pc = pd.DataFrame(ev["compliance"]).T
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(pc, use_container_width=True)
        st.caption(f"n = {ev['compliance_n']} vendor×requirement verdicts")
    with c2:
        st.dataframe(cm, use_container_width=True)
    if ev["time"]:
        st.metric("Time saved", f"{ev['time']['reduction_pct']}%",
                  f"manual {ev['time']['manual']} min → tool {ev['time']['tool']} min")
    else:
        st.caption("Time saved appears after a real measurement is entered in *Time study*.")


def _check_material(t) -> bool:
    from engine import calculator as calc
    import yaml
    mats = yaml.safe_load(config.RULES_MATERIALS.read_text(encoding="utf-8"))
    rules = yaml.safe_load(config.RULES_VESSEL.read_text(encoding="utf-8"))
    ext = st.session_state["extractions"].get(t["file"])
    if not ext:
        return False
    fluid = ext.fields.get("fluid")
    h2s = ext.fields.get("h2s_ppm")
    mdmt = ext.fields.get("mdmt_c")
    grade, _, _ = calc.select_material(
        str(fluid.value) if fluid and fluid.value else "",
        h2s.value if h2s and h2s.value else None,
        mdmt.value if mdmt and mdmt.value else None, mats)
    pwht = calc.pwht_required(None, calc.is_sour(h2s.value if h2s else None), rules)
    return grade == t["expect_material"] and bool(pwht) == bool(t["expect_pwht"])


# -------------------------------------------------------------------- audit
def _audit():
    st.markdown("#### Audit trail (hash-chained, tamper-evident)")
    conn = S.get_conn()
    ok, msg = db.verify_chain(conn)
    if ok:
        st.success(msg)
    else:
        st.error(msg)
    rows = db.audit_rows(conn, 15)
    if not rows:
        st.caption("No audit entries yet — load the demo project.")
        return
    df = pd.DataFrame([{
        "id": r["id"], "time": time.strftime("%H:%M:%S", time.localtime(r["t"])),
        "actor": r["actor"], "action": r["action"],
        "payload": json.dumps(r["payload"], ensure_ascii=False)[:90],
        "hash": r["hash"][:16] + "…",
    } for r in rows])
    st.dataframe(df, use_container_width=True, height=250)

    c1, c2 = st.columns(2)
    if c1.button("🧪 Tamper demo: alter one row"):
        st.session_state["tamper_msg"] = _tamper(conn)
        db.audit(conn, "demo", "tamper_demo", {"target": "first audit row"})
        st.rerun()
    if c2.button("Verify chain again"):
        st.session_state["tamper_msg"] = db.verify_chain(conn)[1]
    if st.session_state.get("tamper_msg"):
        st.code(st.session_state["tamper_msg"])


def _tamper(conn) -> str:
    row = conn.execute("SELECT id, body FROM audit ORDER BY id ASC LIMIT 1").fetchone()
    if not row:
        return "Nothing to tamper with yet."
    orig = row["body"]
    payload = json.loads(orig)
    payload["payload"] = dict(payload.get("payload") or {}, tampered=True)
    conn.execute("UPDATE audit SET body=? WHERE id=?",
                 (json.dumps(payload, sort_keys=True), row["id"]))
    conn.commit()
    _, fail = db.verify_chain(conn)
    conn.execute("UPDATE audit SET body=? WHERE id=?", (orig, row["id"]))
    conn.commit()
    _, back = db.verify_chain(conn)
    return (f"TAMPERED -> {fail}\n"
            f"row restored -> {back}\n"
            "(the demo alters row 1 in memory, shows the failure, then restores it)")


# -------------------------------------------------------------- time study
def _time_study():
    st.markdown("#### Time study")
    st.caption("Enter **real measurements only** — a teammate does one PDS→MDS by hand, "
               "you do the same one with Specora.")
    conn = S.get_conn()
    with st.form("ts"):
        c1, c2, c3 = st.columns(3)
        who = c1.text_input("Who measured", value="")
        man = c2.number_input("Manual PDS → MDS (minutes)", 0.0, 2000.0, 0.0, 1.0)
        tool = c3.number_input("With Specora (minutes)", 0.0, 2000.0, 0.0, 1.0)
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save measurement", type="primary") and man > 0:
            db.add_time_study(conn, who or "tester", man, tool, note)
            db.audit(conn, who or "tester", "time_study",
                     {"manual": man, "tool": tool})
            st.toast("Measurement saved", icon="⏱️")
            st.rerun()
    rows = db.get_time_study(conn)
    if rows:
        df = pd.DataFrame(rows)
        df["reduction_%"] = ((df.manual_min - df.tool_min) / df.manual_min * 100).round(1)
        st.dataframe(df[["actor", "manual_min", "tool_min", "reduction_%", "note"]],
                     use_container_width=True)
        avg = df["reduction_%"].mean()
        st.metric("Average time reduction", f"{avg:.1f}%")
    else:
        st.info("No measurements yet.")


# -------------------------------------------------------------- architecture
def _architecture():
    st.markdown("#### Architecture — left to right lanes")
    lanes = [
        ("User inputs", ["PDS (Excel/PDF/text)", "Vendor offers", "Reference pack"],
         "#2F80ED"),
        ("Pre-processing", ["Document parser", "Field extractor", "Unit normalizer",
                            "Provenance tagger", "Conflict / missing check"], "#5B8FF9"),
        ("Unified engine", ["Rules (YAML)", "Deterministic calculator",
                            "Requirement comparator"], "#6FCF97"),
        ("Decision gate", ["Confidence & compliance gate", "🟢 🟡 🔴"], "#FFB020"),
        ("Outcomes", ["🟢 Auto-fill", "🟡 Review", "🔴 Clarify & block"], "#EB5757"),
        ("Closed loop", ["Approval", "Vendor replies", "TBE re-score", "Alias & rule learning"],
         "#9B51E0"),
    ]
    cols = st.columns(len(lanes))
    for c, (title, items, color) in zip(cols, lanes):
        with c:
            body = "".join(
                f"<div style='background:rgba(255,255,255,.06);border-radius:8px;"
                f"padding:.3rem .45rem;margin:.25rem 0;font-size:.74rem;border-left:3px solid "
                f"{color}'>{i}</div>" for i in items)
            st.markdown(
                f"<div style='border:1px solid rgba(255,255,255,.14);border-radius:12px;"
                f"padding:.5rem;background:rgba(255,255,255,.03)'>"
                f"<div style='font-weight:800;font-size:.82rem;color:{color}'>{title}</div>"
                f"{body}</div>", unsafe_allow_html=True)
    st.caption("Same lane layout as the problem-statement reference image; every block is "
               "Specora's own content. Full description: `SPECORA_ARCHITECTURE.md`.")
    if config.ROOT.joinpath("SPECORA_ARCHITECTURE.md").exists():
        with st.expander("SPECORA_ARCHITECTURE.md"):
            st.code(config.ROOT.joinpath("SPECORA_ARCHITECTURE.md").read_text(encoding="utf-8"),
                    language="markdown")


# ----------------------------------------------------------------- feedback
def _feedback():
    st.markdown("#### Feedback from real testers")
    st.caption("Ask **5 mentors or teammates** to try the demo, then screenshot this section "
               "for the submission. No fabricated testimonials.")
    conn = S.get_conn()
    with st.form("fb"):
        res = st.feedback("stars")
        c1, c2 = st.columns(2)
        role = c1.selectbox("Role", ["Process engineer", "Mechanical engineer",
                                     "Procurement", "Mentor", "Judge", "Other"])
        comment = c2.text_input("Comment")
        if st.form_submit_button("Send feedback", type="primary"):
            stars = int(res.get("score", 0)) + 1 if isinstance(res, dict) else 0
            db.add_feedback(conn, stars, role, comment)
            db.audit(conn, role, "feedback", {"stars": stars, "comment": comment[:60]})
            st.toast("Thanks — stored in SQLite", icon="⭐")
            st.rerun()

    rows = db.get_feedback(conn)
    if not rows:
        st.info("No feedback yet — be the first.")
        return
    avg = sum(r["stars"] for r in rows) / len(rows)
    st.markdown(f"**{avg:.2f} / 5** from {len(rows)} testers")
    cols = st.columns(3)
    for i, r in enumerate(rows):
        with cols[i % 3]:
            st.markdown(
                f"<div class='glass'><b>{'⭐' * int(r['stars'])}</b>"
                f"<span class='sub'> · {r['role']}</span>"
                f"<div style='font-size:.88rem;margin-top:.3rem'>{styles._esc(r['comment'] or '—')}</div>"
                f"</div>", unsafe_allow_html=True)
