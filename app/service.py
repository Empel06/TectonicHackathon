"""Application service: the ONLY functions the UI calls. This is the team contract.

    ask(question, context, mode="trust"|"baseline", user_id) -> AskResult dict
    add_feedback(answer_id, doc_version_id, user_id, reason_code, comment=None) -> event
    owner_tasks() -> [Task]
    resolve_task(task_id, action, user_id) -> event     action: publish_new_version|confirm_scope|reject
    reset()

See README.md "Contract" for the dict shapes.
"""
from collections import Counter
from datetime import date

from app import store
from app.llm import compose_answer
from core import reputation as rep_mod
from core import retrieval, trust

REASONS = {
    "trusted_used": "I trust this and will use it",
    "wrong_context": "Wrong country / context",
    "outdated": "Outdated",
    "contradicts_other_source": "Contradicts another source",
    "incorrect": "Incorrect",
    "incomplete": "Incomplete",
    "unclear": "Unclear",
    "expert_confirmed": "Expert: confirmed",
    "expert_rejected": "Expert: rejected",
}
DOUBT = rep_mod.NEGATIVE | {"wrong_context"}


def today():
    return date.today()


# ---------- documents & versions ----------

def _published_ids():
    return {e["doc_version_id"]: e for e in store.read_events("publish")}


def _versions_by_doc():
    by_doc = {}
    for d in store.load_all_versions():
        by_doc.setdefault(d["id"], []).append(d)
    for vs in by_doc.values():
        vs.sort(key=lambda d: d["version"])
    return by_doc


def active_docs():
    """Latest published version of every document."""
    published = _published_ids()
    active = []
    for versions in _versions_by_doc().values():
        live = [d for d in versions if d.get("published") or d["doc_version_id"] in published]
        if not live:
            continue
        doc = dict(live[-1])
        pub = published.get(doc["doc_version_id"])
        if pub and not doc.get("last_reviewed"):
            doc["last_reviewed"] = pub["published_on"]
        active.append(doc)
    return active


def _feedback_for(doc_version_id, feedback):
    return [e for e in feedback if e["doc_version_id"] == doc_version_id]


def _previous_reports(doc, feedback):
    ids = {f"{doc['id']}@v{v}" for v in range(1, doc["version"])}
    return len({(e["user_id"], e["doc_version_id"]) for e in feedback
                if e["doc_version_id"] in ids and e["reason_code"] in DOUBT})


# ---------- ask ----------

def ask(question, context, mode="trust", user_id="sofie"):
    people = store.load_people()
    feedback = store.read_events("feedback")
    docs = active_docs()
    country = context.get("country")

    per_doc = {}
    for d in docs:
        evs = _feedback_for(d["doc_version_id"], feedback)
        flags = rep_mod.wrong_context_flags(evs, country, d.get("owner"))
        per_doc[d["doc_version_id"]] = {
            "rep": rep_mod.reputation(evs, d.get("owner")),
            "flags": flags,
            "penalty": rep_mod.context_penalty(flags) if mode == "trust" else 0.0,
            "reasons": Counter(e["reason_code"] for e in evs if e["reason_code"] in DOUBT),
        }

    hits = retrieval.rank(question, docs, {k: v["penalty"] for k, v in per_doc.items()})
    text, llm_status = compose_answer(question, context, hits)

    sources = []
    for i, h in enumerate(hits, 1):
        d, info = h["doc"], per_doc[h["doc"]["doc_version_id"]]
        summary = ", ".join(f"{n} × {REASONS.get(c, c)}" for c, n in info["reasons"].items()) or "no doubts reported"
        sources.append({
            "ref": i, "doc_id": d["id"], "doc_version_id": d["doc_version_id"], "version": d["version"],
            "title": d["title"], "country": d.get("country"), "authority": d.get("authority"),
            "relevance": h["relevance"], "context_penalty": h["penalty"], "score": h["score"],
            "reputation": {**info["rep"], "summary": summary},
        })

    result = {
        "answer_id": None, "mode": mode, "question": question, "context": context,
        "answer": text, "llm_status": llm_status, "sources": sources,
        "confidence": None, "confidence_reason": None, "signals": None, "experts": None,
        "trust_policy_version": trust.POLICY_VERSION,
    }

    if mode == "trust":
        if hits:
            top = hits[0]["doc"]
            info = per_doc[top["doc_version_id"]]
            signals, level, reason = trust.score(
                top, [h["doc"] for h in hits[1:]], context, people, info["rep"], info["flags"],
                today(), _previous_reports(top, feedback))
        else:
            signals, (level, reason) = None, trust.confidence(None)
        result.update(confidence=level, confidence_reason=reason, signals=signals,
                      experts=_experts(level, hits, context, people))

    event = store.append_event({"type": "answer", "user_id": user_id, **{k: result[k] for k in (
        "mode", "question", "context", "answer", "confidence", "signals", "trust_policy_version")},
        "doc_version_ids": [s["doc_version_id"] for s in sources]})
    result["answer_id"] = event["id"]
    return result


def _experts(level, hits, context, people):
    if level == "HIGH":
        return []
    country = context.get("country")
    out = []
    if hits:
        top = hits[0]["doc"]
        owner = people.get(top.get("owner") or "")
        if owner and owner["active"] and top.get("country") == country:
            out.append({"id": owner["id"], "name": owner["name"], "reason": f"Owner of '{top['title']}'"})
    for p in people.values():
        if p["active"] and p["role"] == "expert" and country in p["topics"] and p["id"] not in {e["id"] for e in out}:
            out.append({"id": p["id"], "name": p["name"], "reason": f"{p['team']} expert for {country}"})
    return out


# ---------- feedback ----------

def add_feedback(answer_id, doc_version_id, user_id, reason_code, comment=None):
    if reason_code not in REASONS:
        raise ValueError(f"Unknown reason_code {reason_code}")
    answers = {e["id"]: e for e in store.read_events("answer")}
    context = answers.get(answer_id, {}).get("context", {})  # context comes from what the user saw
    role = store.load_people().get(user_id, {}).get("role", "consultant")
    return store.append_event({
        "type": "feedback", "answer_id": answer_id, "doc_version_id": doc_version_id,
        "user_id": user_id, "role": role, "reason_code": reason_code,
        "context": {"country": context.get("country")}, "comment": comment,
        "trust_policy_version": trust.POLICY_VERSION,
    })


# ---------- owner inbox ----------

def owner_tasks():
    people = store.load_people()
    feedback = store.read_events("feedback")
    resolved = {e["task_id"]: e for e in store.read_events("resolution")}
    by_doc = _versions_by_doc()
    published = _published_ids()
    tasks = []
    for doc in active_docs():
        dv = doc["doc_version_id"]
        latest = {}
        for e in _feedback_for(dv, feedback):
            if e["reason_code"] in DOUBT:
                latest[e["user_id"]] = e
        if not latest:
            continue
        owner = people.get(doc.get("owner") or "")
        routed = owner if owner and owner["active"] else next(
            (p for p in people.values() if p["active"] and p["role"] == "owner" and doc.get("country") in p["topics"]), None)
        staged = [d for d in by_doc[doc["id"]] if d["version"] > doc["version"]
                  and not d.get("published") and d["doc_version_id"] not in published]
        evs = sorted(latest.values(), key=lambda e: e["created_at"])
        tasks.append({
            "id": dv, "doc_id": doc["id"], "doc_version_id": dv, "title": doc["title"],
            "owner": owner["name"] if owner else None,
            "owner_active": bool(owner and owner["active"]),
            "routed_to": routed["name"] if routed else "Knowledge team",
            "report_count": len(evs),
            "reasons": dict(Counter(REASONS[e["reason_code"]] + (f" ({e['context'].get('country')})" if e["reason_code"] == "wrong_context" else "") for e in evs)),
            "comments": [e["comment"] for e in evs if e.get("comment")],
            "status": "resolved" if dv in resolved else "open",
            "resolution": resolved.get(dv, {}).get("action"),
            "next_version": staged[0]["doc_version_id"] if staged else None,
        })
    tasks.sort(key=lambda t: (t["status"] != "open", -t["report_count"]))
    return tasks


def resolve_task(task_id, action, user_id="an-peeters"):
    if action == "publish_new_version":
        task = next(t for t in owner_tasks() if t["id"] == task_id)
        if not task["next_version"]:
            raise ValueError("No staged new version for this document")
        store.append_event({"type": "publish", "doc_version_id": task["next_version"],
                            "published_on": today().isoformat(), "by": user_id})
    elif action not in {"confirm_scope", "reject"}:
        raise ValueError(f"Unknown action {action}")
    return store.append_event({"type": "resolution", "task_id": task_id, "action": action, "by": user_id})


def reset():
    store.reset()
