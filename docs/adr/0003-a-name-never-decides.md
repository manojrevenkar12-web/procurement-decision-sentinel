# 0003: A name never decides

## Status
Accepted.

## Context
Supplier news often names a company that shares a stem with one of ours: a sister company in another country, or a
namesake. Matching on the name alone made 34 cards about namesakes on the development seeds.

## Decision
`platform/resolve.py` matches a supplier on three things:
- the stem;
- the legal form, when the article gives one;
- a country backed by a quote.

A different legal form or a different country means the company is not ours. A name whose country is not backed by a
quote is ambiguous, and a person decides.

## Consequences
- No namesake cards in the development seeds.
- Some real events wait for the desk when the model drops the legal form and guesses the country.
