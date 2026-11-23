# 0005: Each message is a durable workflow: journaled steps, at-least-once delivery, one card

## Status
Accepted.

## Context
A news feed delivers at least once, and workers die mid-way. In the world, 4% of messages arrive twice, 3% crash after
the read and 3% crash after the cards are written.

## Decision
- Each step's result (read, cards, done) is written to a journal before the next step starts. The journal is
  `MemoryJournal` in the study and SQLite in the service.
- A redelivered message whose workflow is done does nothing.
- A workflow that crashed resumes from its last step: the model is not called again, and no card is made twice.
- A card's idempotency key is message plus category.

## Consequences
- Without the journal: 18 duplicate cards on the development seeds, and some articles paid for twice.
- A restarted service resumes from the store (`tests/test_api.py::test_a_restart_resumes_from_the_store`).
