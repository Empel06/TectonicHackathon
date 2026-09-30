"""Document reputation (the Validation signal) and context penalties.

Pure functions: they take a list of feedback events and return numbers.
See docs/solution-design.md section 6.
"""

from core.policy import POLICY

PRIOR_ALPHA = POLICY["reputation"]["prior_alpha"]
PRIOR_BETA = POLICY["reputation"]["prior_beta"]
MIN_EVIDENCE = POLICY["reputation"]["min_evidence"]  # below this effective_n the Validation signal is "unknown"
ROLE_WEIGHT = POLICY["reputation"]["role_weight"]

POSITIVE = {"trusted_used", "expert_confirmed"}
NEGATIVE = {"outdated", "incorrect", "incomplete", "contradicts_other_source", "expert_rejected"}
# wrong_context is NOT a reputation hit: the document may be right for another country.
# It only demotes the document for the context it was flagged in (context_penalty).

PENALTY_PER_FLAG = POLICY["ranking"]["penalty_per_wrong_country_flag"]
MAX_PENALTY = POLICY["ranking"]["max_penalty"]


def _latest_vote_per_user(events):
    """One vote per user per document version: the latest one counts."""
    latest = {}
    for e in sorted(events, key=lambda e: e["created_at"]):
        latest[(e["user_id"], e["doc_version_id"])] = e
    return list(latest.values())


def _weight(event):
    if event["reason_code"].startswith("expert_"):
        return ROLE_WEIGHT["expert"]
    return ROLE_WEIGHT.get(event.get("role"), 1)


def reputation(events, doc_owner=None):
    """Beta-Bernoulli reputation for ONE document version.

    Returns {"value", "effective_n", "positive", "negative"}.
    """
    pos = neg = 0.0
    for e in _latest_vote_per_user(events):
        if doc_owner and e["user_id"] == doc_owner:
            continue  # no self-rating
        w = _weight(e)
        if e["reason_code"] in POSITIVE:
            pos += w
        elif e["reason_code"] in NEGATIVE:
            neg += w
    n = pos + neg
    value = (PRIOR_ALPHA + pos) / (PRIOR_ALPHA + PRIOR_BETA + n)
    return {"value": round(value, 2), "effective_n": n, "positive": pos, "negative": neg}


def wrong_context_flags(events, country, doc_owner=None):
    """Weighted number of wrong_context flags for this document version in this country."""
    total = 0.0
    for e in _latest_vote_per_user(events):
        if doc_owner and e["user_id"] == doc_owner:
            continue
        if e["reason_code"] == "wrong_context" and (e.get("context") or {}).get("country") == country:
            total += _weight(e)
    return total


def context_penalty(flags):
    """Demote, never hide: capped at MAX_PENALTY."""
    return min(MAX_PENALTY, PENALTY_PER_FLAG * flags)
