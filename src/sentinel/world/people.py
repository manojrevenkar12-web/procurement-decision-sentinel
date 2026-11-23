"""The people in the world: the market analyst (status quo), the market desk, category managers and their monthly review.

People know what they know: a manager can tell a card that matters from one that does not most of the time; the
desk can read an article correctly most of the time. Their coin flips come from `Luck.person`, keyed by what they
look at, so the same card gets the same decision in every design.
"""

from __future__ import annotations

from typing import Literal

from ..domain import Facts
from .luck import Luck
from .world import Article, Impact, World


class People:
    def __init__(self, world: World, luck: Luck) -> None:
        self.w = world
        self.luck = luck
        self.p = world.cfg["people"]

    # ----- the market analyst of the status quo -----

    def analyst_flags(self, art: Article) -> list[str]:
        w = self.w
        ev = w.events[art.event_id]
        lk = self.luck.analyst[art.msg.msg_id]
        a = self.p["analyst"]
        if art.status == "withdrawn" or ev.kind == "noise":
            return []
        if art.status == "unconfirmed" and lk.u_rumour >= float(a["rumour_flag_p"]):
            return []
        out: list[str] = []
        for i, cat in enumerate(w.cat_ids):
            u = lk.u_cat[i]
            weights = w.cfg["categories"][cat]["weights"]
            if ev.kind == "commodity_move":
                if w.primary[cat] == ev.commodity and u < float(a["direct_p"]):
                    out.append(cat)
                elif w.primary[cat] != ev.commodity and weights.get(ev.commodity, 0) > 0 and u < float(a["secondary_p"]):
                    out.append(cat)
            elif ev.kind == "tariff":
                tier1 = w.primary[cat] == ev.commodity and any(k.cat_id == cat and w.suppliers[k.supplier_id].country == ev.country for k in w.contracts)
                if tier1 and u < float(a["tariff_p"]):
                    out.append(cat)
            elif ev.kind == "supplier_event":
                if ev.supplier_id and cat in w.suppliers[ev.supplier_id].categories and u < float(a["direct_p"]):
                    out.append(cat)
                elif ev.lookalike_of and cat in w.suppliers[ev.lookalike_of].categories and lk.u_lookalike < float(a["lookalike_fooled_p"]):
                    out.append(cat)
        return out

    # ----- the market desk resolves a held message -----

    def desk_facts(self, art: Article) -> Facts | None | Literal["unresolved"]:
        if self.luck.person("desk", art.msg.msg_id) >= float(self.p["desk_resolves_p"]):
            return "unresolved"
        ev = self.w.events[art.event_id]
        if ev.kind == "noise" or (ev.kind == "supplier_event" and ev.supplier_id is None):
            return None
        status = art.status
        return Facts(ev.kind, status, ev.commodity, ev.country, ev.supplier_id, ev.magnitude, ev.event if status != "withdrawn" else None, (), "desk")  # type: ignore[arg-type]

    # ----- a category manager decides on a card -----

    def truth_for(self, msg_id: str, cat: str) -> tuple[str, Impact | None]:
        ev_id = self.w.by_msg[msg_id].event_id
        return ev_id, self.w.impacts.get((ev_id, cat))

    def manager_decides(self, msg_id: str, cat: str) -> tuple[str, str | None]:
        ev_id, imp = self.truth_for(msg_id, cat)
        u = self.luck.person("manager", ev_id, cat)
        if imp is not None:
            return ("accept", None) if u < float(self.p["accept_right_p"]) else ("dismiss", "not_relevant")
        if u < float(self.p["dismiss_right_p"]):
            return "dismiss", ("within_tolerance" if (ev_id, cat) in self.w.near_misses else "not_relevant")
        return "accept", None

    def lever_right(self, ev_id: str, cat: str, card_lever: str, imp: Impact) -> bool:
        if card_lever == "review":
            return self.luck.person("pick", ev_id, cat) < float(self.p["pick_lever_right_p"])
        if card_lever == imp.lever:
            return True
        return self.luck.person("catch", ev_id, cat) < float(self.p["catch_wrong_lever_p"])

    def value(self, imp: Impact, at_h: float, right_lever: bool) -> float:
        delay_days = max(0.0, (at_h - imp.start_h) / 24)
        decay = max(0.0, 1.0 - delay_days / imp.horizon_days)
        return imp.at_stake_eur * decay * (1.0 if right_lever else float(self.w.cfg["wrong_lever_factor"]))

    # ----- the monthly category review, the same in every design -----

    def monthly_finds(self, ev_id: str, cat: str) -> bool:
        return self.luck.person("monthly", ev_id, cat) < float(self.p["monthly_review_finds_p"])
