"""Who may use or see which source. Enforced in the service layer for answers, source pages and lists.

Model (mirrors how a payroll provider separates customer data):
- classification: public | internal (default) | confidential | restricted
- customer_id: a customer-specific source (contract, local agreement) is only used for THAT customer's
  questions, and only by people whose portfolio contains that customer (no cross-customer leakage)
- quarantine: a source that contains personal data (national number, IBAN, ...) or is marked restricted
  is never used in answers; only an admin can open it, and then with the personal data masked
"""
from app import privacy

CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"]


def portfolio(person, customers):
    """Customer ids this person may work on."""
    if not person or not person.get("active"):
        return []
    if person["role"] == "admin":
        return list(customers)
    if person["role"] in ("owner", "expert"):
        return [cid for cid, c in customers.items() if c["country"] in person.get("topics", [])]
    return [cid for cid in person.get("customers", []) if cid in customers]


def personal_data_found(doc):
    text = " ".join([doc.get("title") or "", doc.get("summary") or "", doc.get("body") or ""]
                    + [m.get("text", "") for m in doc.get("messages") or []])
    return privacy.find_personal_data(text)


def quarantined(doc):
    return doc.get("classification") == "restricted" or bool(personal_data_found(doc))


def can_use(doc, person, customers, context_customer_id):
    """May this source feed an answer for this person and this customer?"""
    if quarantined(doc):
        return False
    cid = doc.get("customer_id")
    if cid:
        return cid == context_customer_id and cid in portfolio(person, customers)
    return True


def can_view(doc, person, customers):
    """May this person open the source page?"""
    if not person or not person.get("active"):
        return False
    if quarantined(doc):
        return person["role"] == "admin"
    cid = doc.get("customer_id")
    return not cid or cid in portfolio(person, customers)
