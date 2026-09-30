"""Trust scorer: six rule-based signals + confidence policy (policy v1).

Pure functions. Every signal returns {"status": pass|warn|fail|unknown, "reason": str}.
"""
from datetime import date

POLICY_VERSION = 1
FRESH_DAYS = 365
STALE_DAYS = 540
AUTHORITY_RANK = {"approved_procedure": 3, "note": 2, "chat": 1}
SIGNAL_ORDER = ["freshness", "ownership", "authority", "applicability", "consistency", "validation"]


def sig(status, reason):
    return {"status": status, "reason": reason}


def freshness(doc, today):
    reviewed = doc.get("last_reviewed")
    if not reviewed:
        return sig("unknown", "No review date")
    if isinstance(reviewed, str):
        reviewed = date.fromisoformat(reviewed)
    days = (today - reviewed).days
    months = round(days / 30)
    if days <= FRESH_DAYS:
        return sig("pass", f"Reviewed {days} days ago")
    if days <= STALE_DAYS:
        return sig("warn", f"Last reviewed {months} months ago")
    return sig("fail", f"Last reviewed {months} months ago")


def ownership(doc, people):
    owner_id = doc.get("owner")
    if not owner_id:
        return sig("fail", "No owner")
    person = people.get(owner_id)
    if not person:
        return sig("fail", f"Owner '{owner_id}' unknown")
    if not person["active"]:
        return sig("fail", f"Owner {person['name']} has left the company")
    return sig("pass", f"Owner: {person['name']} ({person['team']})")


def authority(doc):
    kind = doc.get("authority")
    if kind == "approved_procedure":
        return sig("pass", "Approved procedure")
    if kind == "note":
        return sig("warn", "Informal note, not an approved procedure")
    if kind == "chat":
        return sig("fail", "Chat message, not an official source")
    return sig("unknown", "Authority unknown")


def applicability(doc, context):
    doc_country, ctx_country = doc.get("country"), context.get("country")
    if not doc_country:
        return sig("warn", "Source has no country scope")
    if ctx_country and doc_country != ctx_country:
        return sig("fail", f"Source is for {doc_country}, customer is {ctx_country}")
    doc_cla, ctx_cla = doc.get("cla"), context.get("cla")
    if doc_cla and ctx_cla and doc_cla != ctx_cla:
        return sig("warn", f"Source is for {doc_cla}, customer has {ctx_cla}")
    return sig("pass", f"Matches country {doc_country}" + (f" and {doc_cla}" if doc_cla else ""))


def _applies_to(doc, context):
    return not doc.get("country") or doc.get("country") == context.get("country")


def consistency(top, others, context):
    """Do other relevant sources that apply to this context make a different claim?"""
    conflicts = [d for d in others
                 if d.get("topic") == top.get("topic") and _applies_to(d, context)
                 and d.get("claim") != top.get("claim")]
    if not conflicts:
        return sig("pass", "No conflicting sources")
    if not _applies_to(top, context):
        # a source for another country cannot overrule one that applies here
        return sig("warn", f"'{conflicts[0]['title']}' applies to {context.get('country')} and says otherwise")
    top_rank = AUTHORITY_RANK.get(top.get("authority"), 0)
    stronger = [d for d in conflicts if AUTHORITY_RANK.get(d.get("authority"), 0) >= top_rank]
    if stronger:
        return sig("warn", f"Contradicted by '{stronger[0]['title']}'")
    return sig("pass", f"{len(conflicts)} lower-authority source(s) disagree (e.g. '{conflicts[0]['title']}'); superseded")


def validation(rep, wrong_context_flags, context, previous_reports=0, min_evidence=3):
    """rep: output of core.reputation.reputation()."""
    country = context.get("country")
    if wrong_context_flags > 0:
        return sig("warn", f"Flagged {wrong_context_flags:g}× as wrong country for {country}")
    if rep["effective_n"] < min_evidence:
        if previous_reports:
            return sig("unknown", f"New version, published after {previous_reports} report(s) on the old one; not yet validated")
        return sig("unknown", f"Not enough feedback yet ({rep['effective_n']:g} reports)")
    if rep["value"] >= 0.70:
        return sig("pass", f"Reputation {rep['value']:.2f} from {rep['effective_n']:g} weighted reports")
    if rep["value"] >= 0.40:
        return sig("warn", f"Reputation {rep['value']:.2f} from {rep['effective_n']:g} weighted reports")
    return sig("fail", f"Reputation {rep['value']:.2f} from {rep['effective_n']:g} weighted reports")


def confidence(signals):
    """Policy v1. Returns (level, reason).

    - any fail           -> LOW   (ceiling rule: votes can never lift a failing source)
    - any warn           -> MEDIUM
    - validation unknown -> MEDIUM (feedback may create doubt; only people create certainty)
    - otherwise          -> HIGH
    """
    if not signals:
        return "UNKNOWN", "No relevant sources found"
    for status, level in (("fail", "LOW"), ("warn", "MEDIUM")):
        for name in SIGNAL_ORDER:
            if signals[name]["status"] == status:
                return level, signals[name]["reason"]
    if signals["validation"]["status"] == "unknown":
        return "MEDIUM", signals["validation"]["reason"]
    return "HIGH", "All trust signals pass"


def score(top, others, context, people, rep, wrong_context_flags, today, previous_reports=0):
    signals = {
        "freshness": freshness(top, today),
        "ownership": ownership(top, people),
        "authority": authority(top),
        "applicability": applicability(top, context),
        "consistency": consistency(top, others, context),
        "validation": validation(rep, wrong_context_flags, context, previous_reports),
    }
    level, reason = confidence(signals)
    return signals, level, reason
