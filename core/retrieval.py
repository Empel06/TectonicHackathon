"""Tiny deterministic keyword retrieval over the synthetic corpus.

No vector DB on purpose: the corpus is ~6 documents and ranking must only change
because of feedback, never because of randomness.
"""
import re

from core.policy import POLICY

# Consultants ask in Dutch, French or English. Payroll terms are mapped to the corpus vocabulary
# before matching, longest phrase first, so "vakantiegeld" finds the holiday-allowance procedure.
SYNONYMS = {
    "dertiende maand": "13th month", "13de maand": "13th month", "13e maand": "13th month",
    "treizième mois": "13th month", "13e mois": "13th month",
    "eindejaarspremie": "end-of-year bonus", "eindejaarsuitkering": "end-of-year bonus",
    "prime de fin d'année": "end-of-year bonus", "prime de fin d’année": "end-of-year bonus",
    "vakantiegeld": "holiday allowance vakantiegeld", "dubbel vakantiegeld": "double holiday pay",
    "pécule de vacances": "holiday pay", "double pécule": "double holiday pay",
    "deeltijdse": "part-time", "deeltijds": "part-time", "deeltijders": "part-time employees",
    "à temps partiel": "part-time", "temps partiel": "part-time",
    "werknemers": "employees", "werknemer": "employee", "travailleurs": "employees", "employés": "employees",
    "bedienden": "white-collar employees", "arbeiders": "blue-collar workers",
    "gewaarborgd loon": "guaranteed salary", "salaire garanti": "guaranteed salary",
    "ziekte": "sickness", "maladie": "sickness",
    "transitievergoeding": "transition payment transitievergoeding", "ontslag": "dismissal", "licenciement": "dismissal",
    "bedrijfswagen": "company car", "voiture de société": "company car", "voordeel alle aard": "benefit in kind",
    "telewerkvergoeding": "telework allowance", "thuiswerkvergoeding": "telework allowance", "télétravail": "telework",
    "bouwsector": "construction", "bouw": "construction", "construction": "construction",
    "pro rata": "pro-rata", "prorata": "pro-rata", "au prorata": "pro-rata",
    "december": "december", "décembre": "december",
    "maaltijdcheques": "meal vouchers", "maaltijdcheque": "meal voucher", "chèques-repas": "meal vouchers",
    "ecocheques": "eco-cheques", "éco-chèques": "eco-cheques",
    "mobiliteitsvergoeding": "mobility allowance", "slecht weer": "bad weather", "intempéries": "bad weather",
    "tijdelijke werkloosheid": "temporary unemployment", "chômage temporaire": "temporary unemployment",
    "flexijob": "flexi-job", "flexi-jobs": "flexi-job", "hoofdjob": "main job",
    "jobstudent": "student work", "studentenarbeid": "student work", "studentenuren": "student hours",
    "job étudiant": "student work", "étudiant": "student",
    "minimumjeugdloon": "minimum youth wage", "jeugdloon": "youth wage", "minimumloon": "minimum wage",
    "loondoorbetaling bij ziekte": "continued salary payment during sickness", "loondoorbetaling": "continued salary payment",
    "onregelmatigheidstoeslag": "irregular hours allowance ort", "ort": "irregular hours allowance ort",
    "nachtdienst": "night", "weekenddienst": "weekend", "feestdag": "public holiday",
    "fooien": "tips", "fooi": "tips", "pourboires": "tips",
}
_SYNONYM_RE = re.compile("|".join(re.escape(k) for k in sorted(SYNONYMS, key=len, reverse=True)))


def normalize(question):
    """Map Dutch/French payroll terms onto the corpus vocabulary (deterministic, no model)."""
    return _SYNONYM_RE.sub(lambda m: SYNONYMS[m.group(0)], (question or "").lower())


STOPWORDS = {
    # English question words: they say what kind of answer is wanted, not what it is about
    "many", "much", "long", "when", "where", "why", "often", "does", "will", "would", "there", "my",
    # Dutch / French question words, so they do not dilute the match
    "krijgen", "onze", "een", "de", "het", "van", "voor", "hoeveel", "wat", "zijn", "moeten", "wij", "wie",
    "betalen", "hoe", "lang", "le", "la", "les", "des", "du", "nos", "est", "ce", "que", "qui", "combien",
    "ont", "ils", "droit", "une", "un", "pour", "en", "op", "bij", "is", "er", "welke", "dat", "die",
    "a", "an", "the", "do", "does", "did", "our", "we", "you", "your", "is", "are", "to", "of",
    "for", "in", "on", "and", "or", "get", "gets", "what", "how", "when", "can", "should", "with",
    "it", "be", "their", "they", "this", "that", "there", "which", "who", "any", "by", "at",
}


# Irregular forms that suffix stripping cannot catch ("paid" must find "payment").
IRREGULAR = {"paid": "pay", "pays": "pay", "payout": "pay", "uitbetaald": "pay", "betaald": "pay", "payé": "pay",
             "got": "get", "gets": "get", "gotten": "get", "entitled": "entitle", "entitlement": "entitle",
             "children": "child", "men": "man", "women": "woman", "sick": "sickness", "ill": "sickness",
             "holidays": "holiday", "vacation": "holiday", "leave": "holiday"}
SUFFIXES = ("ments", "ment", "ings", "ing", "ies", "ied", "ed", "es", "s")


def stem(word):
    """Light, deterministic stemming: irregular forms, common English suffixes, then a 5-letter prefix.

    payment/payments/paying/paid -> "pay"; employee/employees/employment -> "emplo".
    """
    word = IRREGULAR.get(word, word)
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)] + ("y" if suffix in ("ies", "ied") else "")
            break
    return word[:5]


def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {stem(w) for w in words if w not in STOPWORDS and len(w) > 1}


# words that appear in almost every payroll document: they count for relevance,
# but a match on these alone is not enough to call a document relevant
GENERIC = {"emplo", "worke", "staff", "payro", "custo", "salar", "allow"}
MIN_SPECIFIC_MATCHES = 2


def relevance(question, doc):
    q = tokens(normalize(question))
    if not q:
        return 0.0
    d = tokens(" ".join([doc.get("title", ""), doc.get("summary", ""), doc.get("body", "")]))
    # a short question ("bonus", "when is the bonus paid?") may match on fewer specific words
    needed = min(MIN_SPECIFIC_MATCHES, len(q - GENERIC))
    if needed == 0 or len((q & d) - GENERIC) < needed:
        return 0.0
    return len(q & d) / len(q)


def rank(question, docs, penalties=None, min_score=POLICY["ranking"]["min_relevance"], top_k=3):
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
