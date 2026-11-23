"""Every random draw for one seed. Designs replay the same draws.

Per message: the model's coin flips (per model), the delivery's redelivery and crashes, and the analyst's
coin flips are drawn up front. People's decisions are drawn from a key (who, what), so the same card or the same
held message gets the same decision in every design that shows it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..rng import keyed
from .world import World


@dataclass(frozen=True)
class ReaderLuck:
    u_schema: float
    u_repair: tuple[float, float]
    u_kind: float
    u_mag: float
    u_sign: float
    u_status: float
    u_drift: float
    u_drift_country: float
    u_halluc: float
    u_halluc_pick: float
    u_inject: float
    u_alone: tuple[float, ...]
    u_alone_extra: float
    u_alone_pick: float
    u_rumour: float
    u_latency: float


@dataclass(frozen=True)
class DeliveryLuck:
    redeliver: bool
    redeliver_after_h: float
    crash_after_read: bool
    crash_after_card: bool


@dataclass(frozen=True)
class AnalystLuck:
    u_cat: tuple[float, ...]
    u_lookalike: float
    u_rumour: float


@dataclass
class Luck:
    reader: dict[str, dict[str, ReaderLuck]]
    delivery: dict[str, DeliveryLuck]
    analyst: dict[str, AnalystLuck]
    seed: int
    variant: str

    def person(self, *key: object) -> float:
        """One uniform draw for a person's decision about a thing, the same whichever design asks."""
        return float(keyed(self.seed, self.variant, "person", *key).random())


def draw_luck(world: World) -> Luck:
    cfg = world.cfg
    n = len(world.cat_ids)
    d = cfg["delivery"]
    reader: dict[str, dict[str, ReaderLuck]] = {m: {} for m in cfg["models"]}
    delivery: dict[str, DeliveryLuck] = {}
    analyst: dict[str, AnalystLuck] = {}
    for msg in world.messages():
        mid = msg.msg_id
        for model in cfg["models"]:
            r = keyed(world.seed, world.variant, "reader", mid, model)
            reader[model][mid] = ReaderLuck(
                u_schema=float(r.random()),
                u_repair=(float(r.random()), float(r.random())),
                u_kind=float(r.random()),
                u_mag=float(r.random()),
                u_sign=float(r.random()),
                u_status=float(r.random()),
                u_drift=float(r.random()),
                u_drift_country=float(r.random()),
                u_halluc=float(r.random()),
                u_halluc_pick=float(r.random()),
                u_inject=float(r.random()),
                u_alone=tuple(float(x) for x in r.random(n)),
                u_alone_extra=float(r.random()),
                u_alone_pick=float(r.random()),
                u_rumour=float(r.random()),
                u_latency=float(r.random()),
            )
        r = keyed(world.seed, world.variant, "delivery", mid)
        delivery[mid] = DeliveryLuck(
            redeliver=bool(r.random() < float(d["redeliver_p"])),
            redeliver_after_h=float(r.uniform(*d["redeliver_after_h"])),
            crash_after_read=bool(r.random() < float(d["crash_after_read_p"])),
            crash_after_card=bool(r.random() < float(d["crash_after_card_p"])),
        )
        r = keyed(world.seed, world.variant, "analyst", mid)
        analyst[mid] = AnalystLuck(tuple(float(x) for x in r.random(n)), float(r.random()), float(r.random()))
    return Luck(reader, delivery, analyst, world.seed, world.variant)
