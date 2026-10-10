"""Review & Approve — side-by-side source vs extracted value (the visual hero)."""
from __future__ import annotations

import streamlit as st

import config
import state as S
import styles

CANON = ["tag_no", "fluid", "operating_pressure", "operating_temperature", "design_pressure",
         "design_temperature", "inside_diameter", "tan_to_tan_length", "corrosion_allowance",
         "radiography", "design_code", "h2s_ppm", "mdmt_c", "shell_material", "shell_thickness",
         "hydrotest_pressure", "pwht", "certificates", "inspection_witness", "painting",
         "delivery_documents"]


def render():
    if not st.session_state["extractions"]:
        st.info("Load the demo project (sidebar) first.")
        return
    names = list(st.session_state["extractions"])
    cur = st.session_state["active"]
    idx = names.index(cur) if cur in names else 0
    fname = st.selectbox("Process Data Sheet", names, index=idx, key="rev_pds")
    if fname != st.session_state["active"]:
        st.session_state["active"] = fname
        S.rebuild_mds()
        S.run_compare()
        st.rerun()

    ext = st.session_state["extractions"][fname]
    doc = st.session_state["docs"][fname]
    locked = st.session_state["mds_status"] == "APPROVED"

    left, right = st.columns([1.1, 1], gap="large")
    with right:
        _fields(ext, fname, locked)
    with left:
        _source(ext, doc, locked)

    st.divider()
    a, b = st.columns([1.3, 1], gap="large")
    with a:
        _reds(ext, fname, locked)
    with b:
        _alias(ext, fname, locked)
        _approve(ext, fname)


def _fields(ext, fname, locked):
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for f in ext.fields.values():
        counts[f.status] += 1
    st.markdown("#### Extracted values")
    g_lbl = f"🟢 {counts['GREEN']} auto-filled"
    a_lbl = f"🟡 {counts['AMBER']} review"
    r_lbl = f"🔴 {counts['RED']} blocked"
    st.markdown(styles.chip("GREEN", g_lbl) + " " + styles.chip("AMBER", a_lbl) + " "
                + styles.chip("RED", r_lbl), unsafe_allow_html=True)
    accepted = st.session_state["accepted"].setdefault(fname, set())
    focus = st.session_state.get("rev_focus", "")
    for key, f in sorted(ext.fields.items(), key=lambda kv: (kv[1].status != "RED",
                                                             kv[1].status != "AMBER", kv[0])):
        icon = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}[f.status]
        head = f"{icon} **{key}** — `{f.display}`" + (" ✅" if key in accepted else "")
        with st.expander(head, expanded=(f.status == "RED")):
            st.caption(
                f"source `{f.prov.source_file}` · **`{f.prov.locator}`** · "
                f"raw: \"{f.prov.raw_text}\"")
            st.caption(f"confidence **{f.confidence:.2f}** · method `{f.method}`"
                       + (f" · {' · '.join(f.notes)}" if f.notes else ""))
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("Accept", key=f"acc_{fname}_{key}", disabled=locked or
                         key in accepted, use_container_width=True):
                S.accept_field(fname, key)
                st.toast(f"Accepted {key}", icon="✅")
                st.rerun()
            if c2.button("Locate", key=f"loc_{fname}_{key}", use_container_width=True):
                st.session_state["rev_focus"] = key
                st.rerun()
            editing = st.session_state.get("edit_key") == key
            if c3.button("Edit…" if not editing else "Close", key=f"ed_{fname}_{key}",
                         disabled=locked, use_container_width=True):
                st.session_state["edit_key"] = None if editing else key
                st.rerun()
            if c4.button("Mark unknown", key=f"unk_{fname}_{key}", disabled=locked,
                         use_container_width=True):
                S.mark_unknown(fname, key)
                st.rerun()
            if editing:
                with st.form(key=f"form_{fname}_{key}"):
                    st.caption("Engineer edit — a reason is required and is audit-logged.")
                    new = st.text_input("New value (with unit)", value=str(f.value or ""),
                                        key=f"nv_{fname}_{key}")
                    why = st.text_input("Reason", key=f"nr_{fname}_{key}")
                    ok = st.form_submit_button("Save engineer edit", type="primary")
                    if ok and why.strip():
                        S.resolve_issue(fname, key, new, why.strip())
                        st.session_state["edit_key"] = None
                        st.rerun()


def _source(ext, doc, locked):
    st.markdown("#### Source document")
    fields = ext.fields
    focus = st.session_state.get("rev_focus", "")
    if focus not in fields:
        focus = next(iter(fields), "")
    f = fields.get(focus)
    st.caption(f"Highlighted: **{focus}** → `{f.prov.locator if f and f.prov else '—'}`")
    if doc.is_text:
        styles.render_source({}, highlight=(f.prov.locator if f and f.prov else None),
                             as_text=True, lines=doc.lines)
    else:
        sheet = f.prov.locator.split("!")[0] if f and f.prov else ""
        styles.render_source(doc.grid, highlight=(f.prov.locator if f and f.prov else None),
                             source_file=sheet)
    st.caption("Amber glow = the exact cell/line the value came from.")


def _reds(ext, fname, locked):
    reds = [i for i in ext.issues if i.severity == "RED"]
    st.markdown(f"#### 🔴 Clarify and block · {len(reds)}")
    if not reds:
        st.success("No open RED items on this sheet.")
        return
    for i in reds:
        with st.expander(f"**{i.key}** — {i.code}", expanded=True):
            st.markdown(f"<div class='sub'>{i.message}</div>", unsafe_allow_html=True)
            st.markdown(f"**❓ {i.question}**")
            with st.form(key=f"res_{fname}_{i.key}"):
                v = st.text_input("Resolved: enter value (with unit)",
                                  key=f"rv_{fname}_{i.key}", disabled=locked)
                why = st.text_input("Reason", key=f"rr_{fname}_{i.key}", disabled=locked)
                c1, c2 = st.columns(2)
                save = c1.form_submit_button("Resolve with value", type="primary",
                                             disabled=locked)
                ovr = c2.form_submit_button("Override (no value)", disabled=locked)
                if save and v.strip() and why.strip():
                    S.resolve_issue(fname, i.key, v.strip(), why.strip())
                    st.rerun()
                if ovr and why.strip():
                    S.override_red(fname, i.key, why.strip())
                    st.rerun()
            st.caption("Both paths are written to the tamper-evident audit log.")


def _alias(ext, fname, locked):
    st.markdown("#### 🧠 Alias learning")
    un = ext.unmapped
    if not un:
        st.caption("No unmapped labels on this sheet.")
        return
    labels = sorted({u["label"] for u in un})
    lab = st.selectbox("Unknown label", labels, key="alias_label")
    key = st.selectbox("Canonical field", CANON, key="alias_key")
    if st.button("Teach alias & re-run", type="primary", disabled=locked,
                 use_container_width=True):
        S.teach_and_rerun(lab, key, fname)
        st.rerun()
    st.caption("Persisted to `rules/aliases.yaml` — applies to every future sheet.")


def _approve(ext, fname):
    st.markdown("#### ✅ Approval gate")
    reds = [i for i in ext.issues if i.severity == "RED"]
    ov = st.session_state.get("overrides", {}).get(fname, {})
    open_reds = [i for i in reds if i.key not in ov]
    status = st.session_state["mds_status"]
    st_ch = styles.chip("GREEN" if status == "APPROVED" else "AMBER", status)
    st.markdown(f"Status: {st_ch} &nbsp; version **v{st.session_state['mds_version']}**",
                unsafe_allow_html=True)
    if reds:
        st.caption(f"Open 🔴: {len(open_reds)} · overridden: {len(reds) - len(open_reds)}")
    if status == "APPROVED":
        st.success(f"MDS v{st.session_state['mds_version']} approved — values locked.")
        if st.button("Re-open for editing (new version)", use_container_width=True):
            st.session_state["mds_status"] = "DRAFT"
            import db
            db.audit(S.get_conn(), "engineer", "reopen_mds",
                     {"file": fname, "version": st.session_state["mds_version"]})
            st.rerun()
        return
    if st.button("Approve MDS", type="primary", use_container_width=True):
        if S.approve_mds():
            st.rerun()
    if open_reds:
        st.warning(f"{len(open_reds)} RED item(s) must be resolved or overridden "
                   "with a written reason before approval.")
