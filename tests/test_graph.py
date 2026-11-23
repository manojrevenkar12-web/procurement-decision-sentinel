"""The graph walk: pass-through by contract, renewal windows, tier-2 links, levers."""

from __future__ import annotations

from helpers import cfg, md

from sentinel.domain import Facts
from sentinel.platform.graph import KnowledgeGraph
from sentinel.platform.playbook import choose_lever


def _by_cat(exps: list) -> dict:
    return {e.cat_id: e for e in exps}


def test_an_index_linked_contract_passes_a_move_through_now_and_a_fixed_one_only_at_renewal() -> None:
    g = KnowledgeGraph(md(), cfg())
    e = _by_cat(g.exposures(Facts("commodity_move", "confirmed", commodity="copper", magnitude=0.10), day=0))
    # K1 index-linked: 16M * 0.5 * 0.1 = 800k; K2 fixed, renews in 300 days: outside the window, 0.
    assert abs(e["cable"].impact_eur - 800_000) < 1
    assert e["cable"].lever == "index_pass_through_check"
    # motors: fixed, renews in 60 days -> 8M * 0.25 * 0.1 = 200k at renewal
    assert abs(e["motors"].impact_eur - 200_000) < 1 and e["motors"].lever == "renewal_should_cost"


def test_a_tariff_reaches_tier_two_only_through_a_disclosed_link() -> None:
    f = Facts("tariff", "confirmed", commodity="aluminium", country="CN", magnitude=0.2)
    with_t2 = _by_cat(KnowledgeGraph(md(), cfg()).exposures(f, 0))
    without = _by_cat(KnowledgeGraph(md(), cfg(), tier2=False).exposures(f, 0))
    assert "motors" in with_t2 and "motors" not in without
    assert any("tier 2" in p for p in with_t2["motors"].path)
    # tier 1: Krasline (CN) ships aluminium extrusions; an alternate outside CN exists -> shift volume
    assert abs(with_t2["extr"].impact_eur - 6e6 * 0.2) < 1 and with_t2["extr"].lever == "shift_volume"


def test_a_main_source_in_trouble_gets_a_buffer_and_dual_sourcing() -> None:
    e = _by_cat(KnowledgeGraph(md(), cfg()).exposures(Facts("supplier_event", "confirmed", supplier_id="S1", event="insolvency"), 0))
    assert e["cable"].lever == "dual_source_buffer" and abs(e["cable"].impact_eur - 16e6 * 0.3) < 1


def test_the_first_matching_playbook_rule_wins() -> None:
    rules = cfg()["playbook"]
    assert choose_lever(rules, {"kind": "supplier_event", "event": "sanction", "share": 0.9}) == "stop_new_pos"
    assert choose_lever(rules, {"kind": "supplier_event", "event": "outage", "share": 0.2}) == "qualify_alternate"
    assert choose_lever(rules, {"kind": "tariff", "alternate_outside_country": False}) == "landed_cost_requote"


def test_every_edge_type_is_present() -> None:
    rels = {e.rel for e in KnowledgeGraph(md(), cfg()).edges()}
    assert rels == {"CONTAINS", "LOCATED_IN", "FOR", "WITH", "INDEXED_TO", "SOURCES"}
