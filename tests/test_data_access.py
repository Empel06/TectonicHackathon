"""Customer data separation, quarantine of personal data and access-checked source pages."""
import pytest

from app import service, store


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVENTS", tmp_path / "events.jsonl")
    store.reset()


def ctx(customer_id):
    c = store.load_customers()[customer_id]
    return {"customer_id": customer_id, "country": c["country"], "cla": c["cla"],
            "employee_category": c["employee_category"]}


CAR = "Which functions are entitled to a company car and fuel card?"
NIGHT = "Is there an extra night premium from the local agreement?"


def test_consultant_only_sees_own_portfolio():
    assert "zorggroep-oost" not in service.customers_for("sofie")
    assert "janssens" in service.customers_for("sofie")
    assert "zorggroep-oost" in service.customers_for("bram-janssen")  # NL owner
    assert len(service.customers_for("admin")) == len(store.load_customers())


def test_customer_document_is_used_for_that_customer_only():
    own = service.ask(CAR, ctx("janssens"), user_id="sofie")
    other = service.ask(CAR, ctx("maes"), user_id="sofie")
    assert own["sources"][0]["doc_version_id"] == "cust-janssens-car-policy@v1"
    assert "cust-janssens-car-policy@v1" not in [s["doc_version_id"] for s in other["sources"]]


def test_customer_outside_portfolio_gets_nothing_from_its_confidential_file():
    with pytest.raises(service.PermissionDenied):  # not even an answer for a customer outside the portfolio
        service.ask(NIGHT, ctx("zorggroep-oost"), user_id="sofie")
    r = service.ask(NIGHT, ctx("zorggroep-oost"), user_id="bram-janssen")
    assert r["sources"][0]["doc_version_id"] == "cust-zorggroep-local-agreement@v1"


def test_direct_link_to_other_customers_source_is_denied_and_logged():
    with pytest.raises(service.PermissionDenied):
        service.document_details("cust-zorggroep-local-agreement@v1", "sofie")
    assert store.read_events("access_denied")[-1]["user_id"] == "sofie"


def test_source_with_personal_data_is_quarantined():
    r = service.ask("How long do we pay guaranteed salary during sickness?", ctx("janssens"), user_id="sofie")
    assert "chat-pii-leak@v1" not in [s["doc_version_id"] for s in r["sources"]]
    with pytest.raises(service.PermissionDenied):
        service.document_details("chat-pii-leak@v1", "sofie")
    admin_view = service.document_details("chat-pii-leak@v1", "admin")
    assert "85.07.30-033.28" not in admin_view["body"] and admin_view["quarantine"]
    kb = {r["doc_version_id"]: r["status"] for r in service.knowledge_base("admin")}
    assert kb["chat-pii-leak@v1"] == "Quarantined"


def test_knowledge_base_hides_other_customers_documents():
    ids = {r["doc_version_id"] for r in service.knowledge_base("sofie")}
    assert "cust-janssens-car-policy@v1" in ids and "cust-zorggroep-local-agreement@v1" not in ids


def test_link_tokens_are_signed_and_expire():
    from app import auth
    token = service.link_token("sofie")
    assert service.login_from_link(token) == "sofie"
    person, expires, sig = token.rsplit(".", 2)
    assert service.login_from_link(f"admin.{expires}.{sig}") is None          # tampered user
    assert auth.verify_link_token(token, now=int(expires) + 1) is None        # expired
    assert service.login_from_link("garbage") is None
