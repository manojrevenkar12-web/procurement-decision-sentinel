"""The sentinel API. It knows master data, a reader and a store; it never knows where they come from.

POST /v1/signals                 one article in; accepted once by id; returns the outcome and any cards
GET  /v1/cards?status=open       cards, largest money first
GET  /v1/cards/{id}              one card with its path, evidence and trace
POST /v1/cards/{id}/decision     a manager's decision, kept once per card and per idempotency key
GET  /v1/holds                   messages a person must read
POST /v1/what-if                 walk the graph for a hypothetical signal; no card is made
GET  /v1/graph                   the knowledge graph's edges
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from ..domain import Facts, MasterData, Message
from ..platform.pipeline import Sentinel
from ..platform.readers import Reader
from .store import Store, card_from_dict


class SignalIn(BaseModel):
    msg_id: str = Field(min_length=1, max_length=64)
    source: str = Field(max_length=120)
    published_h: float = Field(ge=0)
    headline: str = Field(max_length=400)
    body: str = Field(max_length=20000)


class DecisionIn(BaseModel):
    decision: Literal["accept", "dismiss"]
    reason: Literal["within_tolerance", "not_relevant"] | None = None
    manager_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)


class WhatIfIn(BaseModel):
    kind: Literal["commodity_move", "tariff", "supplier_event"]
    commodity: str | None = None
    country: str | None = None
    supplier_id: str | None = None
    magnitude_pct: float | None = Field(default=None, ge=-100, le=100)
    event: Literal["insolvency", "outage", "sanction", "esg"] | None = None
    day: float = 0.0


def create_app(md: MasterData, cfg: dict[str, Any], reader: Reader, model: str, store: Store) -> FastAPI:
    sentinel = Sentinel(md, cfg, reader, model, journal=store)
    for d in store.cards():
        c = card_from_dict({k: v for k, v in d.items() if k != "decision"})
        sentinel.cards[c.card_id] = c
        sentinel.by_key[c.key] = c.card_id
    for dec in store.decisions():
        if dec["card_id"] in sentinel.cards:
            sentinel.feedback(dec["card_id"], dec["decision"], dec["reason"])
    app = FastAPI(title="procurement-decision-sentinel", version="1.0.0")
    app.state.sentinel = sentinel

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/signals")
    def ingest(s: SignalIn, response: Response) -> dict[str, Any]:
        created = store.put_message(s.msg_id, s.model_dump(), s.published_h)
        msg = Message(s.msg_id, s.source, s.published_h, s.headline, s.body)
        out = sentinel.handle(msg, s.published_h)
        for cid in sentinel.msg_cards.get(s.msg_id, []):
            store.put_card(sentinel.cards[cid])
        response.status_code = 201 if created else 200
        return {"msg_id": s.msg_id, "result": out.result, "reason": out.reason, "cards": out.cards, "trace": sentinel.traces.get(s.msg_id, [])}

    @app.get("/v1/cards")
    def cards(status: Literal["open", "accept", "dismiss"] | None = None, manager: int | None = None) -> list[dict[str, Any]]:
        return store.cards(status, manager)

    @app.get("/v1/cards/{card_id}")
    def card(card_id: str) -> dict[str, Any]:
        c = store.card(card_id)
        if c is None:
            raise HTTPException(404, "no such card")
        return c | {"trace": sentinel.traces.get(c["msg_ids"][0], [])}

    @app.post("/v1/cards/{card_id}/decision")
    def decide(card_id: str, d: DecisionIn, response: Response) -> dict[str, Any]:
        if store.card(card_id) is None:
            raise HTTPException(404, "no such card")
        if d.decision == "dismiss" and d.reason is None:
            raise HTTPException(422, "a dismissal needs a reason")
        rec, outcome = store.put_decision(card_id, d.decision, d.reason, d.manager_id, d.idempotency_key)
        if outcome == "conflict":
            raise HTTPException(409, {"message": "this card or key already has another decision", "stored": rec})
        if outcome == "created":
            sentinel.feedback(card_id, d.decision, d.reason)
            store.put_card(sentinel.cards[card_id])
            response.status_code = 201
        return rec | {"outcome": outcome}

    @app.get("/v1/holds")
    def holds() -> list[dict[str, Any]]:
        return [asdict(h) for h in sentinel.holds]

    @app.post("/v1/what-if")
    def what_if(w: WhatIfIn) -> list[dict[str, Any]]:
        f = Facts(w.kind, "confirmed", w.commodity, w.country, w.supplier_id, None if w.magnitude_pct is None else w.magnitude_pct / 100, w.event)
        try:
            exps = sentinel.graph.exposures(f, w.day)
        except (AssertionError, KeyError) as e:
            raise HTTPException(422, f"not enough facts for a {w.kind}: {e}") from e
        return [{"cat_id": e.cat_id, "impact_eur": round(e.impact_eur, 2), "lever": e.lever, "path": list(e.path), "material": abs(e.impact_eur) >= float(cfg["materiality_eur"])} for e in exps]

    @app.get("/v1/graph")
    def graph() -> list[dict[str, Any]]:
        return [asdict(e) for e in sentinel.graph.edges()]

    return app
