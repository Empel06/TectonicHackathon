"""Tiny deterministic keyword retrieval over the synthetic corpus.

No vector DB on purpose: the corpus is ~6 documents and ranking must only change
because of feedback, never because of randomness.
"""
import re

STOPWORDS = {
    "a", "an", "the", "do", "does", "did", "our", "we", "you", "your", "is", "are", "to", "of",
    "for", "in", "on", "and", "or", "get", "gets", "what", "how", "when", "can", "should", "with",
    "it", "be", "their", "they", "this", "that", "there", "which", "who", "any", "by", "at",
}


def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    # crude stemming: 5-char prefix makes employee/employees/employment match
    return {w[:5] for w in words if w not in STOPWORDS and len(w) > 1}


# words that appear in almost every payroll document: they count for relevance,
# but a match on these alone is not enough to call a document relevant
GENERIC = {"emplo", "worke", "staff", "payro", "custo", "salar", "allow"}
MIN_SPECIFIC_MATCHES = 2


def relevance(question, doc):
    q = tokens(question)
    if not q:
        return 0.0
    d = tokens(" ".join([doc.get("title", ""), doc.get("summary", ""), doc.get("body", "")]))
    if len((q & d) - GENERIC) < MIN_SPECIFIC_MATCHES:
        return 0.0
    return len(q & d) / len(q)


def rank(question, docs, penalties=None, min_score=0.3, top_k=3):
    """Return [{"doc", "relevance", "penalty", "score"}] best first.

    penalties: {doc_version_id: context_penalty} (0..0.5)
    """
    penalties = penalties or {}
    hits = []
    for doc in docs:
        rel = relevance(question, doc)
        if rel < min_score:
            continue
        pen = penalties.get(doc["doc_version_id"], 0.0)
        hits.append({"doc": doc, "relevance": round(rel, 3), "penalty": pen,
                     "score": round(rel * (1 - pen), 3)})
    hits.sort(key=lambda h: (-h["score"], h["doc"]["doc_version_id"]))
    return hits[:top_k]
