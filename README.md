# procurement-decision-sentinel

An always-on procurement decision engine. Agents watch commodity, tariff and supplier-risk news. Each article is
checked, resolved to the buyer's own suppliers, and walked through a spend and contract knowledge graph to the
categories it touches. A card appears only when the money is material; it shows the path, the quotes and a playbook
lever. A manager accepts or dismisses it, and the dismissals are remembered.

The model reads; code decides. The model returns what an article says, with quotes. Code decides everything else:
- whether each claim is backed by a quote;
- whether the news is confirmed;
- which supplier it means (a name never decides);
- how much money is at stake through which contract;
- whether that clears the materiality floor;
- which lever to propose.

![The console: a tariff on a sub-supplier's input becomes a card for ocean freight](docs/screenshots/console.png)

## Results

Every design reads the same simulated feed (about 230 articles a week) and meets the same luck. The truth stays in the
world and only the evaluation reads it. Value captured is the share of mitigable money that people acted on in time,
with the right lever.

<!-- results:start -->

_Generated from `reports/*.json` by `python -m sentinel.cli report`._

**Development seeds** (dev world, seeds [11, 12, 13])

| Design | Value captured | vs status quo, pts [95% CI] | Cards / week | Cards that mattered | People, min / week | Signal to decision (median) | Duplicate cards | Model cost / week |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Analyst reads the feed + monthly review | 72.4% | baseline | 76.1 | 32.5% | 915 | 20.1 h | 0 | EUR 0.000 |
| Model reads the feed and names categories | 51.2% | -21.2 [-29.4, -14.3] | 153.1 | 16.5% | 970 | 93.9 h | 1049 | EUR 0.354 |
| Sentinel (model reads, graph and code decide) | 85.7% | +13.3 [+7.0, +21.6] | 27.9 | 93.3% | 357 | 17.4 h | 0 | EUR 0.179 |

Gates: all 9 pass. Model swap: Sentinel on the smaller model: passes.

**Held-out seeds, run once** (heldout world, seeds [101, 102])

| Design | Value captured | vs status quo, pts [95% CI] | Cards / week | Cards that mattered | People, min / week | Signal to decision (median) | Duplicate cards | Model cost / week |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Analyst reads the feed + monthly review | 73.8% | baseline | 72.3 | 35.4% | 907 | 21.7 h | 0 | EUR 0.000 |
| Model reads the feed and names categories | 51.8% | -22.0 [-29.8, -14.5] | 153.2 | 16.8% | 966 | 113.2 h | 654 | EUR 0.376 |
| Sentinel (model reads, graph and code decide) | 83.5% | +9.8 [+6.0, +13.8] | 29.4 | 91.5% | 358 | 17.6 h | 1 | EUR 0.190 |

Gates: FAILED: Duplicate cards. Model swap: Sentinel on the smaller model: passes.

<!-- results:end -->

The full tables are in [REPORT.md](REPORT.md):
- false cards by cause;
- each switch turned off on its own;
- value by signal type;
- sample cards with their trace.

## How it works

```
article ──> copy check ──> model reads (forced tool, strict schema) ──> quotes checked against the article
        ──> status from the words ──> supplier resolved on stem + legal form + quoted country
        ──> same-facts merge ──> graph walk to EUR a year per category ──> materiality floor ──> dismissal memory
        ──> card (path, quotes, lever) ──> manager decides ──> memory learns
```

| Part | File | What it does |
|---|---|---|
| Readers | `platform/readers.py` | Claude through the Messages API with a forced tool and a cached system prompt; any OpenAI-compatible endpoint with a JSON schema. Plain httpx, so tests replace the transport. |
| Checks | `platform/evidence.py` | A field counts only if a copied quote backs it; for a price move the verb before the number must match the sign; status comes from the words; instruction-like quotes are never evidence. |
| Resolution | `platform/resolve.py` | Stem, legal form and a quoted country. A name alone goes to a person. |
| Knowledge graph | `platform/graph.py` | Typed nodes and edges over spend, suppliers, contracts, commodities, countries and disclosed tier-2 links; each exposure keeps its path. |
| Playbook | `platform/playbook.py`, `config/platform.yml` | The codified sourcing playbook: first matching rule gives the lever. |
| Workflow | `platform/pipeline.py`, `platform/journal.py` | One message, one durable workflow: journaled steps, at-least-once delivery, one card per message and category. |
| Memory | `platform/memory.py` | A "within tolerance" dismissal stops the same card until the money grows. |
| Service | `service/api.py`, `service/store.py` | FastAPI over SQLite: signals in once, cards largest money first, decisions kept once, holds, a what-if walk, the graph. |
| Console | `web/` | React, Vite, Framer Motion; feature folders, theme tokens, light and dark, loading, error and empty states. |

## The designs

- **Status quo:** an analyst skims every headline, reads the relevant ones, and flags categories to managers.
- **Model alone:** the model reads each article with the category and supplier lists and names the categories; every
  named category becomes a card.
- **Sentinel:** the design above.
- **Ablations:** the sentinel with one part off: tier-2 links, the quote check, strict supplier resolution, the
  rumour hold, dismissal memory, the workflow journal, or the copy check.
- **Model swap:** the sentinel on a smaller model, with its own release gate.

The monthly category review runs in every design. Managers review cards once a day with 24 minutes each; the sentinel
orders their queue by money, the others by arrival.

## Run it

```bash
pip install -e ".[dev]"
pytest -q                                   # about 5 s
python -m sentinel.cli run dev              # every design on the development seeds, about 15 s
python -m sentinel.cli gate dev             # exit 1 if a gate fails
python -m sentinel.cli report               # REPORT.md, this README's block, web/public/data/report.json
python -m sentinel.cli serve                # the API on a simulated feed (first 3 days loaded), port 8000
cd web && npm ci && npm run dev             # the console
```

With a real model:

```python
from sentinel import config
from sentinel.platform.readers import AnthropicReader
from sentinel.service.api import create_app
from sentinel.service.store import Store

app = create_app(master_data, config.platform(), AnthropicReader(api_key, "<model id>"), "model_a", Store("sentinel.db"))
```

Build `master_data` from the spend cube, supplier master, contract repository and supplier disclosures (`domain.MasterData`).

## Reading the held-out run

The held-out world differs on purpose:
- a tariff wave of 10 announcements on one day;
- more namesakes (50% of suppliers have one);
- twice the injections;
- more rumours.

The seeds ran once, behind `reports/heldout.lock`, after the gates were set. ADR 0009 records what came out.

## Limits

- **Everything is simulated.** The buyer, suppliers, prices, articles and the model's mistakes come from
  `config/world.yml`. The numbers show how the designs compare under these assumptions, not what a real buyer would
  save.
- **Articles are templated.** Real news is longer and messier, so the quote check will hold more real articles for a
  person than it does here. Measure that hold rate first on a real feed.
- **The simulated model's mistakes are chosen, not measured.** It mislabels status, gets numbers and signs wrong,
  drops legal forms and obeys some injections. Real error rates have to be measured on labelled articles before any
  gate means anything.
- **Managers are simulated.** They judge cards against the truth with fixed error rates, and their tolerance is a
  hidden number per category. Real dismissals carry reasons this model does not have.
- **Value is an accounting device:** mitigable share × linear decay × a lever factor. It ranks designs; it is not a
  forecast of savings.
- **Not covered:** hedging positions, inventory, multi-currency, sub-tier links nobody disclosed, ESG scoring beyond a
  flag, and live market data feeds. There is no message broker; the at-least-once broker is simulated in virtual
  time, and the service takes HTTP posts.
- **Model cost is tiny here, about €0.18 a week.** The expensive part of alerting is people's time, which is why the
  gates look at minutes and the share of cards that mattered.

## Repository map

`AGENTS.md` (invariants and the held-out rule), `CLAUDE.md`, `SKILLS.md` (repeatable tasks), `docs/adr/` (decisions),
`config/` (all settings), `reports/` (generated), `REPORT.md` (generated), `web/` (console), `scripts/screenshots.py`.

## Licence

MIT.
