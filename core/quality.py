"""Data-quality checks on document metadata. Pure function, used at ingestion and in the UI.

Bad metadata must never silently produce a confident answer: every issue here also shows up
as an 'unknown' or 'fail' trust signal.
"""
from datetime import date

REQUIRED = ["id", "version", "title", "topic", "authority", "summary"]
AUTHORITIES = {"approved_procedure", "note", "chat"}


def check(doc, people, today=None):
    """Return a list of human-readable issues (empty = clean)."""
    today = today or date.today()
    issues = [f"Missing field '{f}'" for f in REQUIRED if not doc.get(f)]
    country = doc.get("country")
    if country and not (isinstance(country, str) and len(country) == 2 and country.isupper()):
        issues.append(f"Country '{country}' is not a 2-letter ISO code")
    if doc.get("authority") and doc["authority"] not in AUTHORITIES:
        issues.append(f"Unknown authority '{doc['authority']}'")
    owner = doc.get("owner")
    if owner is None and doc.get("authority") != "chat":
        issues.append("No owner assigned")
    elif owner and owner not in people:
        issues.append(f"Owner '{owner}' is not in the people directory")
    elif owner and not people[owner]["active"]:
        issues.append(f"Owner {people[owner]['name']} has left the company")
    reviewed = doc.get("last_reviewed")
    if not reviewed and doc.get("published", True):
        issues.append("No review date")
    elif reviewed and date.fromisoformat(str(reviewed)) > today:
        issues.append("Review date is in the future")
    vf, vu = doc.get("valid_from"), doc.get("valid_until")
    if vf and vu and str(vu) < str(vf):
        issues.append("valid_until is before valid_from")
    return issues
