# Demo scenarios and data

All companies, people, documents and feedback in this repository are **synthetic**. The payroll rules are plausible
but have not been verified by a payroll expert.

## Demo companies and their problems

Each customer has a sector, a profile and its own typical questions (shown in the sidebar). The **Scenario**
dropdown on the Ask tab groups 27 prepared cases by company; any other question can be typed freely, in English,
Dutch or French.

| Company | Profile | Typical questions and what the card shows |
|---|---|---|
| Van Dijk BV (NL, retail, 40) | Part-timers, students | 13th month (LOW: Belgian source) · holiday allowance: the official source wins a neutral question; checking the chat's "6%" claim gives LOW · youth minimum wage (MEDIUM: valid H2 2026 only) · transition payment (MEDIUM: contradiction) |
| Janssens NV (BE, PC 200, IT, white-collar, 25) | Company cars, home working | Meal vouchers (HIGH, expert-validated) · eco-cheques (MEDIUM, new) · telework (LOW: expired) · company car (LOW: broken metadata) · bicycle (UNKNOWN) |
| Bouwbedrijf Maes (BE, PC 124, construction, blue-collar, 60) | Site workers, sector fund | Year-end premium (paid by the fund) · mobility allowance (HIGH) · bad weather (LOW: stale, reported incomplete) · Belgian PC 200 bonus rule (LOW: wrong joint committee) |
| Brasserie De Kaai (BE, PC 302, hospitality, 18) | Flexi-jobs, students, tips | Flexi-job (HIGH) · student hours (MEDIUM: 2026 rule; the 2027 announcement and an outdated chat do not override it) · tips (LOW: 2024 note, owner left) |
| Zorggroep Oost (NL, CAO VVT, healthcare, 340) | Shifts, nights, weekends | ORT allowance (MEDIUM: new version after reports; the 2024 table is superseded) · sick pay 104 weeks (HIGH) · the same ORT question in Dutch |
| Müller GmbH (DE, manufacturing, 120) | New country | Every answer is LOW: no German source exists |

The knowledge base has **30 synthetic sources** from SharePoint, Confluence, Teams, customer files and a legacy knowledge base,
including a superseded version, an announced future rule, outdated notes, ownerless pages, popular-but-wrong chats, two confidential customer files and one chat quarantined for containing personal data.

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

