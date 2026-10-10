"""Helper executed inside the AppTest runtime (one file per page)."""
from __future__ import annotations


def run(page: str) -> None:
    import streamlit as st
    import state as S

    S.init_state()
    if not st.session_state["extractions"]:
        S.load_sample_project()
    if page == "review":
        st.session_state["active"] = "PDS_V-102_L1.xlsx"
        S.rebuild_mds()
        S.run_compare()
    if page in ("mds_draft", "vendor_compare", "tbe"):
        st.session_state["active"] = "PDS_V-101_L1.xlsx"
        S.rebuild_mds()
        S.run_compare()
    mod = __import__(f"views.{page}", fromlist=[page])
    mod.render()
