# 0006: Dismissals are remembered

## Status
Accepted.

## Context
Each category has a tolerance for price moves that the sentinel cannot see (hedges, budget buffers). A move above
€150k can still be "within tolerance" for that manager, and repeated moves raise the same card again and again.

## Decision
When a manager dismisses a card as within tolerance, the sentinel remembers the largest amount dismissed for that
category and driver. It raises the card again only above that amount (`memory.suppress_factor: 1.0`). A supplier in
trouble is always shown.

On the development seeds, a factor of 1.25 hid 22 real cards. With 1.0 it hid 1, and within-tolerance cards fell from
70 to 45.

## Consequences
- Memory is only as good as the dismissals it learns from. A wrong number that gets dismissed poisons it; the
  no-quote-check ablation shows this.
