# 0004: A typed graph over the buyer's data, with tier-2 links from disclosures

## Status
Accepted.

## Context
Money at stake depends on things the article does not say:
- the price mechanism: index-linked and cost-plus contracts pass a move through now; a fixed price resets only at
  renewal;
- the renewal date;
- the category's commodity weight;
- whether a supplier buys its input from a country under a new tariff.

## Decision
`platform/graph.py` holds typed nodes (category, supplier, contract, commodity, country) and edges (FOR, WITH,
LOCATED_IN, CONTAINS, INDEXED_TO, SOURCES).

A checked signal walks the graph to a yearly amount per category. The path is kept, and each card shows it. Tier-2
SOURCES edges come only from supplier disclosures; in the world, 70% of the links are disclosed.

## Consequences
- Turning tier-2 links off cost 0.4 points of value overall. On tier-2 tariff impacts alone, value captured fell from
  64% to 31%.
- Undisclosed links stay invisible. Asking suppliers for disclosures is the lever, not more modelling.
- Should-cost weights are estimates (about 20% noise in the world). Impacts near the €150k floor are missed or carded
  wrongly at the margin.
