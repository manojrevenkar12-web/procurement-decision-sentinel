"""Small fixtures: hand-made master data and a reader that returns what a test tells it to."""

from __future__ import annotations

import json
from typing import Any

from sentinel import config
from sentinel.domain import CategoryMD, ContractMD, MasterData, Message, Prompt, Reply, SupplierMD, Tier2MD


def md() -> MasterData:
    cats = {
        "cable": CategoryMD("cable", "Copper cable", 20e6, {"copper": 0.5}, 0),
        "extr": CategoryMD("extr", "Aluminium extrusions", 10e6, {"aluminium": 0.6}, 1),
        "motors": CategoryMD("motors", "Electric motors", 8e6, {"copper": 0.25, "aluminium": 0.1}, 1),
    }
    sups = {
        "S1": SupplierMD("S1", "Nordwerk Metall GmbH", "DE"),
        "S2": SupplierMD("S2", "Krasline Components Co., Ltd.", "CN"),
        "S3": SupplierMD("S3", "Halden Cast S.p.A.", "IT"),
        "S4": SupplierMD("S4", "Orviflow Works s.r.o.", "CZ"),
    }
    cons = (
        ContractMD("K1", "S1", "cable", 16e6, "index_linked", "copper", 100),
        ContractMD("K2", "S3", "cable", 4e6, "fixed", None, 300),
        ContractMD("K3", "S2", "extr", 6e6, "fixed", None, 30),
        ContractMD("K4", "S3", "extr", 4e6, "fixed", None, 30),
        ContractMD("K5", "S4", "motors", 8e6, "fixed", None, 60),
    )
    t2 = (Tier2MD("S4", "aluminium", "CN", 0.8),)
    return MasterData(cats, sups, cons, t2)


def msg(mid: str, headline: str, body: str, h: float = 10.0) -> Message:
    return Message(mid, "Test Wire", h, headline, body)


class ScriptedReader:
    """Returns the scripted reply for a message id (a dict becomes JSON; a string is returned as is)."""

    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    def read(self, prompt: Prompt) -> Reply:
        self.calls.append(prompt.msg_id)
        r = self.replies[prompt.msg_id]
        if isinstance(r, list):
            r = r[min(prompt.attempt, len(r) - 1)]
        text = r if isinstance(r, str) else json.dumps(r)
        return Reply(text, 1000, 800, 100, 1.0)


def cfg() -> dict[str, Any]:
    return config.platform()


COPPER_BODY = "LME copper prices rose 8.0% over the week as inventories fell. Buyers watched the market closely."
COPPER_READ = {
    "kind": "commodity_move",
    "commodity": "LME copper",
    "magnitude_pct": 8.0,
    "status": "confirmed",
    "evidence": [
        {"field": "commodity", "quote": "LME copper prices rose 8.0% over the week as inventories fell."},
        {"field": "magnitude", "quote": "LME copper prices rose 8.0% over the week as inventories fell."},
    ],
}
