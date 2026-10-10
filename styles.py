"""CSS injection + small UI helpers (cards, chips, source viewer)."""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

CSS = """
<style>
.stApp{background:
  linear-gradient(rgba(47,128,237,.06) 1px,transparent 1px) 0 0/40px 40px,
  linear-gradient(90deg,rgba(47,128,237,.06) 1px,transparent 1px) 0 0/40px 40px,
  radial-gradient(1200px 600px at 10% -10%,#16315c 0%,#0A1628 60%);}
.glass{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:18px;
  padding:1.1rem 1.3rem;backdrop-filter:blur(12px);transition:.25s}
.glass:hover{transform:translateY(-3px);box-shadow:0 12px 40px rgba(47,128,237,.35)}
.hero{font-size:3rem;font-weight:800;background:linear-gradient(90deg,#2F80ED,#6FCF97,#FFB020);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1.1}
.sub{color:#9FB3D1;font-size:1.02rem}
.chip{display:inline-block;padding:.2rem .7rem;border-radius:999px;font-weight:700;font-size:.78rem;
  white-space:nowrap}
.chip.GREEN{background:#27AE6022;color:#6FCF97;border:1px solid #27AE60}
.chip.AMBER{background:#FFB02022;color:#FFB020;border:1px solid #FFB020}
.chip.RED{background:#EB575722;color:#FF6B6B;border:1px solid #EB5757;animation:pulse 1.6s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 #EB575788}100%{box-shadow:0 0 0 10px #EB575700}}
.kpi{background:linear-gradient(160deg,rgba(47,128,237,.16),rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:.9rem 1.1rem;text-align:center}
.kpi .n{font-size:2.1rem;font-weight:800;color:#E6EDF7}
.kpi .l{font-size:.78rem;color:#9FB3D1;letter-spacing:.06em;text-transform:uppercase}
.lane{border-radius:14px;padding:.7rem .9rem;border:1px solid rgba(255,255,255,.12);height:100%}
.lane.g{background:linear-gradient(160deg,#27AE6022,transparent)}
.lane.a{background:linear-gradient(160deg,#FFB02022,transparent)}
.lane.r{background:linear-gradient(160deg,#EB575722,transparent)}
.step{display:flex;align-items:center;gap:.55rem;padding:.6rem .8rem;border-radius:12px;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.10);font-size:.85rem;
  position:relative;overflow:hidden}
.step .dot{width:10px;height:10px;border-radius:50%;background:#2F80ED;box-shadow:0 0 10px #2F80ED;
  animation:blink 1.4s infinite}
@keyframes blink{0%,100%{opacity:.35}50%{opacity:1}}
.hl{background:#FFB02033;border:1px solid #FFB020;border-radius:6px;
  box-shadow:0 0 14px #FFB02088;padding:0 .15rem}
td.hl{box-shadow:inset 0 0 0 2px #FFB020, 0 0 16px #FFB02066}
.trace{font-family:ui-monospace,Consolas,monospace;font-size:.82rem;color:#8FD3FF;
  background:rgba(0,0,0,.28);border-left:3px solid #2F80ED;padding:.55rem .7rem;border-radius:6px}
.blocked{color:#FF6B6B;font-weight:700}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0C1A30,#0A1628)}
#MainMenu,footer{visibility:hidden}
div[role="alert"]{display:none}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(status: str, text: str = "") -> str:
    label = text or {"GREEN": "🟢 Auto-filled", "AMBER": "🟡 Review", "RED": "🔴 Block"}[status]
    return f'<span class="chip {status}">{label}</span>'


def st_chip(status: str, text: str = "") -> None:
    st.markdown(chip(status, text), unsafe_allow_html=True)


def kpi(n, label: str, key: str = "") -> None:
    st.markdown(
        f'<div class="kpi"><div class="n">{n}</div><div class="l">{label}</div></div>',
        unsafe_allow_html=True,
    )


def card(title: str, body: str = "", cls: str = "glass") -> None:
    inner = f"<div class='sub'>{body}</div>" if body else ""
    st.markdown(f'<div class="{cls}"><b>{title}</b>{inner}</div>', unsafe_allow_html=True)


def footer(text: str) -> None:
    st.markdown(f"<div class='sub' style='text-align:center;margin-top:1.4rem'>{text}</div>",
                unsafe_allow_html=True)


def status_counts(fields: List) -> Dict[str, int]:
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for f in fields:
        counts[getattr(f, "status", "RED")] += 1
    return counts


# --------------------------------------------------------------- source viewer
def render_source(
    grid: Dict[str, List[List[str]]],
    highlight: Optional[str] = None,
    source_file: str = "",
    as_text: bool = False,
    text_lines: Optional[List[str]] = None,
) -> None:
    """Render a source document as HTML with the matched cell/line highlighted."""
    if as_text:
        lines = text_lines or []
        rows = []
        for i, item in enumerate(lines, start=1):
            if isinstance(item, (tuple, list)):
                loc, txt = item[0], (item[1] if len(item) > 1 else "")
            else:
                loc, txt = f"txt:line{i}", item
            if not str(txt).strip():
                continue
            cls = "hl" if highlight and highlight == loc else ""
            rows.append(
                f'<tr><td style="color:#5B7290;width:3rem;user-select:none">{i}</td>'
                f'<td class="{cls}" style="font-family:ui-monospace,monospace;white-space:pre-wrap">'
                f"{_esc(txt)}</td></tr>"
            )
        html = (
            '<div style="max-height:460px;overflow:auto;border:1px solid rgba(255,255,255,.12);'
            'border-radius:12px;padding:.4rem;background:rgba(0,0,0,.25)">'
            '<table style="width:100%;border-collapse:collapse;font-size:.83rem">'
            + "".join(rows) + "</table></div>"
        )
        st.markdown(html, unsafe_allow_html=True)
        return

    sheet = source_file if source_file in grid else (next(iter(grid), ""))
    if not sheet:
        st.info("No source grid to render.")
        return
    rows_html = []
    for r, row in enumerate(grid[sheet], start=1):
        tds = []
        for c, val in enumerate(row, start=1):
            col = _col_letter(c)
            loc = f"{sheet}!{col}{r}"
            cls = "hl" if highlight and highlight == loc else ""
            tds.append(f'<td class="{cls}">{_esc(str(val))}</td>')
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    html = (
        f'<div style="max-height:460px;overflow:auto;border:1px solid rgba(255,255,255,.12);'
        f'border-radius:12px;padding:.4rem;background:rgba(0,0,0,.25)">'
        f'<div class="sub" style="padding:.2rem .4rem">{_esc(sheet)}</div>'
        f'<table style="width:100%;border-collapse:collapse;font-size:.83rem">{"".join(rows_html)}</table>'
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _col_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _esc(txt: str) -> str:
    return (
        str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def df_html(df: "pd.DataFrame") -> str:
    return df.to_html(index=False, escape=True)
