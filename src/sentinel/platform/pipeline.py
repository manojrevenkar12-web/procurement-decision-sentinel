"""The sentinel: one message in, at most one card per affected category out.

    delivery -> copy check -> model reads -> code checks quotes -> resolve entities -> status gate
             -> same-facts merge -> graph walk to money -> materiality -> dismissal memory -> card

The model only reads. Whether anything is shown, to whom, with what amount and what lever, is code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..domain import Card, Facts, MasterData, Message
from .evidence import Checked, Glossary, check_read
from .fingerprint import jaccard, shingles
from .graph import KnowledgeGraph
from .journal import Journal, MemoryJournal, NoJournal
from .memory import DismissalMemory
from .prompt import build_prompt
from .readers import Reader
from .resolve import resolve_supplier
from .validate import cost_eur, read_signal

DEFAULT_FLAGS = {"tier2": True, "quote_check": True, "strict_resolution": True, "hold_rumours": True, "memory": True, "journal": True, "text_dedupe": True}


class Crash(RuntimeError):
    """The worker died. The broker redelivers the message later."""


@dataclass
class Outcome:
    msg_id: str
    result: Literal["card", "no_card", "hold", "ignore", "watch", "withdrawn", "copy", "corroborated", "redelivered"]
    reason: str
    cards: list[str] = field(default_factory=list)


@dataclass
class Hold:
    msg_id: str
    held_h: float
    reason: str


class Sentinel:
    def __init__(self, md: MasterData, cfg: dict[str, Any], reader: Reader, model: str, flags: dict[str, bool] | None = None, journal: Journal | None = None) -> None:
        self.md = md
        self.cfg = cfg
        self.reader = reader
        self.model = model
        self.flags = {**DEFAULT_FLAGS, **(flags or {})}
        self.g = Glossary(cfg)
        self.graph = KnowledgeGraph(md, cfg, tier2=self.flags["tier2"])
        self.memory = DismissalMemory(float(cfg["memory"]["suppress_factor"]))
        self.journal: Journal = journal or (MemoryJournal() if self.flags["journal"] else NoJournal())
        self.price = cfg["pricing"][model]
        self.cards: dict[str, Card] = {}
        self.by_key: dict[str, str] = {}
        self.facts_seen: dict[str, tuple[float, list[str], str]] = {}
        self.recent: list[tuple[str, float, frozenset[str]]] = []
        self.holds: list[Hold] = []
        self.watches: dict[str, str] = {}
        self.msg_cards: dict[str, list[str]] = {}
        self.suppressed: list[tuple[str, str, float, str]] = []
        self.traces: dict[str, list[dict[str, Any]]] = {}
        self.log: list[Outcome] = []
        self.cost_eur = 0.0
        self.model_calls = 0

    # ---------- one delivery ----------

    def handle(self, msg: Message, now_h: float, crash: str | None = None) -> Outcome:
        sh = shingles(msg.text)
        out = self._handle(msg, now_h, crash, sh)
        if out.result != "redelivered":
            self.recent.append((msg.msg_id, now_h, sh))  # committed with the workflow; a crash loses it
        return out

    def _handle(self, msg: Message, now_h: float, crash: str | None, sh: frozenset[str]) -> Outcome:
        mid = msg.msg_id
        st = self.journal.get(mid)
        if st.get("done"):
            return self._out(Outcome(mid, "redelivered", "already handled; nothing to do"))
        spans = self.traces.setdefault(mid, [])
        dd = self.cfg["dedupe"]
        if self.flags["text_dedupe"] and "read" not in st:
            for oid, oh, osh in reversed(self.recent):
                if now_h - oh > float(dd["text_window_h"]):
                    break
                sim = jaccard(sh, osh)
                if sim >= float(dd["text_jaccard"]):
                    linked = self._corroborate(self.msg_cards.get(oid, []), mid)
                    self.msg_cards[mid] = self.msg_cards.get(oid, [])
                    spans.append({"step": "copy_check", "copy_of": oid, "similarity": round(sim, 3), "cards_linked": linked})
                    self.journal.put(mid, "done", True)
                    return self._out(Outcome(mid, "copy", f"syndicated copy of {oid}"))
        if "read" in st:
            rr = st["read"]
            spans.append({"step": "read", "resumed": True, "cost_eur": 0.0})
        else:
            rr = read_signal(self.reader, build_prompt(msg), int(self.cfg["reader"]["max_repairs"]))
            c = cost_eur(rr, self.price)
            self.cost_eur += c
            self.model_calls += rr.attempts
            spans.append(
                {
                    "step": "read",
                    "model": self.model,
                    "attempts": rr.attempts,
                    "tokens_in": rr.tokens_in,
                    "tokens_cached": rr.tokens_cached,
                    "tokens_out": rr.tokens_out,
                    "latency_s": round(rr.latency_s, 2),
                    "cost_eur": round(c, 5),
                }
            )
            self.journal.put(mid, "read", rr)
        if crash == "after_read":
            spans.append({"step": "crash", "after": "read"})
            raise Crash(mid)
        if rr.read is None:
            return self._hold(msg, now_h, "the reply never matched the schema", spans)
        checked = check_read(rr.read, msg.text, msg.headline, self.g, self.flags["quote_check"])
        spans.append({"step": "check", "outcome": checked.outcome, "reason": checked.reason, "dropped": list(checked.dropped), "instruction_like": checked.instruction_like})
        if checked.outcome == "ignore":
            self.journal.put(mid, "done", True)
            return self._out(Outcome(mid, "ignore", checked.reason))
        if checked.outcome == "hold":
            return self._hold(msg, now_h, checked.reason, spans)
        facts = self._facts(checked, msg, now_h, spans)
        if isinstance(facts, Outcome):
            return facts
        return self._decide(mid, facts, now_h, crash, st, spans)

    def _facts(self, c: Checked, msg: Message, now_h: float, spans: list[dict[str, Any]]) -> Facts | Outcome:
        sid = None
        if c.kind == "supplier_event":
            assert c.supplier_name
            res = resolve_supplier(c.supplier_name, c.supplier_country, self.md, self.g, self.flags["strict_resolution"])
            spans.append({"step": "resolve", "outcome": res.outcome, "reason": res.reason, "supplier_id": res.supplier_id})
            if res.outcome == "not_ours":
                self.journal.put(msg.msg_id, "done", True)
                return self._out(Outcome(msg.msg_id, "ignore", res.reason))
            if res.outcome == "ambiguous":
                return self._hold(msg, now_h, res.reason, spans)
            sid = res.supplier_id
        return Facts(c.kind, c.status, c.commodity, c.country, sid, c.magnitude, c.event, c.quotes)  # type: ignore[arg-type]

    def _watch_key(self, f: Facts) -> str:
        return f"tariff:{f.country}:{f.commodity}" if f.kind == "tariff" else f"supplier:{f.supplier_id}"

    def _decide(self, mid: str, f: Facts, now_h: float, crash: str | None, st: dict[str, Any], spans: list[dict[str, Any]]) -> Outcome:
        if f.status == "withdrawn":
            closed = self.watches.pop(self._watch_key(f), None)
            self.journal.put(mid, "done", True)
            return self._out(Outcome(mid, "withdrawn", f"withdrawn; closed watch from {closed}" if closed else "withdrawn"))
        if f.status == "unconfirmed" and self.flags["hold_rumours"]:
            self.watches[self._watch_key(f)] = mid
            spans.append({"step": "status", "status": "unconfirmed", "action": "watch"})
            self.journal.put(mid, "done", True)
            return self._out(Outcome(mid, "watch", "unconfirmed: watching for confirmation"))
        fk = f.fact_key(float(self.cfg["dedupe"]["magnitude_bucket_pct"]))
        prev = self.facts_seen.get(fk)
        if prev and prev[2] != mid and now_h - prev[0] <= float(self.cfg["dedupe"]["fact_window_h"]):
            linked = self._corroborate(prev[1], mid)
            self.msg_cards[mid.removesuffix("#desk")] = prev[1]
            spans.append({"step": "merge", "fact_key": fk, "cards_linked": linked})
            self.journal.put(mid, "done", True)
            return self._out(Outcome(mid, "corroborated", "same facts already carded", prev[1]))
        if "cards" in st:
            card_ids = list(st["cards"])
            spans.append({"step": "cards", "resumed": True, "cards": card_ids})
        else:
            card_ids = self._cards(mid, f, fk, now_h, spans)
            self.journal.put(mid, "cards", card_ids)
            if self.flags["journal"]:
                # published with the cards, so an article with the same facts that arrives while this workflow is
                # still in flight (crashed, waiting for redelivery) joins these cards instead of making new ones
                self.facts_seen[fk] = (now_h, card_ids, mid)
                self.msg_cards[mid.removesuffix("#desk")] = card_ids
        if crash == "after_card":
            spans.append({"step": "crash", "after": "cards"})
            raise Crash(mid)
        self.facts_seen.setdefault(fk, (now_h, card_ids, mid))
        if self.facts_seen[fk][2] != mid:
            self.facts_seen[fk] = (now_h, card_ids, mid)
        self.msg_cards[mid.removesuffix("#desk")] = card_ids
        if f.kind != "commodity_move":
            self.watches.pop(self._watch_key(f), None)
        self.journal.put(mid, "done", True)
        return self._out(Outcome(mid, "card" if card_ids else "no_card", f"{len(card_ids)} card(s)", card_ids))

    def _cards(self, mid: str, f: Facts, fk: str, now_h: float, spans: list[dict[str, Any]]) -> list[str]:
        exps = self.graph.exposures(f, now_h / 24)
        src = mid.removesuffix("#desk")
        floor = float(self.cfg["materiality_eur"])
        out: list[str] = []
        below = 0
        for e in exps:
            if abs(e.impact_eur) < floor and not (f.kind == "supplier_event" and f.event == "sanction"):
                below += 1
                continue
            driver = f.driver()
            if self.flags["memory"] and self.memory.suppress(e.cat_id, driver, e.impact_eur):
                self.suppressed.append((e.cat_id, driver, e.impact_eur, src))
                continue
            key = f"{mid}|{e.cat_id}"  # idempotency: one card per workflow and category
            if self.flags["journal"] and key in self.by_key:
                continue
            card = Card(
                card_id=f"C{len(self.cards) + 1:05d}",
                key=key,
                cat_id=e.cat_id,
                driver=driver,
                kind=f.kind,
                impact_eur=round(e.impact_eur, 2),
                lever=e.lever,
                path=e.path,
                evidence=tuple(dict.fromkeys((src, q) for _, q in f.quotes)),
                msg_ids=[src],
                created_h=now_h,
                manager=self.md.categories[e.cat_id].manager,
            )
            self.cards[card.card_id] = card
            self.by_key[key] = card.card_id
            out.append(card.card_id)
        spans.append({"step": "graph", "exposures": len(exps), "below_materiality": below, "cards": out})
        return out

    # ---------- people ----------

    def resolve_hold(self, msg: Message, facts: Facts | None, now_h: float) -> Outcome:
        """The market desk read a held message. `facts` is what the person found, or None if nothing for us."""
        spans = self.traces.setdefault(msg.msg_id, [])
        spans.append({"step": "desk", "resolved": facts is not None})
        if facts is None:
            return self._out(Outcome(msg.msg_id, "ignore", "desk: nothing for us"))
        return self._decide(msg.msg_id + "#desk", facts, now_h, None, {}, spans)

    def feedback(self, card_id: str, decision: str, reason: str | None) -> None:
        card = self.cards[card_id]
        card.status = "accepted" if decision == "accept" else "dismissed"
        if decision == "dismiss" and reason:
            self.memory.record(card.cat_id, card.driver, card.impact_eur, reason)

    # ---------- helpers ----------

    def _corroborate(self, card_ids: list[str], mid: str) -> int:
        n = 0
        for cid in card_ids:
            if cid in self.cards:
                self.cards[cid].corroborations += 1
                self.cards[cid].msg_ids.append(mid)
                n += 1
        return n

    def _hold(self, msg: Message, now_h: float, reason: str, spans: list[dict[str, Any]]) -> Outcome:
        self.holds.append(Hold(msg.msg_id, now_h, reason))
        spans.append({"step": "hold", "reason": reason})
        self.journal.put(msg.msg_id, "done", True)
        return self._out(Outcome(msg.msg_id, "hold", reason))

    def _out(self, o: Outcome) -> Outcome:
        self.log.append(o)
        return o
