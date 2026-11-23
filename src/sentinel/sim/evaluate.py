"""Grades runs against the truth. The only module outside world/ that reads the truth."""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

import numpy as np

from ..world.world import World
from .simulate import Run

Pair = tuple[World, Run]
FALSE_CAUSES = ("injection", "namesake", "rumour", "below_tolerance", "wrong_entity", "noise", "estimate_or_read")


def _event(w: World, msg_id: str) -> str:
    return w.by_msg[msg_id].event_id


def false_cause(w: World, card: Any) -> str:
    art = w.by_msg[card.msg_ids[0]]
    ev = w.events[art.event_id]
    if art.injection_targets and card.cat_id in art.injection_targets and (ev.event_id, card.cat_id) not in w.near_misses:
        return "injection"  # the category was named by the injection and the event does not touch it at all"
    if ev.lookalike_of:
        return "namesake"
    if ev.rumour and ev.outcome != "confirmed":
        return "rumour"
    if ev.kind == "noise":
        return "noise"
    if (ev.event_id, card.cat_id) in w.near_misses:
        return "below_tolerance"
    if card.driver.startswith("supplier:") and ev.supplier_id and not card.driver.startswith(f"supplier:{ev.supplier_id}:"):
        return "wrong_entity"
    return "estimate_or_read"


def seed_metrics(w: World, run: Run) -> dict[str, Any]:
    horizon_weeks = float(w.cfg["horizon_days"]) / 7
    stake = sum(i.at_stake_eur for i in w.impacts.values())
    captured = sum(c.value for c in run.captured.values())
    via_card = sum(c.value for c in run.captured.values() if c.via == "card")
    seen: set[tuple[str, str]] = set()
    true_cards = dupes = 0
    causes: Counter[str] = Counter()
    leads: list[float] = []
    for card in run.cards:
        key = (_event(w, card.msg_ids[0]), card.cat_id)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        if key in w.impacts:
            true_cards += 1
            leads.append(card.created_h - w.impacts[key].start_h)
        else:
            causes[false_cause(w, card)] += 1
    decided = [run.captured[k].at_h - w.impacts[k].start_h for k in run.captured if run.captured[k].via == "card"]
    accepted_true = sum(1 for k, c in run.captured.items() if c.via == "card")
    reviewed = len(run.decisions)
    suppressed_true = sum(1 for cat, _d, _i, mid in run.suppressed if (_event(w, mid), cat) in w.impacts)
    minutes = dict(run.minutes)
    return {
        "material_pairs": len(w.impacts),
        "value_at_stake_eur": stake,
        "value_captured_eur": captured,
        "value_via_cards_eur": via_card,
        "caught_by_card": accepted_true,
        "cards": len(run.cards),
        "true_cards": true_cards,
        "duplicate_cards": dupes,
        "false_cards": sum(causes.values()),
        "false_causes": {c: causes.get(c, 0) for c in FALSE_CAUSES},
        "unreviewed_cards": len(run.cards) - reviewed,
        "lead_h": leads,
        "decision_h": decided,
        "minutes": minutes,
        "minutes_per_week": sum(minutes.values()) / horizon_weeks,
        "cost_eur": run.cost_eur,
        "model_calls": run.model_calls,
        "messages": len(w.articles),
        "holds": run.holds,
        "desk_unresolved": run.desk_unresolved,
        "suppressed": len(run.suppressed),
        "suppressed_material": suppressed_true,
        "outcomes": dict(run.outcomes),
        "weeks": horizon_weeks,
    }


def pooled(rows: list[dict[str, Any]]) -> dict[str, Any]:
    s = lambda k: sum(r[k] for r in rows)  # noqa: E731
    leads = [x for r in rows for x in r["lead_h"]]
    dec = [x for r in rows for x in r["decision_h"]]
    weeks = s("weeks")
    minutes = {k: sum(r["minutes"][k] for r in rows) / weeks for k in rows[0]["minutes"]}
    accepted = s("caught_by_card")
    out = {
        "value_share": s("value_captured_eur") / s("value_at_stake_eur"),
        "value_share_by_seed": [r["value_captured_eur"] / r["value_at_stake_eur"] for r in rows],
        "value_captured_eur_per_week": s("value_captured_eur") / weeks,
        "value_at_stake_eur_per_week": s("value_at_stake_eur") / weeks,
        "card_value_share": s("value_via_cards_eur") / s("value_at_stake_eur"),
        "recall_by_card": accepted / s("material_pairs"),
        "material_pairs": s("material_pairs"),
        "cards_per_week": s("cards") / weeks,
        "precision": (s("true_cards") / s("cards")) if s("cards") else None,
        "duplicate_cards": s("duplicate_cards"),
        "false_cards": s("false_cards"),
        "false_causes": {c: sum(r["false_causes"][c] for r in rows) for c in FALSE_CAUSES},
        "unreviewed_cards": s("unreviewed_cards"),
        "lead_median_h": statistics.median(leads) if leads else None,
        "decision_median_h": statistics.median(dec) if dec else None,
        "decision_p90_h": float(np.percentile(dec, 90)) if dec else None,
        "minutes_per_week": sum(minutes.values()),
        "minutes_by_kind_per_week": minutes,
        "cost_eur_per_week": s("cost_eur") / weeks,
        "cost_per_accepted_card_eur": (s("cost_eur") / accepted) if accepted else None,
        "model_calls_per_message": s("model_calls") / s("messages"),
        "messages_per_week": s("messages") / weeks,
        "holds_per_week": s("holds") / weeks,
        "desk_unresolved": s("desk_unresolved"),
        "suppressed": s("suppressed"),
        "suppressed_material": s("suppressed_material"),
        "injection_cards": sum(r["false_causes"]["injection"] for r in rows),
        "namesake_cards": sum(r["false_causes"]["namesake"] for r in rows),
        "wrong_entity_cards": sum(r["false_causes"]["wrong_entity"] for r in rows),
        "rumour_cards": sum(r["false_causes"]["rumour"] for r in rows),
    }
    return out


def pair_values(pairs: list[Pair]) -> list[tuple[str, float, float]]:
    """(cluster, at stake, captured) per material pair; a cluster is one event in one seed."""
    out = []
    for w, run in pairs:
        for k, imp in w.impacts.items():
            c = run.captured.get(k)
            out.append((f"{w.seed}:{k[0]}", imp.at_stake_eur, c.value if c else 0.0))
    return out


def paired_value_diff(a: list[Pair], b: list[Pair], n_boot: int = 2000) -> dict[str, float]:
    """Value share of design a minus design b, with an event-cluster bootstrap. Both saw the same world and luck."""
    va, vb = pair_values(a), pair_values(b)
    assert [x[0] for x in va] == [x[0] for x in vb]
    clusters: dict[str, list[int]] = {}
    for i, (c, _, _) in enumerate(va):
        clusters.setdefault(c, []).append(i)
    keys = list(clusters)
    stake = np.array([x[1] for x in va])
    ca = np.array([x[2] for x in va])
    cb = np.array([x[2] for x in vb])
    per = np.array([[stake[clusters[k]].sum(), ca[clusters[k]].sum(), cb[clusters[k]].sum()] for k in keys])
    diff = (per[:, 1].sum() - per[:, 2].sum()) / per[:, 0].sum()
    rng = np.random.default_rng(20261123)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    s = per[idx]
    boots = (s[:, :, 1].sum(1) - s[:, :, 2].sum(1)) / s[:, :, 0].sum(1)
    return {"diff": float(diff), "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5)), "clusters": len(keys)}


def by_kind(pairs: list[Pair]) -> dict[str, dict[str, float]]:
    agg: dict[str, list[float]] = {}
    for w, run in pairs:
        for k, imp in w.impacts.items():
            kind = w.events[k[0]].kind + (" (tier 2)" if imp.tier2_only else "")
            c = run.captured.get(k)
            a = agg.setdefault(kind, [0.0, 0.0, 0.0, 0.0])
            a[0] += imp.at_stake_eur
            a[1] += c.value if c else 0.0
            a[2] += 1
            a[3] += 1 if c and c.via == "card" else 0
    return {k: {"value_share": v[1] / v[0] if v[0] else 0.0, "pairs": v[2], "caught_by_card": v[3] / v[2] if v[2] else 0.0} for k, v in sorted(agg.items())}


def per_week(pairs: list[Pair]) -> list[dict[str, float]]:
    weeks = int(pairs[0][0].cfg["horizon_days"]) // 7
    stake = [0.0] * weeks
    cap = [0.0] * weeks
    cards = [0] * weeks
    for w, run in pairs:
        for k, imp in w.impacts.items():
            wk = min(weeks - 1, int(imp.start_h // (24 * 7)))
            stake[wk] += imp.at_stake_eur
            c = run.captured.get(k)
            cap[wk] += c.value if c else 0.0
        for card in run.cards:
            cards[min(weeks - 1, int(card.created_h // (24 * 7)))] += 1
    n = len(pairs)
    return [{"week": i + 1, "at_stake_eur": stake[i] / n, "captured_eur": cap[i] / n, "cards": cards[i] / n} for i in range(weeks)]
