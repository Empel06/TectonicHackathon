# Trust Card Assistant: TecTonic Hackathon PoC

An assistant that tells payroll consultants not only **what** the answer is, but **why they can rely on it**.
It gets more reliable every time someone expresses doubt.
The full design is in [`docs/solution-design.md`](docs/solution-design.md). All data is **synthetic**.

## Run it with Docker (one command)

```bash
docker compose up --build     # then open http://localhost:8501
```

Sign in with a demo account (password `demo2026` for all): `sofie` (consultant), `eva-smit` (owner NL),
`an-peeters` (owner BE), `lotte-wouters` (owner BE social law), `bram-janssen` (owner NL healthcare),
`mark-de-vries` (expert NL), `sarah-dubois` (expert BE), `admin`. See [SECURITY.md](SECURITY.md) for the threat model.

**No API key needed.** Everything runs locally: retrieval, trust scoring, feedback and the owner inbox. Answers
are the cited source's own summary. Setting `ANTHROPIC_API_KEY` is only for a future step, where a language
model would phrase the answer from the same sources; the trust verdict stays rule-based either way.

Without compose: `docker build -t trust-card . && docker run --rm -p 8501:8501 trust-card`.
Run the tests in the container with `docker run --rm trust-card python -m pytest -q`.
Demo state lives inside the container, so a restart (or the **Reset** button) gives a clean demo.

## Run it locally (for development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run ui/app.py       # the demo
pytest -q                     # tests, including the full demo flow
```

## Demo script (about 3 minutes)

Sign in as `sofie` and click **Reset demo state** in the sidebar. Use customer **Van Dijk BV (NL)**.
To publish (step 4), sign out and sign in as `eva-smit`. To confirm (step 5), sign in as `mark-de-vries`.

1. **Ask** the prefilled question. On the left, the **existing system** confidently gives the *Belgian* rule: 40 wrong payslips.
2. On the right, the **Trust Card** shows 🔴 **LOW: "Source is for BE, customer is NL"** and suggests who to ask. Switch the customer to Janssens NV (BE): the same doc gets **HIGH**.
3. Back on NL, click **👎 Wrong country**. That is the 4th report, and the Belgian doc drops for NL questions *only*.
   The Dutch note now ranks first, but it is still **LOW**: 21 months old, and its owner has left.
4. Open **Owner inbox**. The Dutch note was routed to Eva Smit because its owner left. Click **Publish nl-13th-month@v2**.
   Ask again: **MEDIUM, "New version, published after 2 reports; not yet validated."**
5. Sign in as **mark-de-vries (expert)**, ask, and click **Confirm as expert**. The card goes to **HIGH**.
   *Feedback may create doubt automatically, but only people can create certainty.*

`tests/test_demo_flow.py` asserts exactly this script. If it passes, the demo works.

## Demo companies and their problems

Each customer has a sector, a profile and its own typical questions (shown in the sidebar). The **Scenario**
dropdown on the Ask tab groups 24 prepared cases by company; any other question can be typed freely, in English,
Dutch or French.

| Company | Profile | Typical questions and what the card shows |
|---|---|---|
| Van Dijk BV (NL, retail, 40) | Part-timers, students | 13th month (LOW: Belgian source) · holiday allowance (LOW: popular chat) · youth minimum wage (MEDIUM: valid H2 2026 only) · transition payment (MEDIUM: contradiction) |
| Janssens NV (BE, PC 200, IT, white-collar, 25) | Company cars, home working | Meal vouchers (HIGH, expert-validated) · eco-cheques (MEDIUM, new) · telework (LOW: expired) · company car (LOW: broken metadata) · bicycle (UNKNOWN) |
| Bouwbedrijf Maes (BE, PC 124, construction, blue-collar, 60) | Site workers, sector fund | Year-end premium (paid by the fund) · mobility allowance (HIGH) · bad weather (LOW: stale, reported incomplete) · Belgian PC 200 bonus rule (LOW: wrong joint committee) |
| Brasserie De Kaai (BE, PC 302, hospitality, 18) | Flexi-jobs, students, tips | Flexi-job (HIGH) · student hours (MEDIUM: 2026 rule; the 2027 announcement and an outdated chat do not override it) · tips (LOW: 2024 note, owner left) |
| Zorggroep Oost (NL, CAO VVT, healthcare, 340) | Shifts, nights, weekends | ORT allowance (MEDIUM: new version after reports; the 2024 table is superseded) · sick pay 104 weeks (HIGH) · the same ORT question in Dutch |
| Müller GmbH (DE, manufacturing, 120) | New country | Every answer is LOW: no German source exists |

The knowledge base has **27 synthetic documents** from SharePoint, Confluence, Teams and a legacy knowledge base,
including a superseded version, an announced future rule, outdated notes, ownerless pages and popular-but-wrong chats.

> After pulling new data, click **Reset demo state** once. The event log lives on a Docker volume, so the new seed
> history only loads after a reset (or run `docker compose down -v`).

## Test scenarios (edge cases)

Pick one from the **Scenario** dropdown on the Ask tab; it sets the customer and the question.

| Scenario | Customer | Expected card | What it proves |
|---|---|---|---|
| Hero: Belgian rule for a Dutch customer | Van Dijk BV (NL) | LOW: source is for BE | Country applicability |
| Same question, construction company | Bouwbedrijf Maes (BE, PC 124, blue-collar) | LOW: source is for PC200 | Joint-committee applicability |
| 2025 telework allowance asked in 2026 | Janssens NV (BE, PC 200) | LOW: expired on 2025-12-31 | Validity period |
| NL transition payment | Van Dijk BV | MEDIUM: contradicted by the 2018 procedure | Conflict detection between official sources |
| 6% holiday allowance chat with 3 upvotes | Van Dijk BV | LOW: chat message | Popularity is not correctness (ceiling rule) |
| Company car page with broken metadata | Janssens NV | LOW, plus 4 data-quality issues | Wrong data never produces confidence |
| Sickness guaranteed salary | Janssens NV vs Bouwbedrijf Maes | Each gets its own category's document | Employee-category applicability |
| Any question for a German customer | Müller GmbH (DE) | LOW: source is for BE | No coverage for a country |
| Bicycle allowance | Janssens NV | UNKNOWN | No source at all: nothing is invented |

`tests/test_edge_cases.py` asserts every row.

## Checking the sources yourself

Every source the assistant used can be opened, so an employee never has to take the card's word for it.
- **Clickable citations:** `[1]` in the answer and every source title open that source in a new tab.
- **Source page** (`?doc=<doc_version_id>`, for example `?doc=chat-nl-holiday-allowance%40v1`) shows:
  - where the source lives (SharePoint, Confluence, Teams or the legacy knowledge base) and its path;
  - the content as it looks in that system, with **Teams chats rendered as the full thread** (authors, times, likes, and replies such as the colleague who doubted the 6%);
  - a **download** of that exact version;
  - trust details, feedback history and all other versions.
- **Exact versions:** links point to the version the answer used. A superseded version still opens, with a notice linking to the live one.
- A document without a source location is flagged as a data-quality issue.

The locations are synthetic. In production each link goes straight to the SharePoint file, Confluence page or Teams message.

## Where a published version goes

Owners write the corrected text in **Owner inbox → Write and publish a corrected version**. Publishing appends a
`publish` event, including the full document, to the event log. From that moment:
- the new version is **live**: every new answer uses it, and it starts with fresh reputation;
- the old version stays in the **Knowledge base** as **Superseded**, with its reports attached (audit trail);
- the task is resolved, and the version appears under **Published versions** in the inbox;
- **Reset demo state** removes it again, because it exists only in the event log.

## Code map

| Path | What | Owner |
|---|---|---|
| `data/docs/*.md` | Synthetic corpus: YAML front matter (country, owner, authority, last_reviewed, claim) plus body. `published: false` means staged, not yet live. | A |
| `data/seed_events.jsonl` | Seeded feedback history. `data/events.jsonl` is the live log (gitignored, recreated by Reset). | A |
| `core/retrieval.py` | Deterministic keyword ranking with a per-context penalty | A |
| `core/reputation.py` | Beta-Bernoulli reputation, `wrong_context` flags and penalty | A |
| `core/trust.py` | Six signals plus confidence policy v1 (applicability = country, validity dates, joint committee, employee category) | A |
| `core/quality.py` | Data-quality checks on document metadata | A |
| `app/service.py` | **The contract** the UI calls: `ask`, `add_feedback`, `owner_tasks`, `resolve_task`, `reset` | C |
| `app/store.py` | Docs loader and the append-only event log | C |
| `app/llm.py` | Answer composer (template, with an optional hook for Claude) | C |
| `app/auth.py`, `app/privacy.py` | Login (hashed passwords, lockout) and personal-data redaction | C |
| `config/policy.yaml`, `core/policy.py` | Versioned trust policy: every threshold | A |
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

## Security and governance

- **Login** with hashed passwords and a lockout; people who left the company are refused.
- **Permissions enforced in the service layer**: only the routed owner publishes, only experts give expert verdicts.
- **Rate limit** on feedback, and **personal data redacted** from comments before storage.
- **Audit log tab**: a hash-chained event log that detects tampering. Try *Simulate tampering*.
- **Trust policy tab**: every threshold comes from the versioned `config/policy.yaml`.
- **Hardened container**: non-root user, read-only filesystem, no Linux capabilities, localhost-only port.
- **Dutch and French questions** are mapped to the corpus vocabulary ("vakantiegeld", "eindejaarspremie", "salaire garanti").

Details: [SECURITY.md](SECURITY.md).

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
