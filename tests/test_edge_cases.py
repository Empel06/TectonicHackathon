"""Each synthetic edge case must produce the verdict the demo claims."""
from datetime import date

import pytest

from app import service, store
from core import quality, trust


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVENTS", tmp_path / "events.jsonl")
    store.reset()


def ctx(customer_id):
    c = store.load_customers()[customer_id]
    return {"country": c["country"], "cla": c["cla"], "employee_category": c["employee_category"]}


def ask(customer_id, question):
    return service.ask(question, ctx(customer_id))


HERO = "Do our part-time employees get a pro-rata end-of-year bonus (13th month) in December?"


def test_wrong_joint_committee_is_low():
    r = ask("maes", HERO)
    assert r["confidence"] == "LOW" and "PC124" in r["confidence_reason"]


def test_expired_rule_is_low():
    r = ask("janssens", "What is the maximum tax-free telework allowance?")
    assert r["confidence"] == "LOW" and r["confidence_reason"].startswith("Expired")


def test_contradicting_procedures_cap_at_medium():
    r = ask("van-dijk", "Is a transition payment due on dismissal in the first year of service?")
    assert r["sources"][0]["doc_version_id"] == "nl-transition-payment-2020@v1"
    assert r["signals"]["consistency"]["status"] == "warn"


def test_popular_chat_cannot_reach_high():
    r = ask("van-dijk", "How much holiday allowance (vakantiegeld) do Dutch employees get?")
    assert r["sources"][0]["reputation"]["positive"] == 3  # upvoted...
    assert r["confidence"] == "LOW"                         # ...but still a chat message


def test_broken_metadata_never_gives_confidence():
    r = ask("janssens", "How is the benefit in kind for a company car calculated?")
    assert r["confidence"] == "LOW"
    issues = service.document_details("be-company-car@v1")["quality_issues"]
    assert any("ISO" in i for i in issues) and any("directory" in i for i in issues)


def test_employee_category_picks_the_right_document_and_no_false_conflict():
    white = ask("janssens", "How long do we pay guaranteed salary during sickness?")
    blue = ask("maes", "How long do we pay guaranteed salary during sickness?")
    assert white["sources"][0]["doc_version_id"] == "be-sick-pay-white@v1"
    assert blue["sources"][0]["doc_version_id"] == "be-sick-pay-blue@v1"
    assert white["signals"]["consistency"]["status"] == "pass"


def test_country_without_documents_is_low():
    assert ask("muller", "How long do we pay guaranteed salary during sickness?")["confidence"] == "LOW"


def test_no_source_is_unknown():
    r = ask("janssens", "Can employees get a bicycle allowance?")
    assert r["confidence"] == "UNKNOWN" and r["sources"] == []


def test_owner_written_version_goes_live_and_old_one_is_superseded():
    service.resolve_task("be-holiday-pay@v1", "publish_new_version", "an-peeters",
                         {"title": "Double holiday pay (BE) 2026", "summary": "Updated 2026 rule.", "body": "Text."})
    r = ask("janssens", "How much double holiday pay do white-collar employees get?")
    assert r["sources"][0]["doc_version_id"] == "be-holiday-pay@v2"
    assert r["signals"]["freshness"]["status"] == "pass"
    kb = {row["doc_version_id"]: row["status"] for row in service.knowledge_base()}
    assert kb["be-holiday-pay@v1"] == "Superseded" and kb["be-holiday-pay@v2"] == "Live"
    assert service.published_versions()[0]["live"]
    store.reset()
    assert "be-holiday-pay@v2" not in {d["doc_version_id"] for d in store.load_all_versions()}


def test_future_validity_warns():
    doc = {"country": "BE", "valid_from": "2027-01-01"}
    assert trust.applicability(doc, {"country": "BE"}, date(2026, 9, 30))["status"] == "warn"


def test_quality_flags_future_review_and_bad_dates():
    doc = {"id": "x", "version": 1, "title": "t", "topic": "t", "authority": "note", "summary": "s",
           "country": "BE", "owner": None, "last_reviewed": "2030-01-01",
           "valid_from": "2026-01-01", "valid_until": "2025-01-01"}
    issues = quality.check(doc, {}, date(2026, 9, 30))
    assert "Review date is in the future" in issues and "valid_until is before valid_from" in issues
