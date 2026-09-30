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

from datetime import datetime, timedelta, timezone

from app import access, auth, privacy, store
from app.llm import compose_answer
from core.policy import POLICY
from core import reputation as rep_mod
from core import quality, retrieval, trust

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


class PermissionDenied(Exception):
    """Raised when a user tries an action their role does not allow. Enforced here, not in the UI."""


def login(username, password):
    """Return the person id for valid credentials of an ACTIVE person, else None."""
    person_id = auth.authenticate(username, password)
    person = store.load_people().get(person_id or "")
    return person_id if person and person["active"] else None


def link_token(user_id):
    return auth.make_link_token(user_id)


def login_from_link(token):
    """Person id from a signed source-link token, if still valid and the person is active."""
    person_id = auth.verify_link_token(token)
    person = store.load_people().get(person_id or "")
    return person_id if person and person["active"] else None


def _role(user_id):
    person = store.load_people().get(user_id)
    if not person or not person["active"]:
        raise PermissionDenied("Unknown or inactive user")
    return person["role"]


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

def customers_for(user_id):
    """The customers this user may work on (their portfolio)."""
    customers = store.load_customers()
    return access.portfolio(store.load_people().get(user_id), customers)


MAX_QUESTION = 500


def _require_user(user_id):
    person = store.load_people().get(user_id or "")
    if not person or not person["active"]:
        raise PermissionDenied("Sign-in required")
    return person


def ask(question, context, mode="trust", *, user_id):
    """Answer a question for an authenticated user; the customer must be in that user's portfolio."""
    _require_user(user_id)
    if mode not in ("trust", "baseline"):
        raise ValueError("mode must be 'trust' or 'baseline'")
    question = (question or "")[:MAX_QUESTION]  # bound the work per request
    minute_ago = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    recent = [e for e in store.read_events("answer") if e.get("user_id") == user_id and e["created_at"] >= minute_ago]
    if len(recent) >= POLICY["abuse"]["max_questions_per_user_per_minute"]:
        raise PermissionDenied("Too many questions, please wait a minute")
    if context.get("customer_id") and context["customer_id"] not in customers_for(user_id):
        raise PermissionDenied("Customer is not in your portfolio")
    people = store.load_people()
    feedback = store.read_events("feedback")
    customers = store.load_customers()
    person = people.get(user_id)
    # access control BEFORE retrieval: quarantined sources and other customers' documents never reach ranking
    docs = [d for d in active_docs() if access.can_use(d, person, customers, context.get("customer_id"))]
    country = context.get("country")

    per_doc = {}
    for d in docs:
        evs = _feedback_for(d["doc_version_id"], feedback)
        flags = rep_mod.wrong_context_flags(evs, country, d.get("owner"))
        per_doc[d["doc_version_id"]] = {
            "rep": rep_mod.reputation(evs, d.get("owner")),
            "flags": flags,
            "penalty": rep_mod.context_penalty(flags) if mode == "trust" else 0.0,
            "fit": trust.context_fit(d, context, today()) if mode == "trust" else 1.0,
            "reasons": Counter(e["reason_code"] for e in evs if e["reason_code"] in DOUBT),
        }

    # combined demotion: feedback penalty for this country x metadata fit (CLA, category, expiry)
    hits = retrieval.rank(question, docs, {k: 1 - (1 - v["penalty"]) * v["fit"] for k, v in per_doc.items()})
    text, llm_status = compose_answer(question, context, hits)

    sources = []
    for i, h in enumerate(hits, 1):
        d, info = h["doc"], per_doc[h["doc"]["doc_version_id"]]
        summary = ", ".join(f"{n} × {REASONS.get(c, c)}" for c, n in info["reasons"].items()) or "no doubts reported"
        sources.append({
            "ref": i, "doc_id": d["id"], "doc_version_id": d["doc_version_id"], "version": d["version"],
            "title": d["title"], "country": d.get("country"), "authority": d.get("authority"),
            "source_system": d.get("source_system"), "source_location": d.get("source_location"),
            "relevance": h["relevance"], "context_penalty": info["penalty"], "fit": info["fit"],
            "score": h["score"],
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
    role = _role(user_id)
    if reason_code.startswith("expert_") and role != "expert":
        raise PermissionDenied("Only domain experts can confirm or reject an answer")
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    recent = [e for e in store.read_events("feedback") if e["user_id"] == user_id and e["created_at"] >= hour_ago]
    if len(recent) >= POLICY["abuse"]["max_feedback_per_user_per_hour"]:
        raise PermissionDenied("Feedback limit reached for this hour")
    answers = {e["id"]: e for e in store.read_events("answer")}
    context = answers.get(answer_id, {}).get("context", {})  # context comes from what the user saw
    return store.append_event({
        "type": "feedback", "answer_id": answer_id, "doc_version_id": doc_version_id,
        "user_id": user_id, "role": role, "reason_code": reason_code,
        "context": {"country": context.get("country")}, "comment": privacy.redact(comment),
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


def draft_for(task_id):
    """Starting text for the owner's new version: the staged draft if one exists, else the live text."""
    task = next(t for t in owner_tasks() if t["id"] == task_id)
    versions = {d["doc_version_id"]: d for d in store.load_all_versions()}
    base = versions.get(task["next_version"]) or next(d for d in active_docs() if d["doc_version_id"] == task_id)
    return {"title": base["title"], "summary": base["summary"], "body": base["body"],
            "next_version": task["next_version"] or f"{task['doc_id']}@v{int(task_id.rsplit('@v', 1)[1]) + 1}"}


def resolve_task(task_id, action, user_id="an-peeters", content=None):
    """action: publish_new_version | confirm_scope | reject.

    publish_new_version without content publishes the staged draft file; with content
    ({"title", "summary", "body"}) the owner's own text becomes the new live version.
    Only the document's active owner, or the person the task was routed to, may resolve it.
    """
    role = _role(user_id)
    task = next((t for t in owner_tasks() if t["id"] == task_id), None)
    if task is None:
        raise ValueError(f"No task {task_id}")
    people = store.load_people()
    if role != "admin" and people[user_id]["name"] not in {task["routed_to"], task["owner"] if task["owner_active"] else None}:
        raise PermissionDenied(f"Only {task['routed_to']} can resolve this task")
    if action == "publish_new_version":
        task = next(t for t in owner_tasks() if t["id"] == task_id)
        if content is None:
            if not task["next_version"]:
                raise ValueError("No staged new version for this document")
            store.append_event({"type": "publish", "doc_version_id": task["next_version"],
                                "published_on": today().isoformat(), "by": user_id})
        else:
            live = next(d for d in active_docs() if d["doc_version_id"] == task_id)
            people = store.load_people()
            owner = live.get("owner")
            if not owner or not people.get(owner, {}).get("active"):
                owner = next((p["id"] for p in people.values() if p["name"] == task["routed_to"]), owner)
            # the owner's text becomes the staged draft's version if one exists, else the next number
            new_version = (int(task["next_version"].rsplit("@v", 1)[1]) if task["next_version"]
                           else max(d["version"] for d in store.load_all_versions() if d["id"] == live["id"]) + 1)
            doc = {k: v for k, v in live.items() if k not in ("body", "doc_version_id")}
            doc["last_reviewed"] = str(doc.get("last_reviewed"))
            doc.update(version=new_version, published=True, owner=owner, last_reviewed=today().isoformat(),
                       authority="approved_procedure", title=content["title"], summary=content["summary"],
                       body=content["body"], source_system="Trust Card owner inbox",
                       source_location=f"Written and published by {people.get(user_id, {}).get('name', user_id)} "
                                       f"in the owner inbox on {today().isoformat()}")
            doc.pop("messages", None)
            doc["doc_version_id"] = f"{doc['id']}@v{new_version}"
            for k in ("valid_from", "valid_until"):
                if doc.get(k) is not None:
                    doc[k] = str(doc[k])
            store.append_event({"type": "publish", "doc_version_id": doc["doc_version_id"],
                                "published_on": today().isoformat(), "by": user_id, "doc": doc})
    elif action not in {"confirm_scope", "reject"}:
        raise ValueError(f"Unknown action {action}")
    return store.append_event({"type": "resolution", "task_id": task_id, "action": action, "by": user_id})


def published_versions():
    """Where published responses went: every publish event with its live status."""
    active = {d["doc_version_id"] for d in active_docs()}
    people = store.load_people()
    return [{"doc_version_id": e["doc_version_id"], "published_on": e["published_on"],
             "by": people.get(e.get("by"), {}).get("name", e.get("by")),
             "written_in_app": bool(e.get("doc")), "live": e["doc_version_id"] in active}
            for e in reversed(store.read_events("publish"))]


def reset(user_id=None):
    """Demo control: restores the seed. Restricted to the admin role in the UI's secured mode."""
    if user_id is not None and _role(user_id) != "admin":
        raise PermissionDenied("Only the admin can reset the demo")
    store.reset()


def audit_log(limit=200):
    """Who did what, newest first, plus whether the hash chain is intact."""
    people = store.load_people()
    ok, bad, total = store.verify_chain()
    rows = []
    for e in reversed(store.read_events()[-limit:]):
        who = e.get("user_id") or e.get("by")
        what = {"feedback": REASONS.get(e.get("reason_code"), e.get("reason_code")),
                "answer": f"asked ({e.get('confidence') or 'baseline'})",
                "publish": f"published {e.get('doc_version_id')}",
                "resolution": f"resolved task: {e.get('action')}",
                "access_denied": "ACCESS DENIED to source"}.get(e["type"], e["type"])
        rows.append({"time": e["created_at"], "user": people.get(who, {}).get("name", who), "event": e["type"],
                     "action": what, "document": e.get("doc_version_id") or e.get("task_id") or "",
                     "hash": (e.get("hash") or "")[:12]})
    return {"chain_ok": ok, "first_bad_index": bad, "total": total, "rows": rows}


# ---------- evidence & knowledge base (read-only views) ----------

def document_details(doc_version_id, user_id):
    """Everything needed to check one document version: metadata, owner, full text, feedback history.

    With user_id, access is checked (source pages, knowledge base); a refusal is logged.
    """
    people = store.load_people()
    doc = next(d for d in store.load_all_versions() if d["doc_version_id"] == doc_version_id)
    _require_user(user_id)
    if not access.can_view(doc, people.get(user_id), store.load_customers()):
        store.append_event({"type": "access_denied", "user_id": user_id, "doc_version_id": doc_version_id})
        raise PermissionDenied("This source is outside your access (other customer, or quarantined)")
    active = {d["doc_version_id"]: d for d in active_docs()}
    doc = dict(active.get(doc_version_id, doc))
    owner = people.get(doc.get("owner") or "")
    events = sorted(_feedback_for(doc_version_id, store.read_events("feedback")),
                    key=lambda e: e["created_at"], reverse=True)
    found = access.personal_data_found(doc)
    if found:  # only an admin gets here; show it masked
        doc = {**doc, "summary": privacy.redact(doc.get("summary")), "body": privacy.redact(doc.get("body")),
               "messages": [{**m, "text": privacy.redact(m.get("text"))} for m in doc.get("messages") or []]}
    return {
        **{k: doc.get(k) for k in ("id", "version", "title", "country", "cla", "topic", "authority",
                                   "last_reviewed", "summary", "body", "likes", "customer_id")},
        "classification": doc.get("classification", "internal"),
        "quarantine": found or (["marked restricted"] if doc.get("classification") == "restricted" else []),
        "doc_version_id": doc_version_id,
        "status": _status(doc, active),
        "owner": {"name": owner["name"], "team": owner["team"], "active": owner["active"]} if owner else None,
        "owner_id": doc.get("owner"),
        "source_system": doc.get("source_system"),
        "source_location": doc.get("source_location"),
        "messages": [{**m, "time": str(m.get("time", ""))} for m in (doc.get("messages") or [])],
        "versions": [{"doc_version_id": v["doc_version_id"], "version": v["version"],
                      "status": _status(active.get(v["doc_version_id"], v), active)}
                     for v in sorted((v for v in store.load_all_versions() if v["id"] == doc["id"]),
                                     key=lambda v: -v["version"])],
        "reputation": rep_mod.reputation(events, doc.get("owner")),
        "valid_from": str(doc["valid_from"]) if doc.get("valid_from") else None,
        "valid_until": str(doc["valid_until"]) if doc.get("valid_until") else None,
        "employee_category": doc.get("employee_category"),
        "quality_issues": quality.check(doc, people, today()),
        "feedback": [{
            "date": e["created_at"][:10],
            "user": people.get(e["user_id"], {}).get("name", e["user_id"]),
            "role": e.get("role"),
            "reason": REASONS.get(e["reason_code"], e["reason_code"]),
            "country": (e.get("context") or {}).get("country"),
            "comment": e.get("comment"),
        } for e in events],
    }


def _status(doc, active):
    if doc["doc_version_id"] in active:
        return "Live"
    live = next((d for d in active.values() if d["id"] == doc["id"]), None)
    if live and live["version"] > doc["version"]:
        return "Superseded"
    return "Draft"


def knowledge_base(user_id):
    """All document versions this user may see, with their status, for the Knowledge base view."""
    person = _require_user(user_id)
    people = store.load_people()
    customers = store.load_customers()
    active = {d["doc_version_id"]: d for d in active_docs()}
    feedback = store.read_events("feedback")
    rows = []
    for d in store.load_all_versions():
        doc = active.get(d["doc_version_id"], d)
        if doc.get("customer_id") and not access.can_view(doc, person, customers):
            continue  # other customers' documents are not even listed
        owner = people.get(doc.get("owner") or "")
        evs = _feedback_for(d["doc_version_id"], feedback)
        rows.append({
            "doc_version_id": d["doc_version_id"], "title": doc["title"], "version": doc["version"],
            "source_system": doc.get("source_system") or "Unknown",
            "status": _status(doc, active), "country": doc.get("country") or "Any",
            "authority": (doc.get("authority") or "").replace("_", " ").capitalize(),
            "owner": (owner["name"] + ("" if owner["active"] else " (left)")) if owner else "None",
            "last_reviewed": str(doc.get("last_reviewed") or "Not yet"),
            "reports": len(evs),
            "quality_issues": len(quality.check(doc, people, today())),
            "classification": doc.get("classification", "internal"),
            "customer": customers.get(doc.get("customer_id") or "", {}).get("name", ""),
        })
    all_versions = {d["doc_version_id"]: d for d in store.load_all_versions()}
    for r in rows:
        if access.quarantined(all_versions[r["doc_version_id"]]):
            r["status"] = "Quarantined"
    order = {"Live": 0, "Draft": 1, "Superseded": 2, "Quarantined": 3}
    rows.sort(key=lambda r: (order[r["status"]], r["doc_version_id"]))
    return rows
