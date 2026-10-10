"""Command Center: hero, animated pipeline strip, live KPIs, outcome lanes."""
from __future__ import annotations

import streamlit as st

import config
import state as S
import styles

STEPS = [
    ("1 · Inputs", "PDS · offers · rules"),
    ("2 · Parse & extract", "aliases + fuzzy"),
    ("3 · Normalise", "bar/psi/bara → MPa(g)"),
    ("4 · Provenance", "source locator on all"),
    ("5 · Gate", "🟢 🟡 🔴 lanes"),
    ("6 · MDS & TBE", "approve → compare"),
]


def render() -> None:
    st.markdown("<div class='hero'>Specora</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sub'>{config.APP_TAGLINE}</div>", unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([2.1, 1], gap="large")
    with left:
        st.markdown("#### Pipeline")
        cols = st.columns(len(STEPS))
        for c, (title, sub) in zip(cols, STEPS):
            with c:
                st.markdown(
                    f"<div class='step'><span class='dot'></span><div><b>{title}</b><br>"
                    f"<span class='sub' style='font-size:.72rem'>{sub}</span></div></div>",
                    unsafe_allow_html=True)
        st.write("")
        st.markdown(
            """
<div class="lane g"><b>🟢 Auto-fill / Compliant</b><div class="sub">Extracted with a source
pointer and high confidence — tick to accept.</div></div>
""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<div class='lane a'><b>🟡 Engineer review</b><div class='sub'>"
                        "Converted units, fuzzy match, derived with assumption.</div></div>",
                        unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='lane r'><b>🔴 Clarify and block</b><div class='sub'>"
                        "Missing or conflicting — question generated, MDS blocked.</div></div>",
                        unsafe_allow_html=True)

    with right:
        st.markdown("#### Project KPIs")
        docs = len(S.st.session_state["docs"]) + len(S.st.session_state["vendor_names"])
        fields = sum(len(e.fields) for e in S.st.session_state["extractions"].values())
        lanes = S.lane_counts_all()
        results = S.st.session_state.get("results", [])
        compared = len({r.vendor for r in results})
        k1, k2 = st.columns(2)
        with k1:
            styles.kpi(docs, "Documents loaded")
            styles.kpi(lanes["GREEN"], "🟢 Auto-filled")
        with k2:
            styles.kpi(fields, "Fields extracted")
            styles.kpi(lanes["AMBER"], "🟡 Review")
        k3, k4 = st.columns(2)
        with k3:
            styles.kpi(lanes["RED"], "🔴 Block")
            styles.kpi(compared, "Vendors compared")
        with k4:
            styles.kpi(f"v{S.st.session_state['mds_version']}",
                       f"MDS {S.st.session_state['mds_status']}")
            styles.kpi(len(results), "Checks run")

    st.write("")
    st.markdown("#### Evidence in one line")
    n_issues = sum(len(e.issues) for e in S.st.session_state["extractions"].values())
    ungrounded = sum(1 for e in S.st.session_state["extractions"].values()
                     for f in e.fields.values() if f.prov is None)
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Issues raised", n_issues, help="MISSING / CONFLICT / UNIT_AMBIGUOUS / "
                                              "RULE_VIOLATION / LOW_MATCH")
    g2.metric("Ungrounded values", ungrounded, help="Fields without a source pointer — must be 0")
    g3.metric("MDS rows blocked",
              sum(1 for r in (S.st.session_state.get("mds_rows") or []) if r.blocked_by),
              help="Rows that refused to compute from a guess")
    g4.metric("Audit entries",
              len(__import__("db").audit_rows(conn := S.get_conn(), 1000)),
              help="Hash-chained, tamper-evident")

    if not S.st.session_state["extractions"]:
        st.info("Load the demo project from the sidebar to light up the pipeline.")
    else:
        st.caption(f"Active PDS: **{S.st.session_state['active']}** — "
                   "continue in *Inputs & Extraction*.")
