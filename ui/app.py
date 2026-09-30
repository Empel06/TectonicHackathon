"""Streamlit UI. Run: streamlit run ui/app.py

Only talks to app.service (the contract). Person B owns this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import service, store  # noqa: E402

HERO_QUESTION = "Do our part-time employees get a pro-rata end-of-year bonus (13th month) in December?"
BADGE = {"HIGH": "#1a7f37", "MEDIUM": "#bf8700", "LOW": "#cf222e", "UNKNOWN": "#6e7781"}
DOT = {"pass": "🟢", "warn": "🟠", "fail": "🔴", "unknown": "⚪"}
DOUBT_BUTTONS = ["wrong_context", "outdated", "contradicts_other_source", "incorrect", "incomplete"]

st.set_page_config(page_title="Trust Card Assistant", layout="wide")

people = store.load_people()
customers = store.load_customers()

with st.sidebar:
    st.header("Demo controls")
    user_id = st.selectbox("Signed in as", list(people),
                           format_func=lambda p: f"{people[p]['name']} ({people[p]['role']})",
                           index=list(people).index("sofie"))
    customer_id = st.selectbox("Customer", list(customers),
                               format_func=lambda c: f"{customers[c]['name']} ({customers[c]['country']})")
    if st.button("Reset demo state", type="secondary"):
        service.reset()
        st.session_state.clear()
        st.rerun()

customer = customers[customer_id]
context = {"country": customer["country"], "cla": customer["cla"]}
role = people[user_id]["role"]

tab_ask, tab_owner = st.tabs(["Ask", "Owner inbox"])


def trust_card(r):
    level = r["confidence"]
    st.markdown(
        f"<div style='padding:14px;border-radius:10px;background:{BADGE[level]};color:white'>"
        f"<span style='font-size:1.6em;font-weight:700'>{level}</span>"
        f"<span style='font-size:1.1em'> — {r['confidence_reason']}</span></div>",
        unsafe_allow_html=True)
    st.write("")
    st.markdown(f"**Answer:** {r['answer']}")
    if r["experts"]:
        st.info("Ask: " + " · ".join(f"**{e['name']}** ({e['reason']})" for e in r["experts"]))
    sig = r["signals"] or {}
    st.markdown(" &nbsp; ".join(f"{DOT[s['status']]} {name.capitalize()}" for name, s in sig.items()),
                unsafe_allow_html=True)
    for name, s in sig.items():
        if s["status"] in ("fail", "warn"):
            st.caption(f"{DOT[s['status']]} **{name.capitalize()}**: {s['reason']}")
    with st.expander("All signals and sources"):
        for name, s in sig.items():
            st.write(f"{DOT[s['status']]} **{name}** — {s['reason']}")
        sources_table(r)


def sources_table(r):
    for s in r["sources"]:
        pen = f" · penalty −{s['context_penalty']:.0%}" if s["context_penalty"] else ""
        st.write(f"[{s['ref']}] **{s['title']}** ({s['doc_version_id']}) — score {s['score']}{pen} · "
                 f"reputation {s['reputation']['value']} · {s['reputation']['summary']}")


def feedback_bar(r):
    top = r["sources"][0] if r["sources"] else None
    if not top:
        return
    st.markdown(f"**Feedback on source [1]:** {top['title']}")
    cols = st.columns(len(DOUBT_BUTTONS) + 1)
    if cols[0].button("👍 Trust & use", key="fb-trust"):
        send(r, top, "trusted_used")
    for col, code in zip(cols[1:], DOUBT_BUTTONS):
        if col.button("👎 " + service.REASONS[code], key=f"fb-{code}"):
            send(r, top, code)
    if role == "expert":
        c1, c2 = st.columns(2)
        if c1.button("🧑‍🏫 Expert: confirm answer", type="primary"):
            send(r, top, "expert_confirmed")
        if c2.button("🧑‍🏫 Expert: reject answer"):
            send(r, top, "expert_rejected")


def send(r, source, code):
    service.add_feedback(r["answer_id"], source["doc_version_id"], user_id, code)
    st.session_state["toast"] = f"Feedback recorded: {service.REASONS[code]} on {source['doc_version_id']}"
    st.session_state["asked"] = True  # re-ask so the card updates immediately
    st.rerun()


with tab_ask:
    question = st.text_input("Question", value=HERO_QUESTION)
    if st.button("Ask", type="primary"):
        st.session_state["asked"] = True
    if st.session_state.pop("toast", None):
        st.success("Feedback recorded. The trust card below is recomputed.")
    if st.session_state.get("asked"):
        base = service.ask(question, context, "baseline", user_id)
        trusted = service.ask(question, context, "trust", user_id)
        left, right = st.columns(2)
        with left:
            st.subheader("Existing system")
            st.markdown(f"**Answer:** {base['answer']}")
            st.caption(f"Source: {base['sources'][0]['title']}" if base["sources"] else "No sources")
        with right:
            st.subheader("Trust Card Assistant")
            trust_card(trusted)
            feedback_bar(trusted)

with tab_owner:
    st.subheader("Flagged documents")
    for t in service.owner_tasks():
        with st.container(border=True):
            status = "✅ resolved" if t["status"] == "resolved" else f"🔴 {t['report_count']} reports"
            st.markdown(f"**{t['title']}** ({t['doc_version_id']}) — {status}")
            owner = t["owner"] or "none"
            if not t["owner_active"]:
                owner += " (left — routed to " + t["routed_to"] + ")"
            st.caption(f"Owner: {owner}")
            st.write(", ".join(f"{n} × {reason}" for reason, n in t["reasons"].items()))
            for c in t["comments"]:
                st.caption(f"💬 {c}")
            if t["status"] == "open":
                c1, c2, c3 = st.columns(3)
                if t["next_version"] and c1.button(f"Publish {t['next_version']}", key=f"pub-{t['id']}", type="primary"):
                    service.resolve_task(t["id"], "publish_new_version", user_id)
                    st.rerun()
                if c2.button("Confirm scope (correct as-is)", key=f"scope-{t['id']}"):
                    service.resolve_task(t["id"], "confirm_scope", user_id)
                    st.rerun()
                if c3.button("Reject feedback", key=f"rej-{t['id']}"):
                    service.resolve_task(t["id"], "reject", user_id)
                    st.rerun()
