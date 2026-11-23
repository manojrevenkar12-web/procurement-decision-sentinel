"""SQLite store: messages, the workflow journal, cards and decisions.

A message is accepted once by id. The journal keeps each workflow step, so a restarted worker resumes and a
redelivered message does nothing. A card is unique per idempotency key; a manager's decision is kept once per card
and per idempotency key.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from typing import Any

from ..domain import Card, SignalRead
from ..platform.validate import ReadResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (msg_id TEXT PRIMARY KEY, body TEXT NOT NULL, received_h REAL NOT NULL);
CREATE TABLE IF NOT EXISTS journal (msg_id TEXT NOT NULL, step TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (msg_id, step));
CREATE TABLE IF NOT EXISTS cards (card_id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, cat_id TEXT NOT NULL, manager INTEGER NOT NULL, impact_eur REAL NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
  card_id TEXT PRIMARY KEY REFERENCES cards(card_id),
  decision TEXT NOT NULL CHECK (decision IN ('accept', 'dismiss')),
  reason TEXT,
  manager_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE
);
"""


def _encode(value: Any) -> str:
    if isinstance(value, ReadResult):
        d = asdict(value)
        d["read"] = value.read.model_dump() if value.read else None
        return json.dumps({"type": "read", "value": d})
    return json.dumps({"type": "json", "value": value})


def _decode(text: str) -> Any:
    obj = json.loads(text)
    if obj["type"] == "read":
        d = obj["value"]
        d["read"] = SignalRead.model_validate(d["read"]) if d["read"] else None
        return ReadResult(**d)
    return obj["value"]


def card_to_dict(c: Card) -> dict[str, Any]:
    d = asdict(c)
    d["path"] = list(c.path)
    d["evidence"] = [{"msg_id": m, "quote": q} for m, q in c.evidence]
    return d


def card_from_dict(d: dict[str, Any]) -> Card:
    d = dict(d)
    d["path"] = tuple(d["path"])
    d["evidence"] = tuple((e["msg_id"], e["quote"]) for e in d["evidence"])
    return Card(**d)


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._lock = threading.RLock()

    # --- messages ---
    def put_message(self, msg_id: str, body: dict[str, Any], received_h: float) -> bool:
        with self._lock:
            cur = self._conn.execute("INSERT OR IGNORE INTO messages VALUES (?, ?, ?)", (msg_id, json.dumps(body), received_h))
            self._conn.commit()
            return cur.rowcount == 1

    # --- journal (the platform's Journal protocol) ---
    def get(self, msg_id: str) -> dict[str, Any]:
        rows = self._conn.execute("SELECT step, value FROM journal WHERE msg_id = ?", (msg_id,)).fetchall()
        return {step: _decode(v) for step, v in rows}

    def put(self, msg_id: str, step: str, value: Any) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO journal VALUES (?, ?, ?)", (msg_id, step, _encode(value)))
            self._conn.commit()

    # --- cards ---
    def put_card(self, c: Card) -> bool:
        with self._lock:
            cur = self._conn.execute("INSERT OR IGNORE INTO cards VALUES (?, ?, ?, ?, ?, ?)", (c.card_id, c.key, c.cat_id, c.manager, abs(c.impact_eur), json.dumps(card_to_dict(c))))
            if cur.rowcount == 0:
                self._conn.execute("UPDATE cards SET body = ? WHERE card_id = ?", (json.dumps(card_to_dict(c)), c.card_id))
            self._conn.commit()
            return cur.rowcount == 1

    def cards(self, status: str | None = None, manager: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT c.body, d.decision FROM cards c LEFT JOIN decisions d ON d.card_id = c.card_id"
        conds: list[str] = []
        args: list[Any] = []
        if manager is not None:
            conds.append("c.manager = ?")
            args.append(manager)
        if status == "open":
            conds.append("d.card_id IS NULL")
        elif status in ("accept", "dismiss"):
            conds.append("d.decision = ?")
            args.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY c.impact_eur DESC, c.card_id"
        return [json.loads(b) | {"decision": d} for b, d in self._conn.execute(sql, args).fetchall()]

    def card(self, card_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT body FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # --- decisions ---
    def put_decision(self, card_id: str, decision: str, reason: str | None, manager_id: str, key: str) -> tuple[dict[str, Any], str]:
        """Returns (stored decision, outcome) where outcome is created, replayed or conflict."""
        cols = ("card_id", "decision", "reason", "manager_id", "idempotency_key")
        with self._lock:
            by_key = self._conn.execute("SELECT * FROM decisions WHERE idempotency_key = ?", (key,)).fetchone()
            if by_key:
                rec = dict(zip(cols, by_key, strict=True))
                return rec, "replayed" if by_key[0] == card_id and by_key[1] == decision else "conflict"
            existing = self._conn.execute("SELECT * FROM decisions WHERE card_id = ?", (card_id,)).fetchone()
            if existing:
                return dict(zip(cols, existing, strict=True)), "conflict"
            self._conn.execute("INSERT INTO decisions VALUES (?, ?, ?, ?, ?)", (card_id, decision, reason, manager_id, key))
            self._conn.commit()
        return dict(zip(cols, (card_id, decision, reason, manager_id, key), strict=True)), "created"

    def decisions(self) -> list[dict[str, Any]]:
        cols = ("card_id", "decision", "reason", "manager_id", "idempotency_key")
        return [dict(zip(cols, r, strict=True)) for r in self._conn.execute("SELECT * FROM decisions ORDER BY rowid").fetchall()]
