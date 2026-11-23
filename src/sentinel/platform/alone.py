"""The model-alone design: the model reads each article and names the categories; every named category becomes a card.

No quote check, no graph, no money, no memory and no deduplication. It is what a quick integration would ship.
"""

from __future__ import annotations

from typing import Any

from ..domain import Card, MasterData, Message
from .prompt import build_prompt
from .readers import Reader
from .validate import cost_eur, read_signal


class ModelAlone:
    def __init__(self, md: MasterData, cfg: dict[str, Any], reader: Reader, model: str) -> None:
        self.md = md
        self.cfg = cfg
        self.reader = reader
        self.price = cfg["pricing"][model]
        self.cards: dict[str, Card] = {}
        self.cost_eur = 0.0
        self.model_calls = 0

    def handle(self, msg: Message, now_h: float) -> list[str]:
        rr = read_signal(self.reader, build_prompt(msg, "alone", self.md), int(self.cfg["reader"]["max_repairs"]))
        self.cost_eur += cost_eur(rr, self.price)
        self.model_calls += rr.attempts
        if rr.read is None or rr.read.urgency == "low":
            return []
        out = []
        for cat in rr.read.affected_categories:
            if cat not in self.md.categories:
                continue
            card = Card(
                f"C{len(self.cards) + 1:05d}",
                f"{msg.msg_id}|{cat}",
                cat,
                f"{rr.read.kind}",
                rr.read.kind,
                0.0,
                "review",
                (),
                tuple((msg.msg_id, e.quote) for e in rr.read.evidence),
                [msg.msg_id],
                now_h,
                self.md.categories[cat].manager,
            )
            self.cards[card.card_id] = card
            out.append(card.card_id)
        return out
