"""Security rules are enforced in the service layer, not by hiding buttons in the UI."""
import json

import pytest
from conftest import TEST_PASSWORD

from app import auth, privacy, service, store


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVENTS", tmp_path / "events.jsonl")
    auth._failures.clear()
    store.reset()


Q = "Do our part-time employees get a pro-rata end-of-year bonus (13th month) in December?"
NL = {"country": "NL", "cla": None}


def test_no_credentials_in_the_repository():
    root = auth.PEOPLE_FILE.parent.parent
    assert not (root / "data" / "users.json").exists()          # no stored credentials or hashes
    assert (root / ".env.example").read_text().count("DEMO_PASSWORD=\n") == 1  # template has no value
    for path in list((root / "app").glob("*.py")) + list((root / "ui").glob("*.py")):
        assert TEST_PASSWORD not in path.read_text()


def test_nobody_can_sign_in_without_a_configured_password(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "")
    assert service.login("sofie", "") is None and service.login("sofie", "anything") is None


def test_login_accepts_valid_and_rejects_wrong_password():
    assert service.login("sofie", TEST_PASSWORD) == "sofie"
    assert service.login("sofie", "wrong") is None
    assert service.login("nobody", TEST_PASSWORD) is None


def test_people_who_left_cannot_log_in():
    assert service.login("joost-bakker", TEST_PASSWORD) is None


def test_lockout_after_repeated_failures():
    for _ in range(auth.MAX_FAILURES):
        service.login("eva-smit", "guess")
    assert service.login("eva-smit", TEST_PASSWORD) is None  # locked, even with the right password


def test_consultant_cannot_give_expert_verdict():
    r = service.ask(Q, NL, user_id="sofie")
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
    r = service.ask(Q, NL, user_id="sofie")
    service.add_feedback(r["answer_id"], "be-eoy-bonus@v1", "sofie", "outdated")
    service.add_feedback(r["answer_id"], "nl-13th-month@v1", "sofie", "outdated")
    with pytest.raises(service.PermissionDenied):
        service.add_feedback(r["answer_id"], "chat-eoy-parttime@v1", "sofie", "outdated")


def test_personal_data_is_redacted_before_storage():
    r = service.ask(Q, NL, user_id="sofie")
    e = service.add_feedback(r["answer_id"], "be-eoy-bonus@v1", "sofie", "wrong_context",
                             "Employee 85.07.30-033.28, IBAN BE68 5390 0754 7034, jan@klant.be")
    stored = store.EVENTS.read_text()
    assert "85.07.30-033.28" not in stored and "BE68" not in stored and "jan@klant.be" not in stored
    assert "[IBAN removed]" in e["comment"]


def test_comment_length_is_capped():
    assert len(privacy.redact("x" * 5000)) == privacy.MAX_COMMENT


def test_audit_chain_detects_tampering():
    service.ask(Q, NL, user_id="sofie")
    assert store.verify_chain()[0]
    store.simulate_tampering()
    ok, bad, _ = store.verify_chain()
    assert not ok and bad == 1
    store.reset()
    assert store.verify_chain()[0]


def test_only_admin_can_reset_when_user_is_given(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    with pytest.raises(service.PermissionDenied):
        service.reset("sofie")
    service.reset("admin")


def test_anonymous_or_unknown_users_get_nothing():
    for user in (None, "", "nobody", "joost-bakker"):
        with pytest.raises(service.PermissionDenied):
            service.ask(Q, NL, user_id=user)
        with pytest.raises(service.PermissionDenied):
            service.document_details("be-eoy-bonus@v1", user)
        with pytest.raises(service.PermissionDenied):
            service.knowledge_base(user)


def test_cannot_ask_for_a_customer_outside_the_portfolio():
    with pytest.raises(service.PermissionDenied):
        service.ask(Q, {"customer_id": "zorggroep-oost", "country": "NL", "cla": "CAO VVT"}, user_id="sofie")


def test_question_length_is_bounded():
    r = service.ask("bonus " * 1000, NL, user_id="sofie")
    assert len(r["question"]) <= service.MAX_QUESTION


def test_questions_are_rate_limited(monkeypatch):
    monkeypatch.setitem(service.POLICY["abuse"], "max_questions_per_user_per_minute", 2)
    service.ask(Q, NL, user_id="sofie")
    service.ask(Q, NL, user_id="sofie")
    with pytest.raises(service.PermissionDenied):
        service.ask(Q, NL, user_id="sofie")


def test_feedback_only_on_own_answers_and_their_sources():
    mine = service.ask(Q, NL, user_id="sofie")
    theirs = service.ask(Q, NL, user_id="eva-smit")
    with pytest.raises(service.PermissionDenied):   # someone else's answer
        service.add_feedback(theirs["answer_id"], "be-eoy-bonus@v1", "sofie", "outdated")
    with pytest.raises(service.PermissionDenied):   # a document that answer did not show
        service.add_feedback(mine["answer_id"], "be-meal-vouchers@v1", "sofie", "outdated")
    with pytest.raises(service.PermissionDenied):   # an answer that does not exist
        service.add_feedback("ans-fake", "be-eoy-bonus@v1", "sofie", "outdated")


def test_owner_inbox_is_isolated_per_portfolio():
    service.ask("Is there an extra night premium from the local agreement?",
                {"customer_id": "zorggroep-oost", "country": "NL", "cla": "CAO VVT"}, user_id="bram-janssen")
    r = service.ask("Is there an extra night premium from the local agreement?",
                    {"customer_id": "zorggroep-oost", "country": "NL", "cla": "CAO VVT"}, user_id="bram-janssen")
    service.add_feedback(r["answer_id"], "cust-zorggroep-local-agreement@v1", "bram-janssen", "incomplete")
    assert "cust-zorggroep-local-agreement@v1" in {t["id"] for t in service.owner_tasks("bram-janssen")}
    assert "cust-zorggroep-local-agreement@v1" not in {t["id"] for t in service.owner_tasks("sofie")}
    with pytest.raises(service.PermissionDenied):
        service.draft_for("nl-13th-month@v1", "sofie")


def test_publishing_rules():
    live = service.draft_for("nl-13th-month@v1", "eva-smit")
    with pytest.raises(ValueError):   # personal data is refused
        service.resolve_task("nl-13th-month@v1", "publish_new_version", "eva-smit",
                             {**live, "body": live["body"] + " IBAN BE68 5390 0754 7034"})
    with pytest.raises(ValueError):   # oversized text is refused
        service.resolve_task("nl-13th-month@v1", "publish_new_version", "eva-smit", {**live, "body": "x" * 30_000})


def test_unchanged_republish_is_refused():
    r = service.ask("How are tips and service charge declared?",
                    {"customer_id": "de-kaai", "country": "BE", "cla": "PC302"}, user_id="an-peeters")
    task = next(t for t in service.owner_tasks("an-peeters") if t["id"] == "be-horeca-tips@v1")
    current = service.document_details("be-horeca-tips@v1", "an-peeters")
    with pytest.raises(ValueError):
        service.resolve_task(task["id"], "publish_new_version", "an-peeters",
                             {"title": current["title"], "summary": current["summary"], "body": current["body"]})
    assert r["sources"]


def test_owner_cannot_self_upgrade_authority():
    draft = {"title": "Tips in hospitality (BE, PC 302)", "summary": "Updated note on tips, flat rate per day.",
             "body": "Updated short note on tips and service charges."}
    service.resolve_task("be-horeca-tips@v1", "publish_new_version", "an-peeters", draft)
    assert service.document_details("be-horeca-tips@v2", "an-peeters")["authority"] == "note"


def test_audit_and_demo_controls_are_admin_only(monkeypatch):
    with pytest.raises(service.PermissionDenied):
        service.audit_log("sofie")
    with pytest.raises(service.PermissionDenied):
        service.simulate_tampering("sofie")
    monkeypatch.setenv("DEMO_MODE", "false")
    with pytest.raises(service.PermissionDenied):
        service.reset("sofie")
    service.reset("admin")


def test_tampered_history_is_not_used():
    before = len(store.read_events())
    store.simulate_tampering()
    assert len(store.read_events()) == 1 < before   # everything from the broken event on is ignored


def test_unreviewed_document_files_are_ignored(monkeypatch, tmp_path):
    import json
    manifest = json.loads(store.MANIFEST.read_text())
    manifest.pop("be-meal-vouchers@v1.md")
    fake = tmp_path / "manifest.json"
    fake.write_text(json.dumps(manifest))
    monkeypatch.setattr(store, "MANIFEST", fake)
    store._parse_files.cache_clear()
    assert "be-meal-vouchers@v1" not in {d["doc_version_id"] for d in store.load_all_versions()}
    assert store.rejected_files() == ["be-meal-vouchers@v1.md"]
    store._parse_files.cache_clear()


def test_manifest_matches_the_reviewed_documents():
    assert store.rejected_files() == []


def test_failed_login_tracking_is_bounded(monkeypatch):
    monkeypatch.setattr(auth, "MAX_TRACKED", 10)
    for i in range(40):
        service.login(f"user{i}" * 20, "x")
    assert len(auth._failures) <= 10
