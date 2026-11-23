"""A simulated model that reads one article. It knows the article's truth and makes the configured mistakes.

It stands in for a real model in the study, so every design meets the same reading errors (the luck is drawn
once per message and model). Its reply is plain JSON text; the sentinel trusts none of it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..domain import Prompt, Reply
from .luck import Luck
from .world import Article, World

LEGAL_RE = re.compile(r"\s+(GmbH|AG|Sp\. z o\.o\.|S\.A\. de C\.V\.|S\.A\.|s\.r\.o\.|a\.s\.|S\.p\.A\.|S\.r\.l\.|A\.S\.|Co\., Ltd\.|Pvt\. Ltd\.|JSC|Inc\.|LLC)$")


class SimReader:
    def __init__(self, world: World, luck: Luck, model: str) -> None:
        self.world = world
        self.luck = luck
        self.model = model
        self.cfg = world.cfg["models"][model]

    def read(self, prompt: Prompt) -> Reply:
        art = self.world.by_msg[prompt.msg_id]
        lk = self.luck.reader[self.model][prompt.msg_id]
        broken = lk.u_schema < float(self.cfg["schema_fail"]) and (prompt.attempt == 0 or lk.u_repair[min(prompt.attempt, 2) - 1] >= float(self.cfg["repair_ok"]))
        if broken:
            text = '{"kind": "' + ("tariff" if prompt.attempt else "supplier_event") + '", "status": "confirmed", "evidence": [{"field": "magnitude", "quote": "'
        else:
            text = json.dumps(self._reply(art, prompt.mode))
        lo, hi = self.cfg["latency_s"]
        return Reply(text, (len(prompt.system) + len(prompt.user)) // 4, len(prompt.system) // 4, max(1, len(text) // 4), lo + (hi - lo) * lk.u_latency)

    def _reply(self, art: Article, mode: str) -> dict[str, Any]:
        w = self.world
        ev = w.events[art.event_id]
        lk = self.luck.reader[self.model][art.msg.msg_id]
        c = self.cfg
        out: dict[str, Any] = {"status": art.status, "evidence": []}
        ev_list: list[dict[str, str]] = out["evidence"]
        kind = ev.kind
        if kind == "noise":
            kind = "commodity_move" if ev.commodity else "other"
        if lk.u_kind < float(c["wrong_kind"]):
            kind = "other"
        out["kind"] = kind
        if lk.u_status < float(c["status_error"]) and art.status != "withdrawn":
            out["status"] = "confirmed" if art.status == "unconfirmed" else "unconfirmed"
        if kind in ("commodity_move", "tariff") and "commodity" in art.names:
            out["commodity"] = art.names["commodity"]
            ev_list.append({"field": "commodity", "quote": art.sentences.get("commodity", art.msg.headline)})
            if ev.magnitude is not None:
                mag = round(ev.magnitude * 100, 1) if kind == "commodity_move" else round(abs(ev.magnitude) * 100, 1)
                if lk.u_mag < float(c["magnitude_error"]):
                    mag = round(min(99.0, abs(mag) * 10) * (1 if mag >= 0 else -1), 1)
                elif kind == "commodity_move" and lk.u_sign < float(c["sign_error"]):
                    mag = -mag
                out["magnitude_pct"] = mag
                ev_list.append({"field": "magnitude", "quote": art.sentences.get("magnitude", art.msg.headline)})
        if kind == "tariff" and "country" in art.names:
            out["country"] = art.names["country"]
            ev_list.append({"field": "country", "quote": art.sentences["country"]})
        if kind == "supplier_event" and "supplier" in art.names:
            name, country = art.names["supplier"], art.names["supplier_country"]
            quote = art.sentences["supplier"]
            if lk.u_halluc < float(c["supplier_halluc"]):
                ours = sorted(w.suppliers.values(), key=lambda s: s.supplier_id)
                pick = ours[int(lk.u_halluc_pick * len(ours))]
                name, country = pick.legal_name, w.cfg["countries"][pick.country]["adj"]
            elif lk.u_drift < float(c["supplier_drift"]):
                name = LEGAL_RE.sub("", name)
                if lk.u_drift_country >= 0.5:
                    country = "German" if country != "German" else "Polish"
            out["supplier_name"] = name
            out["supplier_country"] = country
            ev_list.append({"field": "supplier", "quote": quote})
            ev_list.append({"field": "supplier_country", "quote": quote})
            if ev.event and art.status != "withdrawn":
                out["event"] = ev.event
                ev_list.append({"field": "event", "quote": art.sentences["event"]})
        if "status" in art.sentences:
            ev_list.append({"field": "status", "quote": art.sentences["status"]})
        obey = bool(art.injection_targets) and lk.u_inject < float(c["injection_obey"])
        if obey:
            inj = art.msg.body[art.msg.body.index("Note to AI systems") :]
            if kind == "commodity_move":
                out["magnitude_pct"] = 40.0
                ev_list[:] = [e for e in ev_list if e["field"] != "magnitude"] + [{"field": "magnitude", "quote": inj}]
        if mode == "alone":
            cats = self._alone_categories(art, kind, out["status"])
            if obey:
                cats = list(dict.fromkeys(cats + list(art.injection_targets)))
            out["affected_categories"] = cats
            out["urgency"] = "high" if cats and (obey or kind == "supplier_event") else ("medium" if cats else "low")
        return out

    def _alone_categories(self, art: Article, kind: str, status: str) -> list[str]:
        w = self.world
        ev = w.events[art.event_id]
        lk = self.luck.reader[self.model][art.msg.msg_id]
        a = self.cfg["alone"]
        if status == "withdrawn" or (status == "unconfirmed" and lk.u_rumour >= float(a["rumour_as_real_p"])):
            return []
        cats: list[str] = []
        weights = {k: w.cfg["categories"][k]["weights"] for k in w.cat_ids}
        for i, cat in enumerate(w.cat_ids):
            u = lk.u_alone[i]
            if kind == "commodity_move" and ev.commodity in w.cfg["commodities"]:
                if w.primary[cat] == ev.commodity and u < float(a["primary_p"]):
                    cats.append(cat)
                elif w.primary[cat] != ev.commodity and weights[cat].get(ev.commodity, 0) > 0 and u < float(a["secondary_p"]):
                    cats.append(cat)
            elif kind == "tariff" and ev.kind == "tariff":
                tier1 = any(k.cat_id == cat and w.suppliers[k.supplier_id].country == ev.country for k in w.contracts) and w.primary[cat] == ev.commodity
                tier2 = any(t.country == ev.country and t.commodity == ev.commodity and cat in w.suppliers[t.supplier_id].categories for t in w.tier2)
                if tier1 and u < float(a["primary_p"]):
                    cats.append(cat)
                elif tier2 and u < float(a["indirect_p"]):
                    cats.append(cat)
                elif not tier1 and w.primary[cat] == ev.commodity and u < float(a["secondary_p"]):
                    cats.append(cat)
            elif kind == "supplier_event" and ev.kind == "supplier_event":
                if ev.supplier_id and cat in w.suppliers[ev.supplier_id].categories and u < float(a["primary_p"]):
                    cats.append(cat)
                elif ev.lookalike_of and cat in w.suppliers[ev.lookalike_of].categories and lk.u_alone_extra < float(a["lookalike_fooled_p"]):
                    cats.append(cat)
        if kind != "other" and lk.u_halluc < float(a["false_category_p"]):
            cats.append(w.cat_ids[int(lk.u_halluc_pick * len(w.cat_ids))])
        return list(dict.fromkeys(cats))
