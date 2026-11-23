"""The simulated buyer and its market for one seed. The only place the truth exists.

The sentinel sees `master_data()` (with should-cost weight estimates and only the disclosed tier-2 links) and
`messages()`. Everything else here - true weights, every tier-2 link, tolerances, capacities, rumour outcomes,
namesakes and injections - is for the simulation and the evaluation only.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..domain import CategoryMD, ContractMD, MasterData, Message, SupplierMD, Tier2MD
from ..rng import keyed
from . import texts

WORLD_YML = Path(__file__).resolve().parents[3] / "config" / "world.yml"

STEM_A = [
    "Nord",
    "Ost",
    "Rhein",
    "Elb",
    "Halden",
    "Vistra",
    "Kras",
    "Tauro",
    "Ister",
    "Marlo",
    "Bren",
    "Kalt",
    "Sundra",
    "Orvi",
    "Peka",
    "Lumo",
    "Vesta",
    "Doran",
    "Cara",
    "Tessa",
    "Brava",
    "Silva",
    "Arno",
    "Kora",
]
STEM_B = ["werk", "stahl", "form", "tec", "plast", "pack", "line", "cast", "flow", "wire", "print", "trans", "gas", "chem"]
STEM_C = ["Metall", "Polymer", "Logistik", "Industrie", "Components", "Packaging", "Systems", "Works"]
NOISE_ADJ = ["German", "French", "Dutch", "Spanish", "Swedish"]


@cache
def load_world_cfg(variant: str) -> dict[str, Any]:
    cfg = yaml.safe_load(WORLD_YML.read_text(encoding="utf-8"))
    held = cfg.pop("heldout")
    if variant == "heldout":
        for k, v in held.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    return dict(cfg)


@dataclass
class TrueSupplier:
    supplier_id: str
    stem: str
    legal_name: str
    country: str
    lookalike_name: str | None
    lookalike_country: str | None
    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrueContract:
    contract_id: str
    supplier_id: str
    cat_id: str
    share: float
    spend: float
    mechanism: str
    index_commodity: str | None
    renewal_day: int
    has_capacity: bool


@dataclass(frozen=True)
class TrueTier2:
    supplier_id: str
    commodity: str
    country: str
    share: float
    disclosed: bool


@dataclass
class Event:
    event_id: str
    kind: str  # commodity_move | tariff | supplier_event | noise
    start_h: float
    commodity: str | None = None
    country: str | None = None
    supplier_id: str | None = None  # ours, or None for a namesake or an unrelated company
    company: str | None = None  # the name as written
    company_country: str | None = None
    magnitude: float | None = None
    event: str | None = None
    rumour: bool = False
    outcome: str = "confirmed"  # confirmed | withdrawn
    lookalike_of: str | None = None

    @property
    def real(self) -> bool:
        return self.outcome == "confirmed" and self.kind != "noise"


@dataclass
class Article:
    msg: Message
    event_id: str
    status: str
    sentences: dict[str, str]
    names: dict[str, str]
    copy_of: str | None = None
    injection_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class Impact:
    event_id: str
    cat_id: str
    impact_eur: float
    material: bool
    at_stake_eur: float
    horizon_days: float
    lever: str
    start_h: float
    tier2_only: bool = False


class World:
    def __init__(self, seed: int, variant: str = "dev") -> None:
        self.seed = seed
        self.variant = variant
        self.cfg = copy.deepcopy(load_world_cfg(variant))
        rng = keyed(seed, variant, "world")
        self.cat_ids = list(self.cfg["categories"])
        self.primary = {c: (max(v["weights"], key=v["weights"].get) if v["weights"] else None) for c, v in self.cfg["categories"].items()}
        self.spend = {c: float(v["spend_m"]) * 1e6 for c, v in self.cfg["categories"].items()}
        lo, hi = self.cfg["materiality"]["tolerance_pct"]
        self.tolerance = {c: max(float(self.cfg["materiality"]["threshold_eur"]), float(rng.uniform(lo, hi)) * self.spend[c]) for c in self.cat_ids}
        self.suppliers: dict[str, TrueSupplier] = {}
        self.contracts: list[TrueContract] = []
        self.tier2: list[TrueTier2] = []
        self._build_suppliers(rng)
        self.events: dict[str, Event] = {}
        self.articles: list[Article] = []
        self._build_events(rng)
        self.impacts: dict[tuple[str, str], Impact] = {}
        self.near_misses: dict[tuple[str, str], float] = {}
        for ev in self.events.values():
            self._impacts(ev)
        self.by_msg = {a.msg.msg_id: a for a in self.articles}

    # ---------- suppliers and contracts ----------

    def _new_supplier(self, rng: np.random.Generator, used: set[str]) -> TrueSupplier:
        sc = self.cfg["supplier_countries"]
        countries = list(sc)
        country = str(rng.choice(countries, p=np.array(list(sc.values())) / sum(sc.values())))
        while True:
            stem = f"{rng.choice(STEM_A)}{rng.choice(STEM_B)} {rng.choice(STEM_C)}"
            if stem not in used:
                used.add(stem)
                break
        form = str(rng.choice(self.cfg["countries"][country]["legal"]))
        look_name = look_country = None
        if rng.random() < float(self.cfg["suppliers"]["lookalike_p"]):
            look_country = str(rng.choice([c for c in countries if c != country]))
            look_name = f"{stem} {rng.choice(self.cfg['countries'][look_country]['legal'])}"
        sid = f"S{len(self.suppliers) + 1:03d}"
        s = TrueSupplier(sid, stem, f"{stem} {form}", country, look_name, look_country)
        self.suppliers[sid] = s
        return s

    def _build_suppliers(self, rng: np.random.Generator) -> None:
        scfg = self.cfg["suppliers"]
        ccfg = self.cfg["contracts"]
        used: set[str] = set()
        mech_names = list(ccfg["mechanism"])
        mech_p = np.array(list(ccfg["mechanism"].values()), dtype=float)
        for cat in self.cat_ids:
            n = int(rng.choice(scfg["per_category"]))
            if rng.random() < float(scfg["dominant_p"]):
                rest = rng.dirichlet(np.ones(n - 1) * 2) * (1 - float(scfg["dominant_share"]))
                shares = np.concatenate([[float(scfg["dominant_share"])], rest])
            else:
                shares = rng.dirichlet(np.ones(n) * 2)
            for share in shares:
                others = [s for s in self.suppliers.values() if cat not in s.categories]
                if others and rng.random() < float(scfg["shared_p"]):
                    sup = others[int(rng.integers(len(others)))]
                else:
                    sup = self._new_supplier(rng, used)
                sup.categories.append(cat)
                mech = str(rng.choice(mech_names, p=mech_p / mech_p.sum()))
                if self.primary[cat] is None and mech == "index_linked":
                    mech = "fixed"
                lo, hi = ccfg["renewal_days"]
                self.contracts.append(
                    TrueContract(
                        contract_id=f"K{len(self.contracts) + 1:04d}",
                        supplier_id=sup.supplier_id,
                        cat_id=cat,
                        share=float(share),
                        spend=float(share) * self.spend[cat],
                        mechanism=mech,
                        index_commodity=self.primary[cat] if mech == "index_linked" else None,
                        renewal_day=int(rng.integers(lo, hi + 1)),
                        has_capacity=bool(rng.random() < float(scfg["alt_capacity_p"])),
                    )
                )
        tariff_countries = list(self.cfg["tariff_countries"])
        lo, hi = scfg["tier2_share"]
        for s in self.suppliers.values():
            commodity = self.primary[s.categories[0]]
            if commodity is None or s.country in tariff_countries:
                continue
            if rng.random() < float(scfg["tier2_p"]):
                self.tier2.append(TrueTier2(s.supplier_id, commodity, str(rng.choice(tariff_countries)), float(rng.uniform(lo, hi)), bool(rng.random() < float(scfg["disclosure_p"]))))
        wrng = keyed(self.seed, self.variant, "should-cost")
        self.weight_estimates = {c: {k: round(float(w) * float(np.exp(wrng.normal(0, 0.2))), 3) for k, w in self.cfg["categories"][c]["weights"].items()} for c in self.cat_ids}

    def master_data(self) -> MasterData:
        cats = {c: CategoryMD(c, self.cfg["categories"][c]["label"], self.spend[c], dict(self.weight_estimates[c]), i % int(self.cfg["managers"])) for i, c in enumerate(self.cat_ids)}
        sups = {s.supplier_id: SupplierMD(s.supplier_id, s.legal_name, s.country) for s in self.suppliers.values()}
        cons = tuple(ContractMD(k.contract_id, k.supplier_id, k.cat_id, k.spend, k.mechanism, k.index_commodity, k.renewal_day) for k in self.contracts)  # type: ignore[arg-type]
        t2 = tuple(Tier2MD(t.supplier_id, t.commodity, t.country, t.share) for t in self.tier2 if t.disclosed)
        return MasterData(cats, sups, cons, t2)

    # ---------- events and articles ----------

    def _add(self, rng: np.random.Generator, ev: Event, h: float, status: str, headline: str, body: str, sentences: dict[str, str], names: dict[str, str]) -> None:
        inj: tuple[str, ...] = ()
        if rng.random() < float(self.cfg["injection_p"]):
            k = int(rng.integers(1, 3))
            inj = tuple(str(x) for x in rng.choice(self.cat_ids, size=k, replace=False))
            body = body + " " + texts.injection_sentence([self.cfg["categories"][c]["label"] for c in inj])
        src = str(rng.choice(texts.SOURCES))
        art = Article(Message("", src, h, headline, body), ev.event_id, status, sentences, names, None, inj)
        self.articles.append(art)
        syn = self.cfg["syndication"]
        if rng.random() < float(syn["p"]):
            for _ in range(int(rng.choice(syn["copies"]))):
                ch = h + float(rng.uniform(0.2, float(syn["within_h"])))
                src2 = str(rng.choice([s for s in texts.SOURCES if s != src]))
                variant = int(rng.integers(3))
                if variant == 0:
                    b2, hl2 = body, "UPDATE: " + headline
                elif variant == 1:
                    b2, hl2 = (
                        body.replace("Buyers watched the market closely.", "Market participants said volumes were thin.").replace("Customers are assessing the impact.", "Customers said they were reviewing supply."),
                        headline,
                    )
                else:
                    b2, hl2 = sentences.get("commodity") or sentences.get("supplier") or body, headline + " - report"
                    if inj:
                        b2 = b2 + " " + texts.injection_sentence([self.cfg["categories"][c]["label"] for c in inj])
                self.articles.append(Article(Message("", src2, ch, hl2, b2), ev.event_id, status, sentences, names, "pending", inj))

    def _build_events(self, rng: np.random.Generator) -> None:
        cfg = self.cfg
        horizon = int(cfg["horizon_days"])
        commodities = list(cfg["commodities"])
        rates = cfg["rates"]
        wave = cfg.get("tariff_wave")
        tariff_commodities = sorted({p for p in self.primary.values() if p})
        lookalikes = [s for s in self.suppliers.values() if s.lookalike_name]
        exposed = sorted(
            {(self.suppliers[k.supplier_id].country, self.primary[k.cat_id]) for k in self.contracts if self.primary[k.cat_id] and self.suppliers[k.supplier_id].country in cfg["tariff_countries"]} | {(t.country, t.commodity) for t in self.tier2}
        )
        sup_events = list(cfg["supplier_events"])
        sup_p = np.array([cfg["supplier_events"][e]["p"] for e in sup_events], dtype=float)

        def eid() -> str:
            return f"E{len(self.events) + 1:04d}"

        for day in range(horizon):
            n_t = int(rng.poisson(rates["tariff"])) + (int(wave["count"]) if wave and int(wave["day"]) == day else 0)
            plan = [
                ("commodity_move", int(rng.poisson(rates["commodity_move"]))),
                ("tariff", n_t),
                ("supplier_event", int(rng.poisson(rates["supplier_event"]))),
                ("noise", int(rng.poisson(rates["noise"]))),
            ]
            for kind, n in plan:
                for _ in range(n):
                    h = day * 24 + float(rng.uniform(6, 20))
                    ev = Event(eid(), kind, h)
                    self.events[ev.event_id] = ev
                    if kind == "commodity_move":
                        c = str(rng.choice(commodities))
                        sigma = float(cfg["commodities"][c]["weekly_sigma"])
                        ev.commodity = c
                        ev.magnitude = float(np.sign(rng.random() - 0.4) * min(0.25, 0.015 + rng.exponential(sigma)))
                        hl, body, sent, name = texts.commodity_article(rng, c, ev.magnitude, bool(rng.random() < float(cfg["forward_hedge_p"])))
                        self._add(rng, ev, h, "confirmed", hl, body, sent, {"commodity": name})
                    elif kind == "tariff":
                        if exposed and rng.random() < float(cfg["tariff_targets_exposure_p"]):
                            ev.country, ev.commodity = exposed[int(rng.integers(len(exposed)))]
                        else:
                            ev.country = str(rng.choice(cfg["tariff_countries"]))
                            ev.commodity = str(rng.choice(tariff_commodities))
                        ev.magnitude = float(rng.choice([0.1, 0.15, 0.2, 0.25]))
                        tc = str(ev.commodity)
                        ev.rumour = bool(rng.random() < float(cfg["rumour"]["tariff_p"]))
                        country = cfg["countries"][ev.country]
                        names = {"country": country["name"], "magnitude": texts.fmt_pct(ev.magnitude)}
                        if ev.rumour:
                            ev.outcome = "confirmed" if rng.random() < float(cfg["rumour"]["confirm_p"]) else "withdrawn"
                            hl, body, sent, cname = texts.tariff_article(rng, tc, country, ev.magnitude, "unconfirmed")
                            self._add(rng, ev, h, "unconfirmed", hl, body, sent, {**names, "commodity": cname})
                            h2 = h + 24 * float(rng.uniform(*cfg["rumour"]["follow_up_days"]))
                            hl, body, sent, cname = texts.tariff_article(rng, tc, country, ev.magnitude, ev.outcome)
                            self._add(rng, ev, h2, ev.outcome, hl, body, sent, {**names, "commodity": cname})
                        else:
                            hl, body, sent, cname = texts.tariff_article(rng, tc, country, ev.magnitude, "confirmed")
                            self._add(rng, ev, h, "confirmed", hl, body, sent, {**names, "commodity": cname})
                    elif kind == "supplier_event":
                        ev.event = str(rng.choice(sup_events, p=sup_p / sup_p.sum()))
                        if lookalikes and rng.random() < float(cfg["supplier_event_about_lookalike_p"]):
                            s = lookalikes[int(rng.integers(len(lookalikes)))]
                            ev.company, ev.company_country, ev.lookalike_of = s.lookalike_name, s.lookalike_country, s.supplier_id
                        else:
                            ss = list(self.suppliers.values())
                            s = ss[int(rng.integers(len(ss)))]
                            ev.supplier_id, ev.company, ev.company_country = s.supplier_id, s.legal_name, s.country
                        assert ev.company and ev.company_country
                        product = self.cfg["categories"][s.categories[0]]["label"].lower()
                        adj = cfg["countries"][ev.company_country]["adj"]
                        names = {"supplier": ev.company, "supplier_country": adj}
                        ev.rumour = bool(rng.random() < float(cfg["rumour"]["supplier_p"]))
                        if ev.rumour:
                            ev.outcome = "confirmed" if rng.random() < float(cfg["rumour"]["confirm_p"]) else "withdrawn"
                            hl, body, sent = texts.supplier_article(ev.company, adj, product, ev.event, "unconfirmed")
                            self._add(rng, ev, h, "unconfirmed", hl, body, sent, names)
                            h2 = h + 24 * float(rng.uniform(*cfg["rumour"]["follow_up_days"]))
                            hl, body, sent = texts.supplier_article(ev.company, adj, product, ev.event, ev.outcome)
                            self._add(rng, ev, h2, ev.outcome, hl, body, sent, names)
                        else:
                            hl, body, sent = texts.supplier_article(ev.company, adj, product, ev.event, "confirmed")
                            self._add(rng, ev, h, "confirmed", hl, body, sent, names)
                    else:
                        if rng.random() < 0.5:
                            c = str(rng.choice(cfg["other_commodities"]))
                            m = float(np.sign(rng.random() - 0.5) * (0.015 + rng.exponential(0.03)))
                            hl, body, sent, name = texts.commodity_article(rng, c, m, False, {c: [c]})
                            ev.commodity, ev.magnitude = c, m
                            self._add(rng, ev, h, "confirmed", hl, body, sent, {"commodity": name})
                        else:
                            name = f"{rng.choice(STEM_A)}{rng.choice(['mart', 'shop', 'foods', 'home'])} plc"
                            hl, body = texts.noise_company_article(name, str(rng.choice(NOISE_ADJ)))
                            ev.company = name
                            self._add(rng, ev, h, "confirmed", hl, body, {}, {})
        self.articles = [a for a in self.articles if a.msg.published_h < horizon * 24]
        seen = {(a.event_id, a.status) for a in self.articles}
        for ev in self.events.values():
            if ev.rumour and (ev.event_id, ev.outcome) not in seen:
                ev.outcome = "pending"  # resolved after the horizon: nobody could know, so it is not graded
        self.articles.sort(key=lambda a: a.msg.published_h)
        first: dict[tuple[str, str], str] = {}
        for i, a in enumerate(self.articles):
            mid = f"M{i + 1:05d}"
            a.msg = Message(mid, a.msg.source, round(a.msg.published_h, 3), a.msg.headline, a.msg.body)
            k = (a.event_id, a.status)
            if a.copy_of is not None:
                a.copy_of = first.get(k)
            else:
                first.setdefault(k, mid)

    # ---------- the truth: who is hit, how hard, and the right lever ----------

    def contract_commodity_factor(self, k: TrueContract, commodity: str, day: float) -> float:
        if k.mechanism == "index_linked" and k.index_commodity == commodity:
            return 1.0
        if k.mechanism == "cost_plus":
            return float(self.cfg["contracts"]["cost_plus_pass"])
        until = k.renewal_day - day
        return 1.0 if 0 <= until <= float(self.cfg["renewal_window_days"]) else 0.0

    def _impacts(self, ev: Event) -> None:
        if not ev.real or (ev.kind == "supplier_event" and ev.supplier_id is None):
            return  # nothing happened to us: a rumour that died, noise, or a namesake
        cfg = self.cfg
        day = ev.start_h / 24
        per_cat: dict[str, list[tuple[float, TrueContract, bool]]] = {}
        if ev.kind == "commodity_move":
            assert ev.commodity and ev.magnitude is not None
            for k in self.contracts:
                w = float(cfg["categories"][k.cat_id]["weights"].get(ev.commodity, 0.0))
                if w > 0:
                    per_cat.setdefault(k.cat_id, []).append((k.spend * w * ev.magnitude * self.contract_commodity_factor(k, ev.commodity, day), k, False))
            horizon, mitigable = cfg["price_events"]["commodity_move"]["horizon_days"], cfg["price_events"]["commodity_move"]["mitigable"]
        elif ev.kind == "tariff":
            assert ev.commodity and ev.magnitude is not None
            t2 = {t.supplier_id: t for t in self.tier2 if t.commodity == ev.commodity and t.country == ev.country}
            for k in self.contracts:
                sup = self.suppliers[k.supplier_id]
                if sup.country == ev.country and self.primary[k.cat_id] == ev.commodity:
                    per_cat.setdefault(k.cat_id, []).append((k.spend * ev.magnitude, k, False))
                elif k.supplier_id in t2:
                    w = float(cfg["categories"][k.cat_id]["weights"].get(ev.commodity, 0.0))
                    if w > 0:
                        per_cat.setdefault(k.cat_id, []).append((k.spend * w * t2[k.supplier_id].share * ev.magnitude, k, True))
            horizon, mitigable = cfg["price_events"]["tariff"]["horizon_days"], cfg["price_events"]["tariff"]["mitigable"]
        else:
            assert ev.supplier_id and ev.event
            se = cfg["supplier_events"][ev.event]
            for k in self.contracts:
                if k.supplier_id == ev.supplier_id:
                    single = k.share >= 0.5
                    per_cat.setdefault(k.cat_id, []).append((k.spend * float(se["stake_single" if single else "stake_multi"]), k, False))
            horizon, mitigable = se["horizon_days"], se["mitigable"]
        for cat, parts in per_cat.items():
            total = sum(p[0] for p in parts)
            if abs(total) < 1.0:
                continue
            if ev.kind == "supplier_event":
                material = total >= float(cfg["materiality"]["threshold_eur"]) or ev.event == "sanction"
            else:
                material = abs(total) >= self.tolerance[cat]
            lever = self._lever(ev, cat, parts)
            imp = Impact(ev.event_id, cat, total, material, abs(total) * float(mitigable), float(horizon), lever, ev.start_h, all(p[2] for p in parts))
            if material:
                self.impacts[(ev.event_id, cat)] = imp
            else:
                self.near_misses[(ev.event_id, cat)] = total

    def _lever(self, ev: Event, cat: str, parts: list[tuple[float, TrueContract, bool]]) -> str:
        top = max(parts, key=lambda p: abs(p[0]))
        k = top[1]
        if ev.kind == "commodity_move":
            if (k.mechanism == "index_linked" and k.index_commodity == ev.commodity) or k.mechanism == "cost_plus":
                return "index_pass_through_check"
            return "renewal_should_cost"
        if ev.kind == "tariff":
            if not top[2]:
                alts = [a for a in self.contracts if a.cat_id == cat and self.suppliers[a.supplier_id].country != ev.country and a.has_capacity]
                if alts:
                    return "shift_volume"
            return "landed_cost_requote"
        if ev.event == "sanction":
            return "stop_new_pos"
        if ev.event == "esg":
            return "corrective_action_plan"
        return "dual_source_buffer" if k.share >= 0.5 else "qualify_alternate"

    # ---------- views ----------

    def messages(self) -> list[Message]:
        return [a.msg for a in self.articles]

    def manager_of(self, cat: str) -> int:
        return self.cat_ids.index(cat) % int(self.cfg["managers"])
