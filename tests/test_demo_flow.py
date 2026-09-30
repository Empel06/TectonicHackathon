"""Guards the live demo script. If this fails, the demo is broken."""
import pytest

from app import service, store

Q = "Do our part-time employees get a pro-rata end-of-year bonus (13th month) in December?"
NL = {"country": "NL", "cla": None}
BE = {"country": "BE", "cla": "PC200"}


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVENTS", tmp_path / "events.jsonl")
    store.reset()


def test_demo_flow():
    base = service.ask(Q, NL, "baseline")
    assert base["sources"][0]["doc_version_id"] == "be-eoy-bonus@v1"  # old system: confidently Belgian
    assert base["confidence"] is None

    r = service.ask(Q, NL)
    assert r["confidence"] == "LOW"
    assert r["signals"]["applicability"]["status"] == "fail"

    assert service.ask(Q, BE)["confidence"] == "HIGH"  # same doc is fine for a Belgian customer

    service.add_feedback(r["answer_id"], "be-eoy-bonus@v1", "sofie", "wrong_context")
    r = service.ask(Q, NL)
    assert r["sources"][0]["doc_version_id"] == "nl-13th-month@v1"  # one click flipped the ranking for NL
    assert service.ask(Q, BE)["sources"][0]["doc_version_id"] == "be-eoy-bonus@v1"  # but not for BE

    service.resolve_task("nl-13th-month@v1", "publish_new_version", "eva-smit")
    r = service.ask(Q, NL)
    assert r["sources"][0]["doc_version_id"] == "nl-13th-month@v2"
    assert r["confidence"] == "MEDIUM"

    service.add_feedback(r["answer_id"], "nl-13th-month@v2", "mark-de-vries", "expert_confirmed")
    assert service.ask(Q, NL)["confidence"] == "HIGH"
