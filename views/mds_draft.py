"""MDS Draft: rows, formula traces, approval status, Excel export."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import config
import state as S
import styles


def render():
    rows = st.session_state.get("mds_rows")
    if not rows:
        st.info("No MDS yet — load the demo project and extract a PDS first.")
        return
    status = st.session_state["mds_status"]
    st.markdown(f"#### Mechanical Data Sheet — **{st.session_state['active']}**")
    st.markdown(f"{styles.chip('GREEN' if status == 'APPROVED' else 'AMBER', status)}"
                f" &nbsp; `v{st.session_state['mds_version']}` &nbsp; "
                f"equipment: unfired pressure vessel", unsafe_allow_html=True)
    st.caption("Prototype: not a certified design tool. Demo rule values — CONFIRM WITH EXPERT.")

    blocked = [r for r in rows if r.blocked_by]
    if blocked:
        st.warning(f"{len(blocked)} row(s) are **BLOCKED** — dependent values are never "
                   f"computed from a guess. First blocker: `{blocked[0].blocked_by}`.")

    c1, c2 = st.columns([3, 1])
    with c2:
        if st.button("⬇ Export MDS to Excel", type="primary", use_container_width=True,
                     disabled=status != "APPROVED"):
            out = config.TEMPLATE_DIR / f"MDS_{Path(st.session_state['active']).stem}_v{st.session_state['mds_version']}.xlsx"
            S.export_with_audit(rows, out)
            st.success(f"Written: `{out.name}`")
            with open(out, "rb") as fh:
                st.download_button("Download MDS Excel", fh, file_name=out.name,
                                   mime="application/vnd.openxmlformats-officedocument"
                                        ".spreadsheetml.sheet")
        if status != "APPROVED":
            st.caption("Approve in *Review & Approve* to enable export.")

    table = []
    for r in rows:
        table.append({
            "MDS item": r.label,
            "value": "—" if r.value is None else r.value,
            "unit": r.unit or "",
            "method": r.method,
            "source / rule": r.source,
            "status": r.blocked_by and f"BLOCKED ({r.blocked_by})" or r.status,
        })
    df = pd.DataFrame(table)
    html = df.to_html(escape=True, index=False)
    html = html.replace(">GREEN<", "><span class='chip GREEN'>🟢</span><")
    html = html.replace(">AMBER<", "><span class='chip AMBER'>🟡</span><")
    html = html.replace(">RED<", "><span class='chip RED'>🔴</span><")
    st.markdown(
        '<div style="border:1px solid rgba(255,255,255,.12);border-radius:12px;'
        'background:rgba(0,0,0,.22);padding:.4rem">' + html + "</div>",
        unsafe_allow_html=True)

    st.markdown("**How each value was derived** (deterministic code only)")
    for r in rows:
        if not r.trace:
            continue
        with st.expander(f"{r.label} → `{r.value if r.value is not None else 'BLOCKED'}`"):
            st.markdown(f"<div class='trace'>{styles._esc(r.trace)}</div>",
                        unsafe_allow_html=True)
            st.caption(f"source: {r.source or '—'} · method: {r.method}")

    if status != "APPROVED":
        st.info("Golden case check: on `PDS_V-101_L1.xlsx` the engine returns "
                "**P_design = 1.0 MPa(g)**, **t = 5.17 mm**, **selected = 10 mm**, "
                "**hydrotest = 1.3 MPa(g) = 13 bar(g)** — asserted in "
                "`tests/test_calculator.py`.")
