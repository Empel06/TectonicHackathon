from datetime import date

from core import reputation as R
from core import trust as T


def fb(user, code, doc="d@v1", role="consultant", country="NL", t="2026-09-01T00:00:00Z"):
    return {"user_id": user, "doc_version_id": doc, "role": role, "reason_code": code,
            "context": {"country": country}, "created_at": t}


def test_no_feedback_is_neutral_and_unknown():
    rep = R.reputation([])
    assert rep["value"] == 0.5
    assert T.validation(rep, 0, {"country": "NL"})["status"] == "unknown"


def test_single_negative_vote_stays_unknown():
    rep = R.reputation([fb("u1", "outdated")])
    assert T.validation(rep, 0, {"country": "NL"})["status"] == "unknown"


def test_expert_weighs_three_times():
    assert R.reputation([fb("x", "expert_confirmed", role="expert")])["effective_n"] == 3


def test_owner_cannot_rate_own_document():
    assert R.reputation([fb("owner", "trusted_used")], doc_owner="owner")["effective_n"] == 0


def test_same_user_counts_once():
    evs = [fb("u1", "outdated", t="2026-09-01T00:00:00Z"), fb("u1", "outdated", t="2026-09-02T00:00:00Z")]
    assert R.reputation(evs)["effective_n"] == 1


def test_wrong_context_only_penalises_that_country():
    evs = [fb(f"u{i}", "wrong_context", country="NL") for i in range(3)]
    assert R.wrong_context_flags(evs, "NL") == 3
    assert R.wrong_context_flags(evs, "BE") == 0
    assert R.reputation(evs)["effective_n"] == 0  # not a reputation hit


def test_penalty_is_capped():
    assert R.context_penalty(100) == R.MAX_PENALTY


def _doc(**kw):
    base = {"title": "Doc", "country": "BE", "cla": None, "authority": "approved_procedure",
            "owner": "o", "last_reviewed": "2026-09-01", "topic": "t", "claim": "c"}
    return {**base, **kw}


PEOPLE = {"o": {"name": "Owner", "team": "T", "active": True}}
GOOD_REP = {"value": 0.8, "effective_n": 5}


def test_applicability_fail_caps_at_low_whatever_the_votes():
    signals, level, reason = T.score(_doc(), [], {"country": "NL"}, PEOPLE, GOOD_REP, 0, date(2026, 9, 30))
    assert level == "LOW"
    assert "BE" in reason and "NL" in reason


def test_all_pass_is_high():
    _, level, _ = T.score(_doc(), [], {"country": "BE"}, PEOPLE, GOOD_REP, 0, date(2026, 9, 30))
    assert level == "HIGH"


def test_unvalidated_is_at_most_medium():
    _, level, _ = T.score(_doc(), [], {"country": "BE"}, PEOPLE, {"value": 0.5, "effective_n": 0}, 0, date(2026, 9, 30))
    assert level == "MEDIUM"


def test_every_signal_has_a_reason():
    signals, _, _ = T.score(_doc(), [], {"country": "BE"}, PEOPLE, GOOD_REP, 0, date(2026, 9, 30))
    assert all(s["reason"] for s in signals.values())
