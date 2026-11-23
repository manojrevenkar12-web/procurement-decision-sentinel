"""The workflow: copies, merges, rumours, memory, crashes and redeliveries."""

from __future__ import annotations

import pytest
from helpers import COPPER_BODY, COPPER_READ, ScriptedReader, cfg, md, msg

from sentinel.platform.pipeline import Crash, Sentinel

HEAD = "LME copper rose 8.0%"


def _sentinel(replies: dict, **flags: bool) -> tuple[Sentinel, ScriptedReader]:
    r = ScriptedReader(replies)
    return Sentinel(md(), cfg(), r, "model_a", flags), r


def test_a_checked_move_becomes_one_card_per_material_category() -> None:
    s, _ = _sentinel({"M1": COPPER_READ})
    out = s.handle(msg("M1", HEAD, COPPER_BODY), 10)
    assert out.result == "card"
    cats = sorted(s.cards[c].cat_id for c in out.cards)
    assert cats == ["cable", "motors"]
    card = s.cards[out.cards[0]]
    assert card.evidence and card.path[-1].endswith("a year") or "across" in card.path[-1]


def test_a_syndicated_copy_skips_the_model_and_corroborates() -> None:
    s, r = _sentinel({"M1": COPPER_READ})
    first = s.handle(msg("M1", HEAD, COPPER_BODY), 10)
    copy = s.handle(msg("M2", "UPDATE: " + HEAD, COPPER_BODY, 12), 12)
    assert copy.result == "copy" and r.calls == ["M1"]
    assert all(s.cards[c].corroborations == 1 for c in first.cards)


def test_the_same_facts_from_another_source_are_merged() -> None:
    other = "Copper prices rose 8.0% in a volatile week, traders said, with the market tight."
    read2 = {**COPPER_READ, "commodity": "copper", "evidence": [{"field": "commodity", "quote": other}, {"field": "magnitude", "quote": other}]}
    s, _ = _sentinel({"M1": COPPER_READ, "M2": read2})
    s.handle(msg("M1", HEAD, COPPER_BODY), 10)
    out = s.handle(msg("M2", "Copper up", other, 20), 20)
    assert out.result == "corroborated" and len(s.cards) == 2


def test_an_unreadable_reply_is_repaired_once_then_held() -> None:
    s, r = _sentinel({"M1": ["{bad", COPPER_READ]})
    assert s.handle(msg("M1", HEAD, COPPER_BODY), 10).result == "card" and r.calls == ["M1", "M1"]
    s2, _ = _sentinel({"M1": "{bad"})
    assert s2.handle(msg("M1", HEAD, COPPER_BODY), 10).result == "hold"


def test_a_rumour_is_watched_and_its_confirmation_is_carded() -> None:
    rum = "The European Commission is reportedly considering a 20.0% tariff on aluminium products from China, people familiar said."
    conf = "The European Commission imposes a 20.0% tariff on aluminium products from China, effective next month."

    def read(q: str) -> dict:
        return {
            "kind": "tariff",
            "commodity": "aluminium",
            "country": "China",
            "magnitude_pct": 20.0,
            "status": "confirmed",
            "evidence": [{"field": f, "quote": q} for f in ("commodity", "country", "magnitude", "status")],
        }

    s, _ = _sentinel({"M1": read(rum), "M2": read(conf)})
    assert s.handle(msg("M1", "EU weighing tariff", rum), 10).result == "watch" and not s.cards
    assert s.handle(msg("M2", "EU imposes tariff", conf, 80), 80).result == "card"
    s2, _ = _sentinel({"M1": read(rum)}, hold_rumours=False)
    assert s2.handle(msg("M1", "EU weighing tariff", rum), 10).result == "card"


def test_a_dismissal_within_tolerance_stops_the_same_card_until_the_money_grows() -> None:
    small = "LME copper prices rose 2.0% over the week as inventories fell."
    bigger = "LME copper prices rose 3.0% over the week as demand rose."
    rd = lambda q, m: {**COPPER_READ, "magnitude_pct": m, "evidence": [{"field": "commodity", "quote": q}, {"field": "magnitude", "quote": q}]}  # noqa: E731
    s, _ = _sentinel({"M1": rd(small, 2.0), "M2": rd(small.replace("inventories fell", "stocks fell"), 2.0), "M3": rd(bigger, 3.0)})
    out = s.handle(msg("M1", "Copper rose 2.0%", small), 10)
    cable = next(c for c in out.cards if s.cards[c].cat_id == "cable")
    s.feedback(cable, "dismiss", "within_tolerance")
    s.handle(msg("M2", "Copper rose 2.0%", small.replace("inventories fell", "stocks fell"), 200), 200)
    assert s.suppressed and s.suppressed[-1][0] == "cable"
    out3 = s.handle(msg("M3", "Copper rose 3.0%", bigger, 400), 400)
    assert any(s.cards[c].cat_id == "cable" for c in out3.cards)


def test_a_crash_after_the_cards_resumes_without_duplicates() -> None:
    s, r = _sentinel({"M1": COPPER_READ})
    m = msg("M1", HEAD, COPPER_BODY)
    with pytest.raises(Crash):
        s.handle(m, 10, crash="after_card")
    n = len(s.cards)
    again = s.handle(m, 11)
    assert again.result == "card" and len(s.cards) == n and r.calls == ["M1"]
    assert s.handle(m, 12).result == "redelivered"


def test_without_the_journal_a_crash_duplicates_cards_and_pays_twice() -> None:
    s, r = _sentinel({"M1": COPPER_READ}, journal=False)
    m = msg("M1", HEAD, COPPER_BODY)
    with pytest.raises(Crash):
        s.handle(m, 10, crash="after_card")
    n = len(s.cards)
    s.handle(m, 11)
    assert len(s.cards) == 2 * n and r.calls == ["M1", "M1"]


def test_a_crash_after_the_read_does_not_read_again() -> None:
    s, r = _sentinel({"M1": COPPER_READ})
    m = msg("M1", HEAD, COPPER_BODY)
    with pytest.raises(Crash):
        s.handle(m, 10, crash="after_read")
    assert s.handle(m, 11).result == "card" and r.calls == ["M1"]


def test_an_article_with_the_same_facts_joins_a_crashed_workflow_instead_of_carding_again() -> None:
    # Found in the held-out run (ADR 0009): the copy arrived before the crashed original was redelivered.
    other = "Copper prices rose 8.0% in a volatile week, traders said, with the market tight."
    read2 = {**COPPER_READ, "commodity": "copper", "evidence": [{"field": "commodity", "quote": other}, {"field": "magnitude", "quote": other}]}
    s, _ = _sentinel({"M1": COPPER_READ, "M2": read2})
    m1 = msg("M1", HEAD, COPPER_BODY)
    with pytest.raises(Crash):
        s.handle(m1, 10, crash="after_card")
    n = len(s.cards)
    assert s.handle(msg("M2", "Copper up", other, 10.8), 10.8).result == "corroborated"
    assert s.handle(m1, 11).result == "card" and len(s.cards) == n
