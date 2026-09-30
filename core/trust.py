"""Trust scorer: six rule-based signals + confidence policy (policy v1).

Pure functions. Every signal returns {"status": pass|warn|fail|unknown, "reason": str}.
"""
from datetime import date

POLICY_VERSION = 1
FRESH_DAYS = 365
STALE_DAYS = 540
AUTHORITY_RANK = {"approved_procedure": 3, "note": 2, "chat": 1}
# order decides which reason becomes the card headline: "wrong for this customer" beats "old"
SIGNAL_ORDER = ["applicability", "authority", "freshness", "ownership", "consistency", "validation"]


def sig(status, reason):
    return {"status": status, "reason": reason}


def freshness(doc, today):
    reviewed = doc.get("last_reviewed")
    if not reviewed:
        return sig("unknown", "No review date recorded")
    reviewed = _as_date(reviewed)
    if reviewed > today:
        return sig("unknown", f"Review date {reviewed.isoformat()} is in the future (data quality)")
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
        return sig("fail", f"Owner '{owner_id}' is not in the people directory")
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
    return sig("unknown", f"Authority '{kind}' is not a known type (data quality)")


CATEGORY_LABEL = {"white_collar": "white-collar employees", "blue_collar": "blue-collar workers"}


def _as_date(value):
    if not value:
        return None
    return date.fromisoformat(value) if isinstance(value, str) else value


def valid_country(code):
    return isinstance(code, str) and len(code) == 2 and code.isupper()


def applicability(doc, context, today=None):
    """Does this source apply to THIS customer, today?

    Checks, worst result wins: country, validity period, joint committee (CLA), employee category.
    """
    today = today or date.today()
    fails, warns = [], []
    doc_country, ctx_country = doc.get("country"), context.get("country")
    if doc_country and not valid_country(doc_country):
        return sig("unknown", f"Country '{doc_country}' is not a valid country code (data quality)")
    if not doc_country:
        warns.append("Source has no country scope")
    elif ctx_country and doc_country != ctx_country:
        fails.append(f"Source is for {doc_country}, customer is {ctx_country}")

    valid_from, valid_until = _as_date(doc.get("valid_from")), _as_date(doc.get("valid_until"))
    if valid_until and valid_until < today:
        fails.append(f"Expired on {valid_until.isoformat()}")
    if valid_from and valid_from > today:
        warns.append(f"Not in force until {valid_from.isoformat()}")

    doc_cla, ctx_cla = doc.get("cla"), context.get("cla")
    if doc_cla and ctx_cla and doc_cla != ctx_cla:
        fails.append(f"Source is for {doc_cla}, customer is in {ctx_cla}")
    elif doc_cla and not ctx_cla and doc_country == ctx_country:
        warns.append(f"Only valid for {doc_cla}; customer's joint committee unknown")

    doc_cat, ctx_cat = doc.get("employee_category"), context.get("employee_category")
    if doc_cat and ctx_cat and doc_cat != ctx_cat:
        fails.append(f"Source covers {CATEGORY_LABEL[doc_cat]}, customer has {CATEGORY_LABEL[ctx_cat]}")
    elif doc_cat and not ctx_cat:
        warns.append(f"Only covers {CATEGORY_LABEL[doc_cat]}")

    if fails:
        return sig("fail", "; ".join(fails))
    if warns:
        return sig("warn", "; ".join(warns))
    scope = [doc_country, doc_cla, CATEGORY_LABEL.get(doc_cat)]
    return sig("pass", "Matches " + ", ".join(x for x in scope if x))


def context_fit(doc, context, today=None):
    """Ranking factor from metadata (trust mode only): demote sources that clearly do not fit.

    Country is deliberately NOT used here: a wrong-country source must stay visible so the
    card can warn about it; feedback (context_penalty) is what demotes it per country.
    """
    today = today or date.today()
    factor = 1.0
    if doc.get("cla") and context.get("cla") and doc["cla"] != context["cla"]:
        factor *= 0.8
    cat = doc.get("employee_category")
    if cat and context.get("employee_category") and cat != context["employee_category"]:
        factor *= 0.8
    until = _as_date(doc.get("valid_until"))
    if until and until < today:
        factor *= 0.8
    return factor


def _applies_to(doc, context):
    """Could this source be meant for this customer? (used to decide what counts as a contradiction)"""
    if doc.get("country") and doc["country"] != context.get("country"):
        return False
    for key in ("cla", "employee_category"):
        if doc.get(key) and context.get(key) and doc[key] != context[key]:
            return False
    return True


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
        other = stronger[0]
        when = f" (reviewed {other['last_reviewed']})" if other.get("last_reviewed") else ""
        return sig("warn", f"Contradicted by '{other['title']}'{when}")
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

    - any fail              -> LOW    (ceiling rule: votes can never lift a failing source)
    - any warn              -> MEDIUM
    - any insufficient data -> MEDIUM (feedback may create doubt; only people create certainty)
    - otherwise             -> HIGH
    """
    if not signals:
        return "UNKNOWN", "No relevant sources found"
    for statuses, level in ((("fail",), "LOW"), (("warn", "unknown"), "MEDIUM")):
        for status in statuses:
            for name in SIGNAL_ORDER:
                if signals[name]["status"] == status:
                    return level, signals[name]["reason"]
    return "HIGH", "All trust signals pass"


def score(top, others, context, people, rep, wrong_context_flags, today, previous_reports=0):
    signals = {
        "freshness": freshness(top, today),
        "ownership": ownership(top, people),
        "authority": authority(top),
        "applicability": applicability(top, context, today),
        "consistency": consistency(top, others, context),
        "validation": validation(rep, wrong_context_flags, context, previous_reports),
    }
    level, reason = confidence(signals)
    return signals, level, reason
