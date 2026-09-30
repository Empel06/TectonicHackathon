"""Answer composer. The LLM only writes the sentence; it never decides confidence.

Default is a deterministic template so the demo never depends on network or credits.
TODO (optional, only if ahead of schedule): call Claude here when LLM_MODE=live,
with a timeout and fall back to the template on any error.
"""


def compose_answer(question, context, hits):
    """Return (answer_text, llm_status). hits = core.retrieval.rank() output."""
    if not hits:
        return "I could not find a source that answers this question.", "template"
    top = hits[0]["doc"]
    return f"{top['summary']} [1]", "template"
