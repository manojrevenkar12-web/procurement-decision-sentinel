"""A typed knowledge graph over the buyer's own data, and the walk from a checked signal to money at stake.

Nodes: category, supplier, contract, commodity, country. Edges:
  contract -FOR-> category, contract -WITH-> supplier, supplier -LOCATED_IN-> country,
  category -CONTAINS(weight)-> commodity, contract -INDEXED_TO-> commodity,
  supplier -SOURCES(share)-> commodity@country  (tier 2, from supplier disclosures).
Every exposure carries the path that produced it, so a card can show why it exists.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..domain import ContractMD, Exposure, Facts, MasterData
from .playbook import choose_lever


@dataclass(frozen=True)
class Edge:
    src: str
    rel: str
    dst: str
    weight: float | None = None


def eur(x: float) -> str:
    return f"EUR {x / 1000:,.0f}k"


class KnowledgeGraph:
    def __init__(self, md: MasterData, cfg: dict[str, Any], tier2: bool = True) -> None:
        self.md = md
        self.cfg = cfg
        self.use_tier2 = tier2
        self.by_supplier: dict[str, list[ContractMD]] = defaultdict(list)
        self.by_category: dict[str, list[ContractMD]] = defaultdict(list)
        for k in md.contracts:
            self.by_supplier[k.supplier_id].append(k)
            self.by_category[k.cat_id].append(k)
        self.tier2 = {(t.supplier_id, t.commodity, t.country): t for t in md.tier2} if tier2 else {}
        self.primary = {c.cat_id: (max(c.weights, key=c.weights.__getitem__) if c.weights else None) for c in md.categories.values()}

    def edges(self) -> list[Edge]:
        out: list[Edge] = []
        for c in self.md.categories.values():
            out += [Edge(f"category:{c.cat_id}", "CONTAINS", f"commodity:{k}", w) for k, w in c.weights.items()]
        for s in self.md.suppliers.values():
            out.append(Edge(f"supplier:{s.supplier_id}", "LOCATED_IN", f"country:{s.country}"))
        for k in self.md.contracts:
            out.append(Edge(f"contract:{k.contract_id}", "FOR", f"category:{k.cat_id}", k.annual_spend_eur))
            out.append(Edge(f"contract:{k.contract_id}", "WITH", f"supplier:{k.supplier_id}"))
            if k.index_commodity:
                out.append(Edge(f"contract:{k.contract_id}", "INDEXED_TO", f"commodity:{k.index_commodity}"))
        for t in self.tier2.values():
            out.append(Edge(f"supplier:{t.supplier_id}", "SOURCES", f"commodity:{t.commodity}@{t.country}", t.share))
        return out

    def _sup(self, sid: str) -> str:
        s = self.md.suppliers[sid]
        return f"{s.legal_name} ({s.country})"

    def _factor(self, k: ContractMD, commodity: str, day: float) -> tuple[float, str]:
        if k.mechanism == "index_linked" and k.index_commodity == commodity:
            return 1.0, "index-linked: passes through now"
        if k.mechanism == "cost_plus":
            return float(self.cfg["cost_plus_pass"]), "cost-plus: passes through"
        if k.renewal_day is not None and 0 <= k.renewal_day - day <= float(self.cfg["renewal_window_days"]):
            return 1.0, f"fixed price, renews in {k.renewal_day - day:.0f} days"
        return 0.0, "fixed price beyond the renewal window"

    def exposures(self, f: Facts, day: float) -> list[Exposure]:
        parts: dict[str, list[tuple[float, ContractMD, list[str], dict[str, Any]]]] = defaultdict(list)
        if f.kind == "commodity_move":
            assert f.commodity and f.magnitude is not None
            for k in self.md.contracts:
                w = self.md.categories[k.cat_id].weights.get(f.commodity, 0.0)
                if w <= 0:
                    continue
                factor, why = self._factor(k, f.commodity, day)
                imp = k.annual_spend_eur * w * f.magnitude * factor
                path = [
                    f"{f.commodity} {f.magnitude * 100:+.1f}%",
                    f"{w:.0%} of {self.md.categories[k.cat_id].label} cost (should-cost)",
                    f"contract {k.contract_id} with {self._sup(k.supplier_id)}, {eur(k.annual_spend_eur)}/yr, {why}",
                ]
                mech = "index_linked" if k.mechanism == "index_linked" and k.index_commodity == f.commodity else ("cost_plus" if k.mechanism == "cost_plus" else "fixed")
                parts[k.cat_id].append((imp, k, path, {"kind": "commodity_move", "mechanism": mech}))
        elif f.kind == "tariff":
            assert f.commodity and f.country and f.magnitude is not None
            for k in self.md.contracts:
                s = self.md.suppliers[k.supplier_id]
                if s.country == f.country and self.primary[k.cat_id] == f.commodity:
                    alt = any(self.md.suppliers[a.supplier_id].country != f.country for a in self.by_category[k.cat_id])
                    path = [
                        f"EU tariff {f.magnitude:.0%} on {f.commodity} from {f.country}",
                        f"{self._sup(k.supplier_id)} ships {f.commodity} from {f.country}",
                        f"contract {k.contract_id}, {eur(k.annual_spend_eur)}/yr",
                    ]
                    parts[k.cat_id].append((k.annual_spend_eur * f.magnitude, k, path, {"kind": "tariff", "alternate_outside_country": alt}))
                elif (k.supplier_id, f.commodity, f.country) in self.tier2:
                    t = self.tier2[(k.supplier_id, f.commodity, f.country)]
                    w = self.md.categories[k.cat_id].weights.get(f.commodity, 0.0)
                    if w <= 0:
                        continue
                    path = [
                        f"EU tariff {f.magnitude:.0%} on {f.commodity} from {f.country}",
                        f"tier 2: {self._sup(k.supplier_id)} buys {t.share:.0%} of its {f.commodity} from {f.country} (disclosure)",
                        f"{w:.0%} of {self.md.categories[k.cat_id].label} cost",
                        f"contract {k.contract_id}, {eur(k.annual_spend_eur)}/yr",
                    ]
                    parts[k.cat_id].append((k.annual_spend_eur * w * t.share * f.magnitude, k, path, {"kind": "tariff", "alternate_outside_country": False}))
        elif f.kind == "supplier_event":
            assert f.supplier_id and f.event
            stake = self.cfg["supplier_event_stake"][f.event]
            spend = {c: sum(x.annual_spend_eur for x in ks) for c, ks in self.by_category.items()}
            for k in self.by_supplier[f.supplier_id]:
                share = k.annual_spend_eur / spend[k.cat_id]
                single = share >= float(self.cfg["single_source_share"])
                imp = k.annual_spend_eur * float(stake["single" if single else "multi"])
                path = [
                    f"{f.event} at {self._sup(f.supplier_id)}",
                    f"contract {k.contract_id}: {share:.0%} of {self.md.categories[k.cat_id].label}" + (" (main source)" if single else ""),
                    f"{eur(k.annual_spend_eur)}/yr at risk",
                ]
                parts[k.cat_id].append((imp, k, path, {"kind": "supplier_event", "event": f.event, "share": share}))
        out: list[Exposure] = []
        for cat, ps in parts.items():
            total = sum(p[0] for p in ps)
            if abs(total) < 1.0:
                continue
            top = max(ps, key=lambda p: abs(p[0]))
            lever = choose_lever(self.cfg["playbook"], top[3])
            full = (*top[2], f"{self.md.categories[cat].label}: {eur(total)} a year" + (f" across {len(ps)} contracts" if len(ps) > 1 else ""))
            out.append(Exposure(cat, total, lever, full, top[1].contract_id))
        return sorted(out, key=lambda e: -abs(e.impact_eur))
