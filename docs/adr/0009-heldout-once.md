# 0009: A held-out world, run once behind a lock

## Status
Accepted. Run on 23 Nov 2026.

## Context
Everything else was tuned on the development seeds: the materiality floor, the memory factor, the dedupe thresholds
and the gates. A result on those seeds says how well the sentinel was fitted to them.

## Decision
Seeds 101 and 102 run in a held-out world that adds:
- a tariff wave of 10 announcements on day 20;
- namesakes for 50% of suppliers (dev: 30%);
- twice the injections (8% of articles);
- more rumours;
- more tier-2 links.

`run heldout` writes `reports/heldout.lock` (seeds and a hash of the config) before it runs, and refuses to run again.
CI checks that the lock was committed once.

## Consequences
The held-out numbers are reported as they came out.

- **8 of 9 gates passed.** Value captured was 83.5% against 73.8% for the analyst (+9.8 points, 95% CI +6.0 to +13.8).
  91.5% of cards mattered. People's time was 39% of the analyst design's. There were no cards from injections,
  namesakes or dead rumours. The smaller model passed its release gate.
- **The duplicate-cards gate failed: 1 duplicate.**
  - Cause: a worker crashed after writing its card for a tariff article. A syndicated copy with different wording
    arrived 0.8 hours later, before the redelivery. The crashed workflow had not yet published its facts, so the
    copy made a second card.
  - Fix (after the run): the facts are published in the same step as the cards. Regression test:
    `test_an_article_with_the_same_facts_joins_a_crashed_workflow_instead_of_carding_again`.
  - The development numbers did not change. The held-out report still shows the duplicate.
  - The fix has not been shown on new held-out seeds yet. That needs new seeds under a new name.
- **The evaluator's cause labels were too loose.**
  - Two cards in the held-out ablation rows (smaller model, no copy check) are labelled "injection". Both were
    computed from the article's real 7.7% copper move, not the injected 40%. Both were real exposures below the
    category's tolerance.
  - The label now needs the event to not touch the category at all. The development report was regenerated with
    it (model alone: 108 injection cards instead of 111). The locked held-out report keeps the old labels.
- Tier-2 links mattered more here: without them, value captured on tier-2 tariff impacts fell from 91% to 0% (7 pairs).
