# 0001: A simulated buyer with its own truth, and the same luck for every design

## Status
Accepted.

## Context
A procurement alert system is judged by money acted on in time and by people's time spent. Neither can be measured on
a public dataset, because nobody publishes which news actually moved a buyer's costs.

## Decision
- `world/` builds a buyer for each seed: 20 categories, about 50 suppliers, contracts with a price mechanism and a
  renewal date, true commodity weights, and tier-2 links.
- It also builds 8 weeks of news, about 230 articles a week: commodity moves, tariffs, supplier events, rumours,
  syndicated copies, namesakes, injections and noise.
- The truth (which category each event really hits, by how much, and the right lever) stays in the world.
- Every random draw is made once per message, or keyed by what a person looks at. Designs only replay the draws.

## Consequences
- A difference between designs comes from the design.
- The numbers are only as good as the world's assumptions. The README's Limits section lists them.
