"""Redacts personal data from free-text feedback BEFORE it is stored.

Comments are read by document owners; they must never become a copy of customer or employee data.
"""
import re

MAX_COMMENT = 500
PATTERNS = [
    ("[national number removed]", re.compile(r"\b\d{2}[.\s]?\d{2}[.\s]?\d{2}[-\s]?\d{3}[.\s]?\d{2}\b")),  # BE rijksregisternummer
    ("[IBAN removed]", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")),
    ("[email removed]", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("[phone removed]", re.compile(r"(?<!\w)(?:\+|00)\d{2}[\s./-]?\d{1,3}(?:[\s./-]?\d{2,3}){3}\b|\b0\d{1,3}(?:[\s./-]?\d{2,3}){3}\b")),
    ("[BSN removed]", re.compile(r"\b\d{9}\b")),  # NL burgerservicenummer
]


def redact(text):
    if not text:
        return text
    text = text[:MAX_COMMENT]
    for label, pattern in PATTERNS:
        text = pattern.sub(label, text)
    return text
