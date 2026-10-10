"""Specora — shell: theme, navigation, routing."""
from __future__ import annotations

import streamlit as st
from streamlit_option_menu import option_menu

import config
import state as S
import styles

PAGES = [
    ("Command Center", "command_center", "house-gauge-fill"),
    ("Inputs & Extraction", "inputs_extract", "upload"),
    ("Review & Approve", "review", "check2-square"),
    ("MDS Draft", "mds_draft", "file-earmark-ruled"),
    ("Vendor Compare", "vendor_compare", "columns-gap"),
    ("TBE & What-if", "tbe", "trophy"),
    ("Evidence", "evidence", "shield-check"),
]

st.set_page_config(page_title="Specora — PDS → MDS → TBE", page_icon="🏭",
                   layout="wide", initial_sidebar_state="expanded")
styles.inject_css()
S.init_state()
conn = S.get_conn()


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 🏭 **Specora**")
    st.markdown("<div class='sub'>Process Data Sheet → MDS → TBE</div>",
                unsafe_allow_html=True)
    st.divider()
    choice = option_menu("", [p[0] for p in PAGES], icons=[p[2] for p in PAGES],
                         default_index=0, menu_icon="grid-1x2-fill",
                         styles={"container": {"padding": "0!important", "background": "transparent"},
                                 "icon": {"color": "#2F80ED", "font-size": "15px"},
                                 "nav-link": {"font-size": "14px", "text-align": "left",
                                              "margin": "0px", "--hover-color": "#16315c"},
                                 "nav-link-selected": {"background": "linear-gradient(90deg,#2F80ED,#1B5FBF)",
                                                       "font-weight": "700"}})
    st.divider()
    if st.button("⚡ Load demo project", use_container_width=True, type="primary"):
        with st.spinner("Loading synthetic PDS + vendor offers…"):
            S.load_sample_project()
        st.rerun()
    st.caption(f"PDS loaded: {len(S.st.session_state['extractions'])} · "
               f"Vendors: {len(S.st.session_state['vendor_names'])}")

    st.divider()
    st.markdown("**Gate thresholds**")
    st.session_state["gate_green"] = st.slider(
        "🟢 confidence ≥ ", 0.50, 0.99,
        float(S.st.session_state.get("gate_green", config.GATE_THRESHOLDS["green"])),
        0.01, help="Confidence needed for the GREEN (auto-filled) lane.")

    st.divider()
    llm = st.toggle("LLM assistance (optional)", value=bool(S.st.session_state.get("llm_on")),
                    help="Only for extracting messy text and wording questions. "
                         "Never calculates, never picks values.")
    if llm != S.st.session_state.get("llm_on"):
        S.st.session_state["llm_on"] = llm
        st.rerun()
    if llm:
        st.warning("⚠️ LLM is ON. Use synthetic / mentor-approved documents only. "
                   "Every proposal is grounding-checked against the source span; "
                   "ungrounded values are rejected and logged.")
        if not config.LLM_HAS_KEY:
            st.caption("No ANTHROPIC_API_KEY found → deterministic fallback is active.")

    st.divider()
    st.caption(config.PROTOTYPE_FOOTER)


# ------------------------------------------------------------------- routing
S.regate_all()
view = next((p[1] for p in PAGES if p[0] == choice), "command_center")
mod = __import__(f"views.{view}", fromlist=[view])
mod.render()
styles.footer(config.PROTOTYPE_FOOTER)
