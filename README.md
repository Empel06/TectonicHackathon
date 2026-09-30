# Trust Card Assistant: TecTonic Hackathon PoC

An assistant that tells payroll consultants not only **what** the answer is, but **why they can rely on it**.
It gets more reliable every time someone expresses doubt.
The full design is in [`docs/solution-design.md`](docs/solution-design.md). All data is **synthetic**.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run ui/app.py       # the demo
pytest -q                     # tests, including the full demo flow
```

## Demo script (about 3 minutes)

Before each run, click **Reset demo state** in the sidebar. Use customer **Van Dijk BV (NL)** and sign in as **Sofie (consultant)**.

1. **Ask** the prefilled question. On the left, the **existing system** confidently gives the *Belgian* rule: 40 wrong payslips.
2. On the right, the **Trust Card** shows 🔴 **LOW: "Source is for BE, customer is NL"** and suggests who to ask. Switch the customer to Janssens NV (BE): the same doc gets **HIGH**.
3. Back on NL, click **👎 Wrong country**. That is the 4th report, and the Belgian doc drops for NL questions *only*.
   The Dutch note now ranks first, but it is still **LOW**: 21 months old, and its owner has left.
4. Open **Owner inbox**. The Dutch note was routed to Eva Smit because its owner left. Click **Publish nl-13th-month@v2**.
   Ask again: **MEDIUM, "New version, published after 2 reports; not yet validated."**
5. Sign in as **Mark de Vries (expert)**, ask, and click **Expert: confirm**. The card goes to **HIGH**.
   *Feedback may create doubt automatically, but only people can create certainty.*

`tests/test_demo_flow.py` asserts exactly this script. If it passes, the demo works.

## Code map

| Path | What | Owner |
|---|---|---|
| `data/docs/*.md` | Synthetic corpus: YAML front matter (country, owner, authority, last_reviewed, claim) plus body. `published: false` means staged, not yet live. | A |
| `data/seed_events.jsonl` | Seeded feedback history. `data/events.jsonl` is the live log (gitignored, recreated by Reset). | A |
| `core/retrieval.py` | Deterministic keyword ranking with a per-context penalty | A |
| `core/reputation.py` | Beta-Bernoulli reputation, `wrong_context` flags and penalty | A |
| `core/trust.py` | Six signals plus confidence policy v1 | A |
| `app/service.py` | **The contract** the UI calls: `ask`, `add_feedback`, `owner_tasks`, `resolve_task`, `reset` | C |
| `app/store.py` | Docs loader and the append-only event log | C |
| `app/llm.py` | Answer composer (template, with an optional hook for Claude) | C |
| `ui/app.py` | Streamlit UI: side-by-side answers, Trust Card, feedback, owner inbox | B |
| `tests/` | Unit tests for the core, plus the demo-flow test | all |

### Contract: `service.ask(question, context, mode, user_id)`

```json
{
  "answer_id": "ans-1a2b3c4d", "mode": "trust", "question": "...", "context": {"country": "NL", "cla": null},
  "answer": "... [1]", "llm_status": "template",
  "confidence": "LOW", "confidence_reason": "Source is for BE, customer is NL",
  "signals": {"freshness": {"status": "pass", "reason": "..."}, "ownership": {}, "authority": {},
              "applicability": {}, "consistency": {}, "validation": {}},
  "sources": [{"ref": 1, "doc_id": "be-eoy-bonus", "doc_version_id": "be-eoy-bonus@v1", "version": 1,
               "title": "...", "country": "BE", "authority": "approved_procedure",
               "relevance": 1.0, "context_penalty": 0.3, "score": 0.7,
               "reputation": {"value": 0.8, "effective_n": 6, "summary": "3 × Wrong country / context"}}],
  "experts": [{"id": "mark-de-vries", "name": "Mark de Vries", "reason": "..."}],
  "trust_policy_version": 1
}
```
In `baseline` mode, `confidence`, `signals` and `experts` are `null`.

## Key design decisions (PoC)

- **No fine-tuning and no black box.** Feedback changes document reputation and ranking, and routes problems to the owner, who fixes the source.
- **`wrong_context` does not hurt reputation.** It only demotes the document *for that country*, by 10% per flag, capped at 50%. The doc may be perfectly right elsewhere.
- **Ceiling rule.** Any failing signal means LOW, whatever the votes. HIGH requires positive validation.
- **Deterministic by design.** There is no vector DB and no LLM in the scoring path, so the demo behaves the same every time.

## Team plan (deadline 22:30)

| Time | Checkpoint |
|---|---|
| 19:45 | Everyone runs this branch locally. Branches: `feature/core` (A), `feature/ui` (B), `feature/app` (C). |
| 20:30 | Merge to `main`, with improvements on each part. |
| 21:15 | The full loop is polished. Optional: second scenario, Claude-written answers. |
| **21:45** | **Feature freeze.** Bug fixes only; `pytest` must stay green. |
| 22:00 | Two rehearsals and a backup screen recording. |
| 22:20 | Final merge to `main` and push. |
