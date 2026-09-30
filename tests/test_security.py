"""Security rules are enforced in the service layer, not by hiding buttons in the UI."""
import json

import pytest

from app import auth, privacy, service, store


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVENTS", tmp_path / "events.jsonl")
    auth._failures.clear()
    store.reset()


Q = "Do our part-time employees get a pro-rata end-of-year bonus (13th month) in December?"
NL = {"country": "NL", "cla": None}


def test_passwords_are_stored_hashed_only():
    raw = auth.USERS_FILE.read_text()
    assert "demo2026" not in raw
    assert all({"salt", "hash"} <= set(u) and "password" not in u for u in json.loads(raw))


def test_login_accepts_valid_and_rejects_wrong_password():
    assert service.login("sofie", "demo2026") == "sofie"
    assert service.login("sofie", "wrong") is None
    assert service.login("nobody", "demo2026") is None


def test_people_who_left_cannot_log_in():
    assert service.login("joost-bakker", "demo2026") is None


def test_lockout_after_repeated_failures():
    for _ in range(auth.MAX_FAILURES):
        service.login("eva-smit", "guess")
    assert service.login("eva-smit", "demo2026") is None  # locked, even with the right password


def test_consultant_cannot_give_expert_verdict():
    r = service.ask(Q, NL)
    with pytest.raises(service.PermissionDenied):
        service.add_feedback(r["answer_id"], "be-eoy-bonus@v1", "sofie", "expert_confirmed")


def test_only_the_routed_owner_can_publish():
    with pytest.raises(service.PermissionDenied):
        service.resolve_task("nl-13th-month@v1", "publish_new_version", "sofie")
    with pytest.raises(service.PermissionDenied):
        service.resolve_task("nl-13th-month@v1", "publish_new_version", "an-peeters")  # owner of another doc
    service.resolve_task("nl-13th-month@v1", "publish_new_version", "eva-smit")


def test_feedback_is_rate_limited(monkeypatch):
    monkeypatch.setitem(service.POLICY["abuse"], "max_feedback_per_user_per_hour", 2)
    r = service.ask(Q, NL)
    service.add_feedback(r["answer_id"], "be-eoy-bonus@v1", "sofie", "outdated")
    service.add_feedback(r["answer_id"], "nl-13th-month@v1", "sofie", "outdated")
    with pytest.raises(service.PermissionDenied):
        service.add_feedback(r["answer_id"], "chat-eoy-parttime@v1", "sofie", "outdated")


def test_personal_data_is_redacted_before_storage():
    r = service.ask(Q, NL)
    e = service.add_feedback(r["answer_id"], "be-eoy-bonus@v1", "sofie", "wrong_context",
                             "Employee 85.07.30-033.28, IBAN BE68 5390 0754 7034, jan@klant.be")
    stored = store.EVENTS.read_text()
    assert "85.07.30-033.28" not in stored and "BE68" not in stored and "jan@klant.be" not in stored
    assert "[IBAN removed]" in e["comment"]


def test_comment_length_is_capped():
    assert len(privacy.redact("x" * 5000)) == privacy.MAX_COMMENT


def test_audit_chain_detects_tampering():
    service.ask(Q, NL)
    assert store.verify_chain()[0]
    store.simulate_tampering()
    ok, bad, _ = store.verify_chain()
    assert not ok and bad == 1
    store.reset()
    assert store.verify_chain()[0]


def test_only_admin_can_reset_when_user_is_given():
    with pytest.raises(service.PermissionDenied):
        service.reset("sofie")
    service.reset("admin")
