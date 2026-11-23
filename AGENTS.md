# Working on this repository

## Fast feedback

- `pytest -q` runs in about 5 s: hand-made master data, scripted readers, an in-memory SQLite store, one small seed.
- `ruff check . && ruff format --check . && mypy src` for lint and types.
- `python -m sentinel.cli run dev && python -m sentinel.cli gate dev && python -m sentinel.cli report` runs every
  design on the development seeds (about 15 s) and regenerates REPORT.md, the README block and the console data.
- `cd web && npm test && npm run typecheck && npm run lint` for the console.

## Invariants

Each one has a test or a CI step.

- **The truth stays in the world.**
  - What the sentinel gets: master data (spend, suppliers, contracts, should-cost weight estimates, the tier-2 links
    suppliers disclosed) and the articles.
  - What only the simulation and the evaluation (`sim/`, `lab/study.py`) may read: true weights, every tier-2 link,
    each category's tolerance, which alternates have capacity, which rumours come true, namesakes and injections.
  - Test: `tests/test_boundaries.py`.
- **The world does not read the sentinel's settings.**
  - `world/` loads `world.yml` only.
  - `platform/`, `service/api.py` and `service/store.py` never import `world`, `sim` or `lab`.
  - Test: `tests/test_boundaries.py`.
- **Same luck for every design.**
  - The model's coin flips, deliveries, crashes and the analyst's flips are drawn once per message in
    `world/luck.py`.
  - People's decisions are keyed by what they look at (`Luck.person`), so the same card gets the same decision in
    every design.
  - Test: `tests/test_same_luck.py`.
- **The model reads and code decides.**
  - A reply counts only if it parses as `domain.SignalRead`.
  - Every field must be backed by a quote copied from the article (`platform/evidence.py`). For a price move, the verb
    right before the number must point the same way as the sign.
  - The status (confirmed, unconfirmed, withdrawn) comes from the words in the checked quotes.
  - Categories, money, materiality and the lever come from the graph and the playbook, never from the model.
  - Tests: `tests/test_checks.py`, `tests/test_graph.py`.
- **A name never decides.** A supplier matches on stem, legal form and a country backed by a quote. A name without a
  country is held for a person (`platform/resolve.py`).
- **Article text is data.** It is fenced in the prompt, and the fence cannot be closed from inside. A quote that reads
  like an instruction to a machine is never evidence.
- **A message is handled once and a card is made once.**
  - Every workflow step is journaled before the next starts (`platform/journal.py`, `service/store.py`).
  - A redelivered message does nothing.
  - A card is unique per message and category; a manager's decision per card and per idempotency key.
  - Tests: `tests/test_pipeline.py`, `tests/test_api.py`.
- **Settings live in `config/`**, by owner:
  - the world in `world.yml`;
  - the sentinel in `platform.yml` (glossary, playbook, materiality, memory, pricing);
  - the designs in `designs.yml`;
  - seeds in `seeds.yml`;
  - thresholds in `gates.yml`.
- **Reports are generated, never edited.** CI regenerates REPORT.md, the README block and
  `web/public/data/report.json`, and fails on a diff.

## Held-out seeds

- `config/seeds.yml` lists them, and they run in the held-out world (`world.yml: heldout`): a tariff wave, more
  namesakes, more injections and more rumours.
- `python -m sentinel.cli run heldout` writes `reports/heldout.lock` before it runs. If the lock exists, it exits with
  code 3. CI checks the lock was committed exactly once.
- Gates were set from the development seeds before the held-out run. Never loosen a gate after it.
- If a change needs new held-out evidence, add new seeds under a new name and record why in an ADR.

## Data

Everything is simulated. There are no real companies, suppliers or prices; the publication names are invented.
