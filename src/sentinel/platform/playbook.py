"""The codified sourcing playbook: which lever a card proposes. Rules live in config/platform.yml."""

from __future__ import annotations

from typing import Any


def choose_lever(rules: list[dict[str, Any]], ctx: dict[str, Any]) -> str:
    for rule in rules:
        ok = True
        for key, want in rule["when"].items():
            if key == "share_at_least":
                ok = "share" in ctx and float(ctx["share"]) >= float(want)
                if not ok:
                    break
                continue
            have = ctx.get(key)
            if isinstance(want, list):
                ok = have in want
            else:
                ok = have == want
            if not ok:
                break
        if ok:
            return str(rule["lever"])
    return "review"
