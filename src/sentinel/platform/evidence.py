"""Code checks every claim against the article. A field counts only if a quote copied from the article backs it.

The status (confirmed, unconfirmed, withdrawn) is decided here from the words in the checked quotes, not from the
model's label. A quote that reads like an instruction to a machine is never evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ..domain import SignalRead

EVENT_WORDS = {
    "insolvency": ["insolvency", "bankruptcy"],
    "outage": ["fire", "halted", "halt production", "outage", "shut"],
    "sanction": ["sanctions"],
    "esg": ["audit", "forced", "violation", "pollution"],
}
REQUIRED = {
    "commodity_move": ("commodity", "magnitude"),
    "tariff": ("country", "commodity", "magnitude"),
    "supplier_event": ("supplier", "supplier_country", "event"),
}
REQUIRED_WITHDRAWN = {"tariff": ("country", "commodity"), "supplier_event": ("supplier", "supplier_country")}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _has(text: str, phrase: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(phrase.lower()) + r"(?![\w-])", text.lower()) is not None


class Glossary:
    def __init__(self, cfg: dict[str, Any]) -> None:
        g = cfg["glossary"]
        self.commodities: dict[str, list[str]] = g["commodities"]
        self.countries: dict[str, list[str]] = g["countries"]
        self.legal_forms: list[str] = sorted(g["legal_forms"], key=len, reverse=True)
        self.up: list[str] = g["up_words"]
        self.down: list[str] = g["down_words"]
        self.hedge: list[str] = g["hedge_words"]
        self.withdrawn: list[str] = g["withdrawn_words"]
        self.instruction = [re.compile(p, re.I) for p in g["instruction_patterns"]]

    def commodity_id(self, name: str | None) -> str | None:
        if not name:
            return None
        n = name.strip().lower()
        for cid, syns in self.commodities.items():
            if n in (s.lower() for s in syns) or n == cid:
                return cid
        return None

    def country_id(self, name: str | None) -> str | None:
        if not name:
            return None
        n = name.strip().lower().removeprefix("the ")
        for iso, names in self.countries.items():
            if n == iso.lower() or n in (x.lower() for x in names):
                return iso
        return None

    def instruction_like(self, text: str) -> bool:
        return any(p.search(text) for p in self.instruction)

    def split_legal(self, name: str) -> tuple[str, str | None]:
        n = norm(name)
        for form in self.legal_forms:
            if n.endswith(" " + form):
                return n[: -len(form) - 1].strip(), form
        return n, None


@dataclass(frozen=True)
class Checked:
    outcome: Literal["facts", "hold", "ignore"]
    reason: str
    kind: str = "other"
    status: str = "confirmed"
    commodity: str | None = None
    country: str | None = None
    magnitude: float | None = None
    supplier_name: str | None = None
    supplier_country: str | None = None
    event: str | None = None
    quotes: tuple[tuple[str, str], ...] = ()
    dropped: tuple[str, ...] = ()
    instruction_like: bool = False
    verified: dict[str, bool] = field(default_factory=dict)


def _pct_in(quote: str, value: float) -> bool:
    target = abs(value)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s?%", quote):
        if abs(float(m.group(1)) - target) < 0.051:
            return True
    return False


def _move_in(quote: str, value: float, verbs: list[str]) -> bool:
    """The verb right before the number must point the same way as the sign: 'rose 4.2%' backs +4.2, not -4.2."""
    for m in re.finditer(r"([A-Za-z]+)\s+(?:by\s+)?(\d+(?:\.\d+)?)\s?%", quote):
        if abs(float(m.group(2)) - abs(value)) < 0.051 and m.group(1).lower() in (v.lower() for v in verbs):
            return True
    return False


def code_status(g: Glossary, quotes: list[str], headline: str) -> str:
    texts = quotes + [headline]
    if any(_has(t, w) for t in texts for w in g.withdrawn):
        return "withdrawn"
    if any(_has(t, w) for t in texts for w in g.hedge):
        return "unconfirmed"
    return "confirmed"


def check_read(read: SignalRead, text: str, headline: str, g: Glossary, quote_check: bool = True) -> Checked:
    instr = g.instruction_like(text)
    if read.kind == "other":
        return Checked("ignore", "the model read no procurement signal", instruction_like=instr)
    if not quote_check:
        return _unchecked(read, g, instr)
    body = norm(text)
    by_field: dict[str, list[str]] = {}
    for e in read.evidence:
        q = norm(e.quote)
        if q and q in body and not g.instruction_like(q):
            by_field.setdefault(e.field, []).append(q)
    ok: dict[str, bool] = {}
    cid = g.commodity_id(read.commodity)
    if read.commodity:
        quotes = by_field.get("commodity", [])
        if cid is None:
            if any(_has(q, read.commodity) for q in quotes):
                return Checked("ignore", f"'{read.commodity}' is not a commodity we buy", read.kind, instruction_like=instr)
            ok["commodity"] = False
        else:
            ok["commodity"] = any(_has(q, s) for q in quotes for s in g.commodities[cid])
    mag: float | None = None
    if read.magnitude_pct is not None:
        quotes = by_field.get("magnitude", [])
        if read.kind == "commodity_move":
            want = g.up if read.magnitude_pct > 0 else g.down
            good = [q for q in quotes if _move_in(q, read.magnitude_pct, want)]
        else:
            good = [q for q in quotes if _pct_in(q, read.magnitude_pct)]
        ok["magnitude"] = bool(good)
        mag = read.magnitude_pct / 100 if good else None
    iso = g.country_id(read.country)
    if read.country:
        ok["country"] = iso is not None and any(_has(q, n) for q in by_field.get("country", []) for n in g.countries[iso])
    if read.supplier_name:
        ok["supplier"] = any(norm(read.supplier_name) in q for q in by_field.get("supplier", []))
    sup_iso = g.country_id(read.supplier_country)
    if read.supplier_country:
        ok["supplier_country"] = sup_iso is not None and any(_has(q, n) for q in by_field.get("supplier_country", []) for n in g.countries[sup_iso])
    if read.event:
        ok["event"] = any(_has(q, w) for q in by_field.get("event", []) for w in EVENT_WORDS[read.event])
    used = [q for f, qs in by_field.items() if ok.get(f) for q in qs]
    status = code_status(g, used + by_field.get("status", []), headline)
    need = (REQUIRED_WITHDRAWN if status == "withdrawn" else REQUIRED).get(read.kind, ())
    dropped = tuple(f for f, v in ok.items() if not v)
    missing = [f for f in need if not ok.get(f)]
    quotes_kept = tuple((f, q) for f, qs in by_field.items() if ok.get(f) for q in qs)
    common = dict(
        kind=read.kind,
        status=status,
        commodity=cid if ok.get("commodity") else None,
        country=iso if ok.get("country") else None,
        magnitude=mag,
        supplier_name=norm(read.supplier_name) if ok.get("supplier") and read.supplier_name else None,
        supplier_country=sup_iso if ok.get("supplier_country") else None,
        event=read.event if ok.get("event") else None,
        quotes=quotes_kept,
        dropped=dropped,
        instruction_like=instr,
        verified=ok,
    )
    if missing:
        return Checked("hold", "not backed by a quote: " + ", ".join(missing), **common)  # type: ignore[arg-type]
    return Checked("facts", "checked", **common)  # type: ignore[arg-type]


def _unchecked(read: SignalRead, g: Glossary, instr: bool) -> Checked:
    """The no-quote-check ablation: take the model's fields and its status as given."""
    cid = g.commodity_id(read.commodity)
    if read.kind in ("commodity_move", "tariff") and read.commodity and cid is None:
        return Checked("ignore", f"'{read.commodity}' is not a commodity we buy", read.kind, instruction_like=instr)
    need = (REQUIRED_WITHDRAWN if read.status == "withdrawn" else REQUIRED).get(read.kind, ())
    mag = None if read.magnitude_pct is None else read.magnitude_pct / 100
    country, sup_country = g.country_id(read.country), g.country_id(read.supplier_country)
    present = {"commodity": cid, "magnitude": mag, "country": country, "supplier": read.supplier_name, "supplier_country": sup_country, "event": read.event}
    missing = [f for f in need if present.get(f) is None]
    return Checked(
        outcome="hold" if missing else "facts",
        reason="missing: " + ", ".join(missing) if missing else "unchecked",
        kind=read.kind,
        status=read.status,
        commodity=cid,
        country=country,
        magnitude=mag,
        supplier_name=norm(read.supplier_name) if read.supplier_name else None,
        supplier_country=sup_country,
        event=read.event,
        quotes=tuple((e.field, norm(e.quote)) for e in read.evidence),
        instruction_like=instr,
    )
