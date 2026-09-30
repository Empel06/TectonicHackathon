"""Streamlit UI. Run: streamlit run ui/app.py

Only talks to app.service (the contract). Person B owns this file.
"""
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import service, store  # noqa: E402

HERO_QUESTION = "Do our part-time employees get a pro-rata end-of-year bonus (13th month) in December?"
SIGNAL_LABEL = {"freshness": "Freshness", "ownership": "Ownership", "authority": "Authority",
                "applicability": "Applicability", "consistency": "Consistency", "validation": "Validation"}
STATUS_LABEL = {"pass": "Pass", "warn": "Warning", "fail": "Fail", "unknown": "Insufficient data"}
REPORT_REASONS = ["wrong_context", "outdated", "contradicts_other_source", "incorrect", "incomplete", "unclear"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --ink:#111827; --muted:#6B7280; --line:#E5E7EB; --card:#FFFFFF; --accent:#1E3A8A;
  --pass:#15803D; --pass-bg:#ECFDF3; --warn:#B45309; --warn-bg:#FFFBEB;
  --fail:#B91C1C; --fail-bg:#FEF2F2; --unknown:#6B7280; --unknown-bg:#F3F4F6;
}
html, body, .stApp, .stMarkdown, button, input, textarea { font-family: 'Inter', system-ui, sans-serif; }
#MainMenu, footer, [data-testid="stDecoration"] { display: none; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; max-width: 1280px; }

.tc-header { display:flex; justify-content:space-between; align-items:flex-end; gap:16px;
  border-bottom:1px solid var(--line); padding-bottom:16px; margin-bottom:8px; flex-wrap:wrap; }
.tc-eyebrow { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:600; }
.tc-title { font-size:28px; font-weight:700; color:var(--ink); margin:2px 0 0; line-height:1.2; }
.tc-context { font-size:13px; color:var(--muted); background:var(--card); border:1px solid var(--line);
  border-radius:8px; padding:8px 12px; }
.tc-context b { color:var(--ink); }

.tc-card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px 22px; }
.tc-card-label { font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted);
  font-weight:600; margin-bottom:12px; }
.tc-answer { font-size:15px; line-height:1.6; color:var(--ink); }
.tc-source-line { font-size:13px; color:var(--muted); margin-top:14px; padding-top:12px; border-top:1px solid var(--line); }
.tc-note { font-size:12px; color:var(--muted); margin-top:6px; font-style:italic; }

.tc-verdict { display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; margin-bottom:16px; }
.tc-verdict .tc-level { font-size:12px; font-weight:700; letter-spacing:.06em; padding:4px 10px; border-radius:999px; color:#fff; white-space:nowrap; }
.tc-verdict .tc-reason { font-size:14px; font-weight:500; color:var(--ink); }
.tc-HIGH { background:var(--pass-bg); } .tc-HIGH .tc-level { background:var(--pass); }
.tc-MEDIUM { background:var(--warn-bg); } .tc-MEDIUM .tc-level { background:var(--warn); }
.tc-LOW { background:var(--fail-bg); } .tc-LOW .tc-level { background:var(--fail); }
.tc-UNKNOWN { background:var(--unknown-bg); } .tc-UNKNOWN .tc-level { background:var(--unknown); }

.tc-contact { font-size:13px; color:var(--ink); margin-top:14px; padding:10px 12px; border-left:3px solid var(--accent);
  background:#F5F7FB; border-radius:0 8px 8px 0; }
.tc-contact span { color:var(--muted); }

.tc-signals { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin-top:16px; }
@media (max-width: 900px) { .tc-signals { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.tc-signal { border:1px solid var(--line); border-radius:8px; padding:10px 12px; background:var(--card); }
.tc-signal-head { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600; color:var(--ink); }
.tc-signal-status { margin-left:auto; font-size:11px; font-weight:600; }
.tc-signal-reason { font-size:12px; color:var(--muted); margin-top:4px; line-height:1.4; }
.tc-dot { width:8px; height:8px; border-radius:50%; display:inline-block; flex:none; }
.tc-s-pass .tc-dot { background:var(--pass); } .tc-s-pass .tc-signal-status { color:var(--pass); }
.tc-s-warn .tc-dot { background:var(--warn); } .tc-s-warn .tc-signal-status { color:var(--warn); }
.tc-s-fail .tc-dot { background:var(--fail); } .tc-s-fail .tc-signal-status { color:var(--fail); }
.tc-s-unknown .tc-dot { background:var(--unknown); } .tc-s-unknown .tc-signal-status { color:var(--unknown); }
.tc-s-fail { border-color:#FECACA; } .tc-s-warn { border-color:#FDE68A; }

.tc-section { font-size:18px; font-weight:600; color:var(--ink); margin:28px 0 4px; }
.tc-section-sub { font-size:13px; color:var(--muted); margin-bottom:12px; }

.tc-meta { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:1px; background:var(--line);
  border:1px solid var(--line); border-radius:8px; overflow:hidden; }
@media (max-width: 900px) { .tc-meta { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.tc-meta > div { background:var(--card); padding:10px 12px; }
.tc-meta .k { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-weight:600; }
.tc-meta .v { font-size:14px; color:var(--ink); margin-top:2px; }
.tc-meta .v.bad { color:var(--fail); font-weight:600; }
.tc-calc { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:13px; background:#F8FAFC;
  border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:12px 0; color:var(--ink); }
.tc-doc { font-size:14px; line-height:1.65; color:var(--ink); background:#FBFBFC; border:1px solid var(--line);
  border-radius:8px; padding:14px 16px; white-space:pre-wrap; }
.tc-tag { display:inline-block; font-size:11px; font-weight:600; padding:2px 8px; border-radius:999px;
  background:#EEF2FF; color:var(--accent); margin-right:6px; }
.tc-tag.live { background:var(--pass-bg); color:var(--pass); }
.tc-tag.draft { background:var(--unknown-bg); color:var(--unknown); }
.tc-tag.superseded { background:var(--warn-bg); color:var(--warn); }

.tc-stats { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin:8px 0 16px; }
.tc-stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.tc-stat .n { font-size:26px; font-weight:700; color:var(--ink); }
.tc-stat .l { font-size:12px; color:var(--muted); }
.tc-task-title { font-size:16px; font-weight:600; color:var(--ink); }
.tc-task-meta { font-size:13px; color:var(--muted); margin:4px 0 8px; }
.tc-reasons span { display:inline-block; font-size:12px; background:var(--fail-bg); color:var(--fail);
  border-radius:6px; padding:3px 8px; margin:0 6px 6px 0; font-weight:500; }
.tc-comment { font-size:13px; color:var(--ink); border-left:2px solid var(--line); padding-left:10px; margin:4px 0; }
</style>
"""


def show(markup):
    """Render HTML/markdown. Lines are stripped and blank lines dropped so indentation never becomes a code block."""
    st.markdown("\n".join(line.strip() for line in markup.splitlines() if line.strip()), unsafe_allow_html=True)


def esc(value):
    return html.escape(str(value)) if value is not None else ""


st.set_page_config(page_title="Trust Card Assistant", layout="wide", initial_sidebar_state="expanded")
st.html(CSS)

people = store.load_people()
customers = store.load_customers()

# ---------- sidebar ----------
with st.sidebar:
    show("**Workspace**")
    user_id = st.selectbox("Signed in as", list(people), index=list(people).index("sofie"),
                           format_func=lambda p: f"{people[p]['name']} · {people[p]['role'].capitalize()}")
    customer_id = st.selectbox("Customer", list(customers),
                               format_func=lambda c: f"{customers[c]['name']} ({customers[c]['country']})")
    st.divider()
    st.caption(f"Trust policy v{service.trust.POLICY_VERSION} · rule-based · all data synthetic")
    if st.button("Reset demo state", width="stretch"):
        service.reset()
        st.session_state.clear()
        st.rerun()

customer = customers[customer_id]
context = {"country": customer["country"], "cla": customer["cla"]}
role = people[user_id]["role"]

show(
    f"""<div class="tc-header">
      <div><div class="tc-eyebrow">Payroll knowledge · Proof of concept</div>
           <div class="tc-title">Trust Card Assistant</div></div>
      <div class="tc-context">Customer <b>{esc(customer['name'])}</b> · {esc(customer['country'])}
        {(' · ' + esc(customer['cla'])) if customer['cla'] else ''} · {customer['employees']} employees
        &nbsp;|&nbsp; Signed in as <b>{esc(people[user_id]['name'])}</b></div>
    </div>""")

if msg := st.session_state.pop("toast", None):
    st.toast(msg)


# ---------- state ----------
def current_results():
    """Re-ask only when the question, customer or user changed, or state changed (feedback, publish)."""
    if "question" not in st.session_state:
        return None, None
    key = (st.session_state["question"], customer_id, user_id)
    if st.session_state.get("dirty") or st.session_state.get("key") != key:
        st.session_state["baseline"] = service.ask(key[0], context, "baseline", user_id)
        st.session_state["trusted"] = service.ask(key[0], context, "trust", user_id)
        st.session_state["key"] = key
        st.session_state["dirty"] = False
    return st.session_state["baseline"], st.session_state["trusted"]


def mark_dirty(toast=None):
    st.session_state["dirty"] = True
    if toast:
        st.session_state["toast"] = toast
    st.rerun()


# ---------- renderers ----------
def render_baseline(r):
    src = r["sources"][0]["title"] if r["sources"] else "No source found"
    show(
        f"""<div class="tc-card">
          <div class="tc-card-label">Existing system</div>
          <div class="tc-answer">{esc(r['answer'])}</div>
          <div class="tc-source-line">Source: {esc(src)}</div>
          <div class="tc-note">No information on freshness, ownership, country scope or validation.</div>
        </div>""")


def render_trust_card(r):
    level = r["confidence"]
    tiles = "".join(
        f"""<div class="tc-signal tc-s-{s['status']}">
              <div class="tc-signal-head"><span class="tc-dot"></span>{SIGNAL_LABEL[name]}
                <span class="tc-signal-status">{STATUS_LABEL[s['status']]}</span></div>
              <div class="tc-signal-reason">{esc(s['reason'])}</div></div>"""
        for name, s in (r["signals"] or {}).items())
    contact = ""
    if r["experts"]:
        e = r["experts"][0]
        contact = f"""<div class="tc-contact">Recommended contact: <b>{esc(e['name'])}</b>
                      <span>· {esc(e['reason'])}</span></div>"""
    show(
        f"""<div class="tc-card">
          <div class="tc-card-label">Trust Card Assistant</div>
          <div class="tc-verdict tc-{level}"><span class="tc-level">{level} CONFIDENCE</span>
            <span class="tc-reason">{esc(r['confidence_reason'])}</span></div>
          <div class="tc-answer">{esc(r['answer'])}</div>
          {contact}
          <div class="tc-signals">{tiles}</div>
        </div>""")


def render_feedback(r):
    if not r["sources"]:
        return
    top = r["sources"][0]
    st.write("")
    c1, c2, c3 = st.columns([1, 1.1, 1.9])
    if c1.button("Trust and use", type="primary", width="stretch"):
        service.add_feedback(r["answer_id"], top["doc_version_id"], user_id, "trusted_used")
        mark_dirty("Recorded: trusted and used")
    with c2.popover("Report an issue", width="stretch"):
        reason = st.radio("What is wrong with source [1]?", REPORT_REASONS,
                          format_func=lambda c: service.REASONS[c], key="report-reason")
        comment = st.text_input("Comment (optional)", key="report-comment", max_chars=200)
        if st.button("Submit report", type="primary", width="stretch"):
            service.add_feedback(r["answer_id"], top["doc_version_id"], user_id, reason, comment or None)
            mark_dirty(f"Report recorded: {service.REASONS[reason]}")
    if role == "expert":
        e1, e2 = c3.columns(2)
        if e1.button("Confirm as expert", width="stretch"):
            service.add_feedback(r["answer_id"], top["doc_version_id"], user_id, "expert_confirmed")
            mark_dirty("Expert confirmation recorded")
        if e2.button("Reject as expert", width="stretch"):
            service.add_feedback(r["answer_id"], top["doc_version_id"], user_id, "expert_rejected")
            mark_dirty("Expert rejection recorded")


def render_document(d, source=None):
    """Full evidence for one document version: metadata, ranking maths, text, feedback history."""
    owner = d["owner"]
    owner_txt = f"{owner['name']}{'' if owner['active'] else ' (left company)'}" if owner else "None"
    owner_bad = "bad" if not owner or not owner["active"] else ""
    rep = d["reputation"]
    cells = [
        ("Country", d["country"] or "Any"), ("Collective agreement", d["cla"] or "Any"),
        ("Authority", (d["authority"] or "").replace("_", " ").capitalize()),
        ("Last reviewed", d["last_reviewed"] or "Not yet"),
        ("Owner", owner_txt), ("Team", owner["team"] if owner else "None"),
        ("Reputation", f"{rep['value']:.2f}"), ("Weighted reports", f"{rep['effective_n']:g}"),
    ]
    meta = "".join(
        f"<div><div class='k'>{k}</div><div class='v {owner_bad if k == 'Owner' else ''}'>{esc(v)}</div></div>"
        for k, v in cells)
    show(f"<div class='tc-meta'>{meta}</div>")
    if source:
        pen = source["context_penalty"]
        show(
            f"""<div class="tc-calc">ranking score = relevance {source['relevance']:.2f}
            × (1 − country penalty {pen:.2f}) = <b>{source['score']:.2f}</b></div>""")
    show("**Document text**")
    show(f"<div class='tc-doc'>{esc(d['body'])}</div>")
    show("**Feedback on this version**")
    if d["feedback"]:
        st.dataframe(
            [{"Date": f["date"], "By": f["user"], "Role": (f["role"] or "").capitalize(),
              "Reason": f["reason"], "Country": f["country"] or "", "Comment": f["comment"] or ""}
             for f in d["feedback"]],
            hide_index=True, width="stretch")
    else:
        st.caption("No feedback yet.")


def status_tag(status):
    return f"<span class='tc-tag {status.lower()}'>{status}</span>"


# ---------- pages ----------
tab_ask, tab_owner, tab_kb = st.tabs(["Ask", "Owner inbox", "Knowledge base"])

if "question" not in st.session_state and st.query_params.get("demo"):
    st.session_state["question"] = HERO_QUESTION  # ?demo=1 opens straight on the hero question

with tab_ask:
    with st.form("ask"):
        q_col, b_col = st.columns([6, 1])
        question = q_col.text_input("Question", value=st.session_state.get("question", HERO_QUESTION),
                                    label_visibility="collapsed", placeholder="Ask a payroll question")
        if b_col.form_submit_button("Ask", type="primary", width="stretch"):
            st.session_state["question"] = question
            st.session_state["dirty"] = True

    baseline, trusted = current_results()
    if trusted is None:
        show("<div class='tc-section-sub'>Ask a question to compare the existing system "
                    "with the Trust Card Assistant.</div>")
    else:
        left, right = st.columns([1, 1.4], gap="large")
        with left:
            render_baseline(baseline)
        with right:
            render_trust_card(trusted)
            render_feedback(trusted)

        show("<div class='tc-section'>Sources used</div>"
                    "<div class='tc-section-sub'>Every document the answer relied on, how it was ranked "
                    "for this customer, and what colleagues reported about it.</div>")
        for s in trusted["sources"]:
            d = service.document_details(s["doc_version_id"])
            with st.expander(f"[{s['ref']}]  {s['title']}  ·  {s['doc_version_id']}  ·  score {s['score']:.2f}",
                             expanded=s["ref"] == 1):
                show(status_tag(d["status"]) + f"<span class='tc-tag'>{esc(d['topic'])}</span>")
                render_document(d, s)

with tab_owner:
    tasks = service.owner_tasks()
    open_tasks = [t for t in tasks if t["status"] == "open"]
    show(
        f"""<div class="tc-stats">
          <div class="tc-stat"><div class="n">{len(open_tasks)}</div><div class="l">Open tasks</div></div>
          <div class="tc-stat"><div class="n">{sum(t['report_count'] for t in open_tasks)}</div>
            <div class="l">Reports waiting for an owner</div></div>
          <div class="tc-stat"><div class="n">{len(tasks) - len(open_tasks)}</div><div class="l">Resolved</div></div>
        </div>""")
    for t in tasks:
        with st.container(border=True):
            owner = t["owner"] or "No owner"
            routing = "" if t["owner_active"] else f" · owner has left, routed to <b>{esc(t['routed_to'])}</b>"
            state = status_tag("Live") if t["status"] == "open" else "<span class='tc-tag'>Resolved</span>"
            reasons = "".join(f"<span>{n} × {esc(r)}</span>" for r, n in t["reasons"].items())
            comments = "".join(f"<div class='tc-comment'>{esc(c)}</div>" for c in t["comments"])
            show(
                f"""<div class="tc-task-title">{esc(t['title'])}</div>
                <div class="tc-task-meta">{esc(t['doc_version_id'])} · Owner: {esc(owner)}{routing}
                  · {t['report_count']} report{'s' if t['report_count'] != 1 else ''}</div>
                <div class="tc-reasons">{reasons}</div>{comments}""")
            if t["status"] == "open":
                actions = []
                if t["next_version"]:
                    actions.append((f"Publish {t['next_version']}", "publish_new_version", "primary",
                                    f"Published {t['next_version']}"))
                actions += [("Confirm scope", "confirm_scope", "secondary", "Task resolved: scope confirmed"),
                            ("Reject feedback", "reject", "secondary", "Task resolved: feedback rejected")]
                cols = st.columns([1.3, 1, 1, 1.7])
                for col, (label, action, kind, toast) in zip(cols, actions):
                    if col.button(label, key=f"{action}-{t['id']}", type=kind, width="stretch"):
                        service.resolve_task(t["id"], action, user_id)
                        mark_dirty(toast)
            else:
                st.caption(f"Resolved: {(t['resolution'] or '').replace('_', ' ')}")

with tab_kb:
    rows = service.knowledge_base()
    show("<div class='tc-section-sub'>All document versions, including drafts waiting to be "
                "published and versions that were replaced.</div>")
    st.dataframe(
        [{"Document": r["title"], "Version": r["doc_version_id"], "Status": r["status"], "Country": r["country"],
          "Authority": r["authority"], "Owner": r["owner"], "Last reviewed": r["last_reviewed"],
          "Reports": r["reports"]} for r in rows],
        hide_index=True, width="stretch")
    pick = st.selectbox("Open a document", [r["doc_version_id"] for r in rows],
                        format_func=lambda v: next(f"{r['title']} ({v})" for r in rows if r["doc_version_id"] == v))
    d = service.document_details(pick)
    show(status_tag(d["status"]))
    render_document(d)
