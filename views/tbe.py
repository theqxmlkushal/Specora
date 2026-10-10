"""TBE & What-if: weights, ranking, radar, robustness, export."""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

import config
import db
import state as S
import styles
from engine import tbe as TBE

VC = {"Vendor A": "#2F80ED", "Vendor B": "#FFB020", "Vendor C": "#EB5757"}


def render():
    results = st.session_state.get("results") or []
    if not results:
        st.info("Run the extraction and build an MDS first.")
        return

    st.markdown("#### Technical Bid Evaluation")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("**Category weights** (drag to see the ranking respond live)")
        w = {}
        cols = st.columns(len(config.CATEGORY_WEIGHTS))
        for c, (cat, default) in zip(cols, config.CATEGORY_WEIGHTS.items()):
            with c:
                w[cat] = st.slider(cat, 0, 60, int(default), key=f"w_{cat}")
    with c2:
        whatif = st.toggle("What-if: assume open clarifications resolve favourably",
                           key="whatif")
    pts = {}
    with st.expander("Scoring points per class (configurable)"):
        pc = st.columns(len(config.POINTS))
        for c, (k, v) in zip(pc, config.POINTS.items()):
            with c:
                pts[k] = float(st.number_input(k, 0.0, 1.0, float(v), 0.1, key=f"p_{k}"))
    if sum(w.values()) == 0:
        st.warning("Total weight is 0 — give at least one category a weight.")
        return

    sc = TBE.what_if(results, pts, w) if whatif else TBE.score(results, pts, w)
    rob = TBE.robustness(results, None, w, trials=config.ROBUSTNESS_TRIALS,
                         perturb=config.ROBUSTNESS_PERTURB)

    _rank_bar(sc)
    _radar(sc)
    _robustness(sc, rob)

    st.divider()
    st.markdown("**Decision trail**")
    for v in sc["ranking"]:
        d = sc["vendors"][v]
        ok = d["acceptable"]
        st.markdown(
            f"<div class='glass'><b>{v}</b> {styles.chip('GREEN' if ok else 'RED', 'score ' + str(d['total']))} "
            + ("" if ok else styles.chip("RED", "Not technically acceptable pending clarification"))
            + f"<br><span class='sub'>blocking: {', '.join(d['blocking']) or '—'} · "
              f"open clarifications: {', '.join(d['open_clarifications']) or '—'}</span></div>",
            unsafe_allow_html=True)

    if st.button("⬇ Export TBE to Excel", type="primary"):
        out = config.DATA_DIR / "uploads" / "TBE_export.xlsx"
        out.parent.mkdir(parents=True, exist_ok=True)
        TBE.export_tbe(out, results, sc, rob,
                       TBE.what_if(results, None, w) if not whatif else None)
        db.audit(S.get_conn(), "engineer", "export_tbe",
                 {"ranking": sc["ranking"], "weights": w})
        with open(out, "rb") as fh:
            st.download_button("Download TBE", fh, file_name=out.name,
                               mime="application/vnd.openxmlformats-officedocument"
                                    ".spreadsheetml.sheet")
        st.toast("TBE exported with inputs, weights and decision trail", icon="⬇️")


def _rank_bar(sc):
    st.markdown("**Ranked bar**")
    vendors = sc["ranking"]
    totals = [sc["vendors"][v]["total"] for v in vendors]
    colors = [VC.get(v, "#2F80ED") for v in vendors]
    fig = go.Figure(go.Bar(x=vendors, y=totals, marker_color=colors,
                           text=[f"{t:.1f}" for t in totals], textposition="outside"))
    fig.update_layout(height=300, yaxis=dict(range=[0, 105], title="score /100"),
                      margin=dict(t=20, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", font_color="#E6EDF7")
    st.plotly_chart(fig, use_container_width=True)


def _radar(sc):
    st.markdown("**Category radar**")
    cats = [c for c in config.CATEGORY_WEIGHTS if any(
        c in sc["vendors"][v]["categories"] for v in sc["vendors"])]
    fig = go.Figure()
    for v in sc["ranking"]:
        d = sc["vendors"][v]["categories"]
        fig.add_trace(go.Scatterpolar(
            r=[d.get(c, {}).get("score", 0) for c in cats],
            theta=cats, fill="toself", name=v,
            line_color=VC.get(v, "#2F80ED")))
    fig.update_layout(height=340, polar=dict(radialaxis=dict(range=[0, 100]),
                                             bgcolor="rgba(0,0,0,0)"),
                      margin=dict(t=20, b=20, l=30, r=30),
                      paper_bgcolor="rgba(0,0,0,0)", font_color="#E6EDF7",
                      showlegend=True)
    st.plotly_chart(fig, use_container_width=True)


def _robustness(sc, rob):
    st.markdown(f"**Rank robustness** — weights perturbed ±{int(rob['perturb']*100)}% "
                f"× {rob['trials']} trials (numpy, seed {config.ROBUSTNESS_SEED})")
    top = rob["ranking_first"] if "ranking_first" in rob else sc["ranking"][0]
    best = max(rob["pct"].items(), key=lambda kv: kv[1])
    st.success(f"**{best[0]}** ranks first in **{best[1]}%** of scenarios.")
    fig = go.Figure(go.Bar(x=list(rob["pct"]), y=list(rob["pct"].values()),
                           marker_color=[VC.get(v, "#2F80ED") for v in rob["pct"]],
                           text=[f"{p}%" for p in rob["pct"].values()], textposition="outside"))
    fig.update_layout(height=230, yaxis=dict(range=[0, 110], title="% first place"),
                      margin=dict(t=10, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", font_color="#E6EDF7")
    st.plotly_chart(fig, use_container_width=True)
