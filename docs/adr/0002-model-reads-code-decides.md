# 0002: The model reads; code decides

## Status
Accepted.

## Context
A model asked "which of our categories does this hit, and how urgently?" names categories from words.

It cannot see contract mechanics, renewal windows or sub-supplier links. On the development seeds that design showed
153 cards a week, 17% of which mattered, and captured 21 points less value than an analyst.

## Decision
The model returns what the article says, with quotes, through a forced tool and a strict schema
(`domain.SignalRead`, `extra=forbid`). Code then:
- keeps a field only if a quote copied from the article backs it;
- for a price move, requires the verb right before the number to point the same way as the sign;
- sets the status (confirmed, unconfirmed, withdrawn) from the words in the checked quotes;
- holds the article for the market desk when a required field is not backed.

Categories, money, materiality and the lever come from the graph and the playbook.

## Consequences
- Without the quote check, value captured fell by about 15 points. Misread signs and tenfold numbers became cards.
  Managers dismissed those cards, and the dismissals then taught the memory to hide 124 real ones.
- About 5 articles a week go to the desk.
