"""The API: a message is accepted once, a decision is kept once, a what-if makes no card."""

from __future__ import annotations

from fastapi.testclient import TestClient
from helpers import COPPER_BODY, COPPER_READ, ScriptedReader, cfg, md

from sentinel.service.api import create_app
from sentinel.service.store import Store

SIG = {"msg_id": "M1", "source": "Test Wire", "published_h": 10, "headline": "LME copper rose 8.0%", "body": COPPER_BODY}


def _client(store: Store | None = None) -> tuple[TestClient, ScriptedReader, Store]:
    store = store or Store()
    r = ScriptedReader({"M1": COPPER_READ})
    return TestClient(create_app(md(), cfg(), r, "model_a", store)), r, store


def test_a_message_sent_twice_is_handled_once() -> None:
    c, r, _ = _client()
    a = c.post("/v1/signals", json=SIG)
    b = c.post("/v1/signals", json=SIG)
    assert a.status_code == 201 and b.status_code == 200 and b.json()["result"] == "redelivered"
    assert len(c.get("/v1/cards").json()) == 2 and r.calls == ["M1"]


def test_cards_come_largest_money_first_with_their_path() -> None:
    c, _, _ = _client()
    c.post("/v1/signals", json=SIG)
    cards = c.get("/v1/cards?status=open").json()
    assert abs(cards[0]["impact_eur"]) >= abs(cards[1]["impact_eur"])
    one = c.get(f"/v1/cards/{cards[0]['card_id']}").json()
    assert one["path"] and one["evidence"] and one["trace"]


def test_a_decision_is_kept_once() -> None:
    c, _, _ = _client()
    c.post("/v1/signals", json=SIG)
    cid = c.get("/v1/cards").json()[0]["card_id"]
    body = {"decision": "accept", "manager_id": "m1", "idempotency_key": "key-00001"}
    assert c.post(f"/v1/cards/{cid}/decision", json=body).status_code == 201
    assert c.post(f"/v1/cards/{cid}/decision", json=body).json()["outcome"] == "replayed"
    assert c.post(f"/v1/cards/{cid}/decision", json={**body, "decision": "dismiss", "reason": "not_relevant", "idempotency_key": "key-00002"}).status_code == 409
    assert c.get("/v1/cards?status=open").json() and all(x["card_id"] != cid for x in c.get("/v1/cards?status=open").json())


def test_a_dismissal_needs_a_reason() -> None:
    c, _, _ = _client()
    c.post("/v1/signals", json=SIG)
    cid = c.get("/v1/cards").json()[0]["card_id"]
    assert c.post(f"/v1/cards/{cid}/decision", json={"decision": "dismiss", "manager_id": "m1", "idempotency_key": "key-00003"}).status_code == 422


def test_a_restart_resumes_from_the_store() -> None:
    store = Store()
    c, _, _ = _client(store)
    c.post("/v1/signals", json=SIG)
    c2, r2, _ = _client(store)
    assert c2.post("/v1/signals", json=SIG).json()["result"] == "redelivered" and r2.calls == []
    assert len(c2.get("/v1/cards").json()) == 2


def test_what_if_walks_the_graph_without_making_a_card() -> None:
    c, _, _ = _client()
    out = c.post("/v1/what-if", json={"kind": "tariff", "commodity": "aluminium", "country": "CN", "magnitude_pct": 20}).json()
    assert {x["cat_id"] for x in out} == {"extr", "motors"}
    assert c.get("/v1/cards").json() == []
    assert c.post("/v1/what-if", json={"kind": "tariff"}).status_code == 422
