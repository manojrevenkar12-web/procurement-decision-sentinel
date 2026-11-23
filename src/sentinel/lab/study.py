"""Runs every design on a split's seeds, grades them, checks gates and writes reports/<split>.json."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .. import config
from ..platform.graph import KnowledgeGraph
from ..sim.evaluate import Pair, by_kind, paired_value_diff, per_week, pooled, seed_metrics
from ..sim.simulate import Run, SeedSim
from ..world.world import World

REPORTS = config.REPORTS
LOCK = REPORTS / "heldout.lock"


class HeldOutLocked(RuntimeError):
    pass


def _round(x: Any) -> Any:
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        x = float(x)
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            return None
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_round(v) for v in x]
    return x


def config_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(config.CONFIG.glob("*.yml")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def check_gates(res: dict[str, Any], g: dict[str, Any]) -> dict[str, Any]:
    d = res["designs"]
    pm, sm = d["platform"]["metrics"], d["status_quo"]["metrics"]
    gp = g["platform"]
    rows: list[tuple[str, float | None, float, str]] = [
        ("Value captured minus status quo, points", (pm["value_share"] - sm["value_share"]) * 100, gp["value_share_min_over_status_quo_pts"], "min"),
        ("Share of cards that were material", pm["precision"], gp["precision_min"], "min"),
        ("People's minutes per week / status quo", pm["minutes_per_week"] / sm["minutes_per_week"], gp["minutes_max_ratio_to_status_quo"], "max"),
        ("Median hours from first signal to decision", pm["decision_median_h"], gp["decision_median_h_max"], "max"),
        ("Cards caused by injected text", pm["injection_cards"], gp["injection_cards_max"], "max"),
        ("Cards about a namesake or the wrong supplier", pm["namesake_cards"] + pm["wrong_entity_cards"], gp["namesake_or_wrong_entity_cards_max"], "max"),
        ("Cards from rumours that died", pm["rumour_cards"], gp["rumour_cards_max"], "max"),
        ("Duplicate cards", pm["duplicate_cards"], gp["duplicate_cards_max"], "max"),
        ("Model cost per accepted card, EUR", pm["cost_per_accepted_card_eur"], gp["cost_per_accepted_card_eur_max"], "max"),
    ]
    platform = [{"gate": n, "value": v, "limit": lim, "kind": k, "pass": v is not None and (v >= lim if k == "min" else v <= lim)} for n, v, lim, k in rows]
    gs = g["model_swap"]
    swap: dict[str, Any] = {}
    for name in res["model_swap"]:
        m = d[name]["metrics"]
        below = (pm["value_share"] - m["value_share"]) * 100
        ratio = m["minutes_per_week"] / pm["minutes_per_week"]
        ok = below <= gs["value_share_max_below_platform_pts"] and (m["precision"] or 0) >= gs["precision_min"] and ratio <= gs["minutes_max_ratio_to_platform"]
        swap[name] = {"value_share_below_platform_pts": below, "precision": m["precision"], "minutes_ratio_to_platform": ratio, "verdict": "passes" if ok else "blocked"}
    return {"platform": platform, "platform_pass": all(r["pass"] for r in platform), "model_swap": swap}


def _card_view(w: World, run: Run, card_id: str) -> dict[str, Any]:
    assert run.sentinel is not None
    s = run.sentinel
    c = s.cards[card_id]
    art = w.by_msg[c.msg_ids[0]]
    ev_id = art.event_id
    imp = w.impacts.get((ev_id, c.cat_id))
    decision = run.decisions.get(card_id)
    return {
        "card_id": c.card_id,
        "category": s.md.categories[c.cat_id].label,
        "manager": c.manager,
        "kind": c.kind,
        "driver": c.driver,
        "impact_eur": c.impact_eur,
        "lever": c.lever,
        "path": list(c.path),
        "evidence": [{"msg_id": m, "quote": q} for m, q in c.evidence],
        "sources": [{"msg_id": m, "source": w.by_msg[m].msg.source, "headline": w.by_msg[m].msg.headline, "published_h": w.by_msg[m].msg.published_h} for m in c.msg_ids],
        "created_h": c.created_h,
        "decision": None if decision is None else {"decision": decision[0], "reason": decision[1], "at_h": decision[2]},
        "truth": {"material": imp is not None, "true_impact_eur": imp.impact_eur if imp else w.near_misses.get((ev_id, c.cat_id)), "right_lever": imp.lever if imp else None},
        "trace": s.traces.get(c.msg_ids[0], []),
    }


def _msg_view(w: World, run: Run, msg_id: str, note: str) -> dict[str, Any]:
    assert run.sentinel is not None
    a = w.by_msg[msg_id]
    out = next((o for o in run.sentinel.log if o.msg_id == msg_id), None)
    return {
        "msg_id": msg_id,
        "note": note,
        "headline": a.msg.headline,
        "body": a.msg.body,
        "source": a.msg.source,
        "outcome": out.result if out else None,
        "reason": out.reason if out else None,
        "trace": run.sentinel.traces.get(msg_id, []),
    }


def pick_samples(w: World, run: Run) -> dict[str, Any]:
    s = run.sentinel
    assert s is not None
    cards = list(s.cards.values())
    picks: dict[str, Any] = {}
    tier2 = [c for c in cards if any("tier 2" in p for p in c.path) and (w.by_msg[c.msg_ids[0]].event_id, c.cat_id) in w.impacts]
    sup = [c for c in cards if c.kind == "supplier_event" and (w.by_msg[c.msg_ids[0]].event_id, c.cat_id) in w.impacts]
    com = sorted([c for c in cards if c.kind == "commodity_move" and c.corroborations > 0], key=lambda c: -abs(c.impact_eur))
    for name, pool in (("tier2_tariff", tier2), ("supplier_event", sup), ("commodity_move", com)):
        if pool:
            picks[name] = _card_view(w, run, pool[0].card_id)
    msgs: dict[str, Any] = {}
    inj = [a.msg.msg_id for a in w.articles if a.injection_targets and a.copy_of is None]
    for mid in inj:
        tr = s.traces.get(mid, [])
        if any(t.get("instruction_like") for t in tr):
            msgs["injection"] = _msg_view(w, run, mid, "The article carries an instruction to machines. Its quotes are not evidence.")
            break
    look = [a.msg.msg_id for a in w.articles if w.events[a.event_id].lookalike_of and a.copy_of is None]
    for mid in look:
        o = next((x for x in s.log if x.msg_id == mid), None)
        if o and o.result == "ignore":
            msgs["namesake"] = _msg_view(w, run, mid, "Same name as one of our suppliers, different legal form and country.")
            break
    rum = [a.msg.msg_id for a in w.articles if a.status == "unconfirmed" and a.copy_of is None]
    for mid in rum:
        o = next((x for x in s.log if x.msg_id == mid), None)
        if o and o.result == "watch":
            msgs["rumour"] = _msg_view(w, run, mid, "Unconfirmed: watched until confirmed or withdrawn.")
            break
    return {"cards": picks, "messages": msgs}


def graph_stats(md_world: World) -> dict[str, Any]:
    md = md_world.master_data()
    edges = KnowledgeGraph(md, config.platform()).edges()
    rels: dict[str, int] = {}
    for e in edges:
        rels[e.rel] = rels.get(e.rel, 0) + 1
    return {"categories": len(md.categories), "suppliers": len(md.suppliers), "contracts": len(md.contracts), "tier2_disclosed": len(md.tier2), "tier2_true": len(md_world.tier2), "edges": rels}


def run_split(split: str) -> dict[str, Any]:
    pcfg = config.platform()
    dcfg = config.designs()
    designs: dict[str, dict[str, Any]] = dcfg["designs"]
    seeds: list[int] = config.seeds()[split]
    variant = "heldout" if split == "heldout" else "dev"
    pairs: dict[str, list[Pair]] = {n: [] for n in designs}
    samples: dict[str, Any] = {}
    graph: dict[str, Any] = {}
    for i, seed in enumerate(seeds):
        sim = SeedSim(seed, variant)
        for name, d in designs.items():
            run = sim.run(name, d, pcfg, keep=(name == "platform" and i == 0))
            if run.sentinel is not None:
                samples = pick_samples(sim.world, run)
                graph = graph_stats(sim.world)
                run.sentinel = None
            pairs[name].append((sim.world, run))
    metrics = {n: pooled([seed_metrics(w, r) for w, r in pairs[n]]) for n in designs}
    res: dict[str, Any] = {
        "split": split,
        "variant": variant,
        "seeds": seeds,
        "designs": {n: {"label": d["label"], "kind": d["kind"], "model": d.get("model"), "metrics": metrics[n]} for n, d in designs.items()},
        "order": list(designs),
        "ablations": dcfg["ablations"],
        "model_swap": dcfg["model_swap"],
        "comparisons": {
            "platform_vs_status_quo": paired_value_diff(pairs["platform"], pairs["status_quo"]),
            "model_alone_vs_status_quo": paired_value_diff(pairs["model_alone"], pairs["status_quo"]),
            **{f"{a}_vs_platform": paired_value_diff(pairs[a], pairs["platform"]) for a in dcfg["ablations"] + dcfg["model_swap"]},
        },
        "by_kind": {n: by_kind(pairs[n]) for n in ("status_quo", "model_alone", "platform", "tier1_only")},
        "weeks": {n: per_week(pairs[n]) for n in ("status_quo", "model_alone", "platform")},
        "samples": samples,
        "graph": graph,
    }
    res["gates"] = check_gates(res, config.gates())
    return _round(res)


def write(split: str, res: dict[str, Any]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"{split}.json"
    path.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return path


def run_heldout_once() -> dict[str, Any]:
    if LOCK.exists():
        raise HeldOutLocked(f"{LOCK} exists: the held-out seeds have been run. Add new seeds under a new name and an ADR.")
    REPORTS.mkdir(exist_ok=True)
    LOCK.write_text(json.dumps({"seeds": config.seeds()["heldout"], "config_sha256": config_hash()}, indent=1) + "\n", encoding="utf-8")
    res = run_split("heldout")
    write("heldout", res)
    return res
