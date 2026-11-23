# Repeatable tasks

## Add a signal source
1. Write an adapter that turns the source's items into `domain.Message` (id, source, time, headline, body) and posts
   them to `POST /v1/signals`. Use the source's own item id as `msg_id`, so a redelivery is free.
2. If the source uses new words for a commodity or a country, add them to `glossary` in `config/platform.yml`.
3. Add a test in `tests/test_checks.py` with one real sentence from the source.

## Add a commodity or a category
1. Add the commodity's synonyms under `glossary.commodities` in `config/platform.yml`.
2. In the world, add it under `commodities` (with a weekly volatility) and give categories a true weight in
   `world.yml`. The world derives the sentinel's should-cost estimates from these, with noise.
3. Run `pytest -q`, then the development study, and compare the value-by-signal table.

## Add a lever to the playbook
1. Add a rule under `playbook` in `config/platform.yml`. Rules are checked in order; the first match wins.
2. Mirror the right answer in `world/world.py::_lever`, so the study can tell whether the lever was right.
3. Add a case to `tests/test_graph.py::test_the_first_matching_playbook_rule_wins`.

## Swap or upgrade the model
1. Add the candidate as a design in `config/designs.yml` with `kind: platform` and its model, and list it under
   `model_swap`. Add its price to `pricing` in `config/platform.yml`.
2. Run the development study. The model-swap gate gives it a verdict: `passes` or `blocked`.
3. Compare value, desk minutes and model cost together. A cheaper model that sends more articles to the desk can cost
   more people's time than it saves in tokens.

## Change a gate
Gates are set on the development seeds. Never change one after the held-out run. If evidence says a gate is wrong,
write an ADR, add new held-out seeds under a new name and run them once.

## Run new held-out seeds
Add a new list in `config/seeds.yml`, write an ADR saying why, then point the lock and the split at it. Never delete
`reports/heldout.lock`.

## Regenerate reports and screenshots
```bash
python -m sentinel.cli run dev && python -m sentinel.cli report
cd web && npm run build && (python -m http.server 4173 -d dist &) && cd .. && python scripts/screenshots.py
```

## Wire a real model and real data
1. Build `domain.MasterData` from the spend cube, the supplier master, the contract repository (price mechanism,
   index, renewal date) and the supplier disclosures.
2. Use `AnthropicReader(api_key, model)` or `OpenAICompatibleReader(api_key, model, base_url)`.
3. Pass them to `service.api.create_app(md, config.platform(), reader, model, Store("sentinel.db"))`.
