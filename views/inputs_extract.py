"""Inputs (PDS / offers / template / rules) and the pre-processing pipeline."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import db
import state as S
import styles

MODULES = [
    ("Document parser", "tables → label/value candidates (3 layouts)"),
    ("Field extractor", "exact alias → normalised → fuzzy ≥88 🟢 / 70–88 🟡"),
    ("Unit normalizer", "psi · bara · bar(g) · °F · in → MPa(g) · degC · mm"),
    ("Provenance tagger", "source_file + locator on every value, none without"),
    ("Missing / conflict check", "MISSING · CONFLICT · RULE_VIOLATION · LOW_MATCH"),
]


def render():
    t1, t2 = st.tabs(["1 · Inputs", "2 · Extract & Validate"])
    with t1:
        _inputs()
    with t2:
        _pipeline()


# ------------------------------------------------------------------- inputs
def _inputs():
    st.markdown("#### User inputs")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Process Data Sheets**")
        up = st.file_uploader("PDS files", type=["xlsx", "csv", "txt", "pdf"],
                              accept_multiple_files=True, key="up_pds",
                              label_visibility="collapsed")
        if up:
            dest = config.DATA_DIR / "uploads"
            dest.mkdir(parents=True, exist_ok=True)
            paths = []
            for f in up:
                p = dest / Path(f.name).name
                p.write_bytes(f.getvalue())
                paths.append(p)
            if st.button("Ingest uploaded PDS", use_container_width=True):
                S.run_pipeline(paths, None, S.get_conn())
                db.audit(S.get_conn(), "engineer", "upload_pds",
                         {"files": [p.name for p in paths]})
                st.toast(f"Ingested {len(paths)} file(s)", icon="📄")
                st.rerun()

    with c2:
        st.markdown("**Vendor offers**")
        upv = st.file_uploader("Vendor offers", type=["xlsx", "csv"],
                               accept_multiple_files=True, key="up_vendor",
                               label_visibility="collapsed")
        if upv:
            dest = config.DATA_DIR / "uploads"
            dest.mkdir(parents=True, exist_ok=True)
            paths = []
            for f in upv:
                p = dest / Path(f.name).name
                p.write_bytes(f.getvalue())
                paths.append(p)
            if st.button("Ingest uploaded offers", use_container_width=True):
                S.run_pipeline([], paths, S.get_conn())
                db.audit(S.get_conn(), "engineer", "upload_vendor",
                         {"files": [p.name for p in paths]})
                st.toast(f"Ingested {len(paths)} offer(s)", icon="🧾")
                st.rerun()

    with c3:
        st.markdown("**MDS template & rules**")
        st.caption(f"Template: `{config.MDS_TEMPLATE.name}` "
                   f"({'found' if config.MDS_TEMPLATE.exists() else 'missing'})")
        if st.button("Use sample project", use_container_width=True, type="primary"):
            with st.spinner("Loading 8 PDS + 3 offers…"):
                S.load_sample_project()
            st.rerun()

    with st.expander("Rules (read-only) — `rules/*.yaml` · demo values CONFIRM WITH EXPERT"):
        tabs = st.tabs(["vessel_rules", "materials", "requirements", "aliases"])
        for tab, path in zip(tabs, [config.RULES_VESSEL, config.RULES_MATERIALS,
                                    config.RULES_REQUIREMENTS, config.RULES_ALIASES]):
            with tab:
                st.code(path.read_text(encoding="utf-8"), language="yaml")

    st.divider()
    _preview()


def _preview():
    docs = st.session_state["docs"]
    if not docs:
        st.caption("No documents loaded yet.")
        return
    st.markdown("**Preview**")
    name = st.selectbox("Source document", list(docs), label_visibility="collapsed")
    doc = docs[name]
    if doc.error:
        st.error(doc.error)
        return
    if doc.is_text:
        rows = [(loc, txt) for loc, txt in doc.lines if txt.strip()]
        html = ('<div style="max-height:340px;overflow:auto;border:1px solid rgba(255,255,255,.12);'
                'border-radius:10px;background:rgba(0,0,0,.25);padding:.4rem">'
                '<table style="width:100%;font-size:.82rem;font-family:ui-monospace,monospace">'
                + "".join(
                    f'<tr><td style="color:#5B7290;width:70px">{loc}</td>'
                    f'<td style="white-space:pre-wrap">{styles._esc(t)}</td></tr>'
                    for loc, t in rows)
                + "</table></div>")
        st.markdown(html, unsafe_allow_html=True)
        st.caption(f"{len(rows)} non-empty lines · layout {doc.layout}")
    else:
        st.dataframe(doc.preview_df().rename(columns=lambda c: f"col {c}"),
                     use_container_width=True, height=340)
        st.caption(f"layout {doc.layout} · {len(doc.cells)} non-empty cells, "
                   f"each with a `Sheet!Cell` locator")


# ---------------------------------------------------------------- pipeline
def _pipeline():
    st.markdown("#### Pre-processing modules")
    run = st.button("▶ Run extraction & validation", type="primary")
    if run:
        files = list(S.pds_files())
        updir = config.DATA_DIR / "uploads"
        if updir.exists():
            files += [p for p in updir.iterdir()
                      if p.suffix.lower() in (".xlsx", ".csv", ".txt", ".pdf")
                      and p.name not in {f.name for f in S.pds_files()}]
        S.run_pipeline(files,
                       S.vendor_files() if not st.session_state.get("vendor_names") else None,
                       S.get_conn())
        db.audit(S.get_conn(), "engineer", "run_extraction",
                 {"files": len(st.session_state["docs"])})
        st.rerun()

    if not st.session_state["extractions"]:
        st.info("Load the demo project (sidebar) and press **Run extraction & validation**.")
        return

    with st.status("Pre-processing pipeline", expanded=False) as status:
        for i, (name, sub) in enumerate(MODULES, start=1):
            st.write(f"**{i}. {name}** — {sub}")
            st.toast(f"{name} done", icon="⚙️")
        st.session_state["status_done"] = True
        status.update(label="Pipeline complete", state="complete")

    _donut_and_lanes()
    _provenance_table()
    _issues_panel()


def _donut_and_lanes():
    counts = S.lane_counts_all()
    left, right = st.columns([1, 1.4], gap="large")
    with left:
        fig = go.Figure(go.Pie(
            labels=["🟢 Auto-filled", "🟡 Review", "🔴 Block"],
            values=[counts["GREEN"], counts["AMBER"], counts["RED"]],
            hole=.62, marker=dict(colors=["#27AE60", "#FFB020", "#EB5757"]),
            textinfo="label+value",
            hovertemplate="%{label}: %{value}<extra></extra>"))
        fig.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10),
                          paper_bgcolor="rgba(0,0,0,0)", font_color="#E6EDF7",
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        s = S.st.session_state["gate_green"]
        st.caption(f"Gate: 🟢 needs confidence ≥ **{s:.2f}** and a clean source — "
                   "drag the sidebar slider to change the lanes live.")
        g, a, r = st.columns(3)
        g.markdown(f"<div class='lane g'><b>🟢 {counts['GREEN']}</b>"
                   f"<div class='sub'>auto-filled</div></div>", unsafe_allow_html=True)
        a.markdown(f"<div class='lane a'><b>🟡 {counts['AMBER']}</b>"
                   f"<div class='sub'>engineer review</div></div>", unsafe_allow_html=True)
        r.markdown(f"<div class='lane r'><b>🔴 {counts['RED']}</b>"
                   f"<div class='sub'>clarify & block</div></div>", unsafe_allow_html=True)


def _provenance_table():
    st.markdown("**Provenance table** — every value carries its source")
    rows = []
    for fname, ext in st.session_state["extractions"].items():
        for key, f in ext.fields.items():
            rows.append({
                "PDS": fname,
                "key": key,
                "value": f.display,
                "source locator": (f.prov.locator if f.prov else "— MISSING SOURCE —"),
                "raw text": (f.prov.raw_text[:48] if f.prov else ""),
                "confidence": round(f.confidence, 2),
                "method": f.method,
                "status": f.status,
            })
    df = pd.DataFrame(rows)
    df.index += 1
    styler = df.style.format({"confidence": "{:.2f}"})
    html = df.to_html(escape=True)
    for st_name, cls in (("GREEN", "GREEN"), ("AMBER", "AMBER"), ("RED", "RED")):
        html = html.replace(f">{st_name}<", f"><span class='chip {cls}'>{st_name}</span><")
    st.markdown(
        '<div style="max-height:380px;overflow:auto;border:1px solid rgba(255,255,255,.12);'
        'border-radius:12px;background:rgba(0,0,0,.22);padding:.3rem">' + html + "</div>",
        unsafe_allow_html=True)


def _issues_panel():
    st.markdown("**Issues panel** (grouped by code)")
    by_code: dict = {}
    for fname, ext in st.session_state["extractions"].items():
        for i in ext.issues:
            by_code.setdefault(i.code, []).append((fname, i))
    if not by_code:
        st.success("No issues raised on the current sample set.")
        return
    for code in ("MISSING", "CONFLICT", "UNIT_AMBIGUOUS", "RULE_VIOLATION", "LOW_MATCH"):
        items = by_code.get(code)
        if not items:
            continue
        with st.expander(f"{code} · {len(items)}", expanded=(code in ("MISSING", "CONFLICT"))):
            for fname, i in items:
                st.markdown(
                    f"<div class='glass' style='padding:.6rem .8rem'>"
                    f"{styles.chip(i.severity, i.severity)} <b>{i.key}</b> "
                    f"<span class='sub'>in {fname}</span><br>"
                    f"<span style='font-size:.86rem'>{i.message}</span>"
                    f"<br><span class='sub' style='font-size:.84rem'>"
                    f"❓ {i.question or '—'}</span></div>", unsafe_allow_html=True)
    un = [(f, u["label"], u.get("locator", "")) for f, ext in st.session_state["extractions"].items()
          for u in ext.unmapped]
    if un:
        with st.expander(f"Unmapped labels · {len(un)} (teach an alias in Review)"):
            st.dataframe(pd.DataFrame(un, columns=["PDS", "label", "locator"]).drop_duplicates(),
                         use_container_width=True, height=200)
