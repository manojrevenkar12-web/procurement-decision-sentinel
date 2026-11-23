"""Runs one design over one seed in virtual time: deliveries, crashes and redeliveries, the desk, managers, reviews."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any

from ..domain import Card
from ..platform.alone import ModelAlone
from ..platform.pipeline import Crash, Sentinel
from ..world.luck import Luck, draw_luck
from ..world.people import People
from ..world.reader_sim import SimReader
from ..world.world import World


@dataclass
class Capture:
    at_h: float
    value: float
    via: str  # card | monthly
    right_lever: bool


@dataclass
class Run:
    design: str
    cards: list[Card]
    decisions: dict[str, tuple[str, str | None, float]] = field(default_factory=dict)
    captured: dict[tuple[str, str], Capture] = field(default_factory=dict)
    minutes: dict[str, float] = field(default_factory=lambda: {"cards": 0.0, "desk": 0.0, "analyst": 0.0, "monthly": 0.0})
    cost_eur: float = 0.0
    model_calls: int = 0
    holds: int = 0
    desk_unresolved: int = 0
    suppressed: list[tuple[str, str, float, str]] = field(default_factory=list)
    outcomes: dict[str, int] = field(default_factory=dict)
    sentinel: Sentinel | None = None


class SeedSim:
    def __init__(self, seed: int, variant: str) -> None:
        self.world = World(seed, variant)
        self.luck: Luck = draw_luck(self.world)
        self.people = People(self.world, self.luck)
        self.md = self.world.master_data()

    def run(self, name: str, design: dict[str, Any], pcfg: dict[str, Any], keep: bool = False) -> Run:
        w = self.world
        cfg = w.cfg
        p = cfg["people"]
        horizon = int(cfg["horizon_days"])
        kind = design["kind"]
        sentinel: Sentinel | None = None
        alone: ModelAlone | None = None
        if kind == "platform":
            sentinel = Sentinel(self.md, pcfg, SimReader(w, self.luck, design["model"]), design["model"], design.get("flags"))
        elif kind == "model_alone":
            alone = ModelAlone(self.md, pcfg, SimReader(w, self.luck, design["model"]), design["model"])
        shown: dict[str, Card] = {}
        run = Run(name, [])
        analyst_queue: list[str] = []
        analyst_seen: set[tuple[str, str]] = set()
        analyst_cards = 0
        seq = 0
        q: list[tuple[float, int, str, str, int]] = []

        def push(h: float, what: str, ref: str, attempt: int = 0) -> None:
            nonlocal seq
            seq += 1
            heapq.heappush(q, (h, seq, what, ref, attempt))

        for msg in w.messages():
            push(msg.published_h, "msg", msg.msg_id)
            dl = self.luck.delivery[msg.msg_id]
            if dl.redeliver:
                push(msg.published_h + dl.redeliver_after_h, "msg", msg.msg_id, 1)
        for day in range(1, horizon + 1):
            push(day * 24 + float(cfg["desk_hour"]), "desk", str(day))
            push(day * 24 + float(cfg["manager_hour"]), "managers", str(day))
        msgs = {m.msg_id: m for m in w.messages()}
        offsets = {c: (i * int(p["monthly_review_days"])) // len(w.cat_ids) for i, c in enumerate(w.cat_ids)}

        while q:
            h, _, what, ref, attempt = heapq.heappop(q)
            if h >= horizon * 24 + 24:
                break
            if what == "msg":
                msg = msgs[ref]
                if sentinel is not None:
                    dl = self.luck.delivery[ref]
                    crash = None
                    if attempt == 0 and dl.crash_after_read:
                        crash = "after_read"
                    elif attempt == 0 and dl.crash_after_card:
                        crash = "after_card"
                    try:
                        out = sentinel.handle(msg, h, crash)
                        run.outcomes[out.result] = run.outcomes.get(out.result, 0) + 1
                    except Crash:
                        run.outcomes["crash"] = run.outcomes.get("crash", 0) + 1
                        push(h + 1.0, "msg", ref, attempt + 2)  # visibility timeout, then the broker redelivers
                elif alone is not None and attempt == 0:
                    alone.handle(msg, h)
                elif kind == "analyst" and attempt == 0:
                    analyst_queue.append(ref)
            elif what == "desk":
                day = int(ref)
                if kind == "analyst":
                    budget = float(p["analyst_minutes_per_day"])
                    while analyst_queue and budget > 0:
                        mid = analyst_queue.pop(0)
                        art = w.by_msg[mid]
                        cost = float(p["analyst_skim_min"]) + (float(p["analyst_read_min"]) if w.events[art.event_id].kind != "noise" else 0.0)
                        budget -= cost
                        run.minutes["analyst"] += cost
                        if w.events[art.event_id].kind == "noise":
                            continue
                        for cat in self.people.analyst_flags(art):
                            if (art.event_id, cat) in analyst_seen:
                                continue
                            analyst_seen.add((art.event_id, cat))
                            analyst_cards += 1
                            c = Card(f"A{analyst_cards:05d}", f"{mid}|{cat}", cat, art.event_id, "other", 0.0, "review", (), (), [mid], h, w.manager_of(cat))
                            shown[c.card_id] = c
                if sentinel is not None:
                    budget = float(p["desk_minutes_per_day"])
                    while sentinel.holds and budget >= float(p["hold_review_min"]):
                        hold = sentinel.holds.pop(0)
                        budget -= float(p["hold_review_min"])
                        run.minutes["desk"] += float(p["hold_review_min"])
                        facts = self.people.desk_facts(w.by_msg[hold.msg_id])
                        if facts == "unresolved":
                            run.desk_unresolved += 1
                            continue
                        sentinel.resolve_hold(msgs[hold.msg_id], facts, h)
                for c in w.cat_ids:
                    if day >= offsets[c] and (day - offsets[c]) % int(p["monthly_review_days"]) == 0 and day > 0:
                        run.minutes["monthly"] += float(p["monthly_review_min"])
                        for (ev_id, cat), imp in w.impacts.items():
                            if cat != c or imp.start_h >= h or (ev_id, cat) in run.captured:
                                continue
                            if self.people.monthly_finds(ev_id, cat):
                                right = self.people.lever_right(ev_id, cat, "review", imp)
                                run.captured[(ev_id, cat)] = Capture(h, self.people.value(imp, h, right), "monthly", right)
            elif what == "managers":
                if sentinel is not None:
                    shown.update(sentinel.cards)
                if alone is not None:
                    shown.update(alone.cards)
                platform_order = kind == "platform"
                for m in range(int(cfg["managers"])):
                    queue = [c for c in shown.values() if c.manager == m and c.status == "open" and c.created_h <= h]
                    queue.sort(key=(lambda c: (-abs(c.impact_eur), c.created_h)) if platform_order else (lambda c: c.created_h))
                    budget = float(p["manager_minutes_per_day"])
                    for card in queue:
                        if budget < float(p["card_review_min"]):
                            break
                        budget -= float(p["card_review_min"])
                        run.minutes["cards"] += float(p["card_review_min"])
                        decision, reason = self.people.manager_decides(card.msg_ids[0], card.cat_id)
                        card.status = "accepted" if decision == "accept" else "dismissed"
                        run.decisions[card.card_id] = (decision, reason, h)
                        if sentinel is not None and card.card_id in sentinel.cards:
                            sentinel.feedback(card.card_id, decision, reason)
                        ev_id, truth = self.people.truth_for(card.msg_ids[0], card.cat_id)
                        if decision == "accept" and truth is not None and (ev_id, card.cat_id) not in run.captured:
                            right = self.people.lever_right(ev_id, card.cat_id, card.lever, truth)
                            run.captured[(ev_id, card.cat_id)] = Capture(h, self.people.value(truth, h, right), "card", right)
        if sentinel is not None:
            shown.update(sentinel.cards)
            run.cost_eur, run.model_calls, run.suppressed = sentinel.cost_eur, sentinel.model_calls, sentinel.suppressed
            run.holds = sum(1 for o in sentinel.log if o.result == "hold")
            if keep:
                run.sentinel = sentinel
        if alone is not None:
            shown.update(alone.cards)
            run.cost_eur, run.model_calls = alone.cost_eur, alone.model_calls
        run.cards = sorted(shown.values(), key=lambda c: (c.created_h, c.card_id))
        return run
