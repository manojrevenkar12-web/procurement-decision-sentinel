"""Writes REPORT.md, the README results block and web/public/data/report.json from reports/*.json. Never edit those by hand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config

ROOT = config.ROOT
START, END = "<!-- results:start -->", "<!-- results:end -->"
LEVERS = {
    "index_pass_through_check": "check index pass-through",
    "renewal_should_cost": "prepare renewal with should-cost",
    "shift_volume": "shift volume to an alternate",
    "landed_cost_requote": "re-quote landed cost",
    "stop_new_pos": "stop new POs, legal review",
    "corrective_action_plan": "ask for a corrective action plan",
    "dual_source_buffer": "secure buffer stock, dual-source",
    "qualify_alternate": "qualify an alternate",
    "review": "manager decides",
}


def pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def pts(x: float) -> str:
    return f"{x * 100:+.1f}"


def ci(c: dict[str, float]) -> str:
    return f"{pts(c['diff'])} [{pts(c['lo'])}, {pts(c['hi'])}]"


def eur(x: float | None) -> str:
    if x is None:
        return "n/a"
    if abs(x) >= 1e6:
        return f"EUR {x / 1e6:.2f}M"
    if abs(x) >= 1e3:
        return f"EUR {x / 1e3:.0f}k"
    return f"EUR {x:.3f}"


def hours(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f} h"


def _main_table(res: dict[str, Any], names: list[str]) -> list[str]:
    d = res["designs"]
    comp = res["comparisons"]
    rows = [
        "| Design | Value captured | vs status quo, pts [95% CI] | Cards / week | Cards that mattered | People, min / week | Signal to decision (median) | Duplicate cards | Model cost / week |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for n in names:
        m = d[n]["metrics"]
        vs = "baseline" if n == "status_quo" else ci(comp[f"{n}_vs_status_quo"]) if f"{n}_vs_status_quo" in comp else "-"
        rows.append(f"| {d[n]['label']} | {pct(m['value_share'])} | {vs} | {m['cards_per_week']:.1f} | {pct(m['precision'])} | {m['minutes_per_week']:.0f} | {hours(m['decision_median_h'])} | {m['duplicate_cards']} | {eur(m['cost_eur_per_week'])} |")
    return rows


def _gates(res: dict[str, Any]) -> list[str]:
    rows = ["| Gate | Value | Limit | Result |", "|---|---:|---:|---|"]
    for g in res["gates"]["platform"]:
        v = g["value"]
        vs = "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
        op = ">=" if g["kind"] == "min" else "<="
        rows.append(f"| {g['gate']} | {vs} | {op} {g['limit']} | {'pass' if g['pass'] else '**FAIL**'} |")
    for name, s in res["gates"]["model_swap"].items():
        rows.append(f"| Model swap: {res['designs'][name]['label']} | {s['value_share_below_platform_pts']:.2f} pts below, {pct(s['precision'])} material, {s['minutes_ratio_to_platform']:.2f}x minutes | see gates.yml | {s['verdict']} |")
    return rows


def _false_table(res: dict[str, Any]) -> list[str]:
    d = res["designs"]
    names = ["status_quo", "model_alone", "platform"]
    causes = list(d["platform"]["metrics"]["false_causes"])
    rows = ["| Why a card did not matter | " + " | ".join(d[n]["label"] for n in names) + " |", "|---|" + "---:|" * len(names)]
    label = {
        "injection": "injected instruction in the article",
        "namesake": "a namesake, not our supplier",
        "rumour": "a rumour that died",
        "below_tolerance": "real but within the category's tolerance",
        "wrong_entity": "the wrong supplier",
        "noise": "not about anything we buy",
        "estimate_or_read": "misread amount or estimate",
    }
    for c in causes:
        rows.append(f"| {label[c]} | " + " | ".join(str(d[n]["metrics"]["false_causes"][c]) for n in names) + " |")
    rows.append("| duplicate of an earlier card | " + " | ".join(str(d[n]["metrics"]["duplicate_cards"]) for n in names) + " |")
    rows.append("| left unreviewed at the end | " + " | ".join(str(d[n]["metrics"]["unreviewed_cards"]) for n in names) + " |")
    return rows


def _ablations(res: dict[str, Any]) -> list[str]:
    d = res["designs"]
    pm = d["platform"]["metrics"]
    rows = ["| Switched off | Value vs sentinel, pts [95% CI] | Cards that mattered | People, min / week | What moved |", "|---|---:|---:|---:|---|"]
    for a in res["ablations"] + res["model_swap"]:
        m = d[a]["metrics"]
        moved = []
        for key, lab in (("injection_cards", "injection cards"), ("namesake_cards", "namesake cards"), ("rumour_cards", "rumour cards"), ("duplicate_cards", "duplicates")):
            if m[key] != pm[key]:
                moved.append(f"{lab} {pm[key]} -> {m[key]}")
        if abs(m["holds_per_week"] - pm["holds_per_week"]) > 0.5:
            moved.append(f"held for the desk {pm['holds_per_week']:.1f} -> {m['holds_per_week']:.1f}/wk")
        if abs(m["cost_eur_per_week"] - pm["cost_eur_per_week"]) > 0.01:
            moved.append(f"model cost {eur(pm['cost_eur_per_week'])} -> {eur(m['cost_eur_per_week'])}/wk")
        if m["suppressed_material"] != pm["suppressed_material"]:
            moved.append(f"material cards suppressed {pm['suppressed_material']} -> {m['suppressed_material']}")
        if abs(m["false_causes"]["below_tolerance"] - pm["false_causes"]["below_tolerance"]) > 2:
            moved.append(f"within-tolerance cards {pm['false_causes']['below_tolerance']} -> {m['false_causes']['below_tolerance']}")
        rows.append(f"| {d[a]['label']} | {ci(res['comparisons'][f'{a}_vs_platform'])} | {pct(m['precision'])} | {m['minutes_per_week']:.0f} | {'; '.join(moved) or 'nothing beyond noise'} |")
    return rows


def _by_kind(res: dict[str, Any]) -> list[str]:
    names = ["status_quo", "model_alone", "platform", "tier1_only"]
    kinds = list(res["by_kind"]["platform"])
    rows = ["| Signal | Material pairs | " + " | ".join(res["designs"][n]["label"] for n in names) + " |", "|---|---:|" + "---:|" * len(names)]
    for k in kinds:
        rows.append(f"| {k} | {res['by_kind']['platform'][k]['pairs']:.0f} | " + " | ".join(pct(res["by_kind"][n].get(k, {}).get("value_share")) for n in names) + " |")
    return rows


def _card_md(c: dict[str, Any]) -> list[str]:
    out = [f"**{c['category']}**: {eur(c['impact_eur'])} a year, lever: {LEVERS.get(c['lever'], c['lever'])}", "", "Why this card exists:", ""]
    out += [f"{i + 1}. {p}" for i, p in enumerate(c["path"])]
    out += ["", "Evidence, copied from the article:", ""]
    out += [f"> {e['quote']} ({e['msg_id']})" for e in c["evidence"][:3]]
    dec = c["decision"]
    out += [
        "",
        f"Manager: {dec['decision'] if dec else 'not reviewed'}{', ' + dec['reason'] if dec and dec['reason'] else ''}. Truth: {'material' if c['truth']['material'] else 'not material'}, true impact {eur(c['truth']['true_impact_eur'])}.",
    ]
    return out


def section(res: dict[str, Any], title: str) -> list[str]:
    names = ["status_quo", "model_alone", "platform"]
    pm = res["designs"]["platform"]["metrics"]
    out = [
        f"## {title}",
        "",
        f"Seeds {res['seeds']} ({res['variant']} world), 8 weeks each. {pm['messages_per_week']:.0f} articles a week reach every design; {pm['material_pairs']} (event, category) pairs truly mattered.",
        "",
    ]
    out += _main_table(res, names)
    out += [
        "",
        "Value captured is the share of mitigable money that people acted on in time, with the right lever (a wrong lever captures half; value decays to zero over each signal's horizon). The monthly category review runs in every design.",
        "",
    ]
    out += ["### Gates", ""] + _gates(res)
    out += ["", "### Why cards did not matter", ""] + _false_table(res)
    out += ["", "### One switch at a time", ""] + _ablations(res)
    out += ["", "### Value captured by signal", ""] + _by_kind(res)
    return out


def report_md() -> str:
    dev = json.loads((config.REPORTS / "dev.json").read_text(encoding="utf-8"))
    held_path = config.REPORTS / "heldout.json"
    lines = ["# Results", "", "Generated by `python -m sentinel.cli report` from `reports/*.json`. Do not edit.", ""]
    lines += section(dev, "Development seeds")
    if held_path.exists():
        lines += [""] + section(json.loads(held_path.read_text(encoding="utf-8")), "Held-out seeds (run once)")
    s = dev["samples"]
    if s.get("cards"):
        lines += ["", "## Sample cards (development seed 11)", ""]
        for name, c in s["cards"].items():
            lines += [f"### {name.replace('_', ' ')}", ""] + _card_md(c) + [""]
    if s.get("messages"):
        lines += ["## Messages that did not become cards", ""]
        for name, m in s["messages"].items():
            lines += [f"### {name}", "", f"*{m['headline']}* ({m['source']})", "", f"> {m['body']}", "", f"Outcome: {m['outcome']}: {m['reason']}. {m['note']}", ""]
            lines += ["```json", json.dumps(m["trace"], indent=1), "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def readme_block() -> str:
    dev = json.loads((config.REPORTS / "dev.json").read_text(encoding="utf-8"))
    held_path = config.REPORTS / "heldout.json"
    out = [START, "", "_Generated from `reports/*.json` by `python -m sentinel.cli report`._", ""]
    for res, title in [(dev, "Development seeds")] + ([(json.loads(held_path.read_text(encoding="utf-8")), "Held-out seeds, run once")] if held_path.exists() else []):
        out += [f"**{title}** ({res['variant']} world, seeds {res['seeds']})", ""]
        out += _main_table(res, ["status_quo", "model_alone", "platform"])
        failed = [g["gate"] for g in res["gates"]["platform"] if not g["pass"]]
        swap = "; ".join(f"{res['designs'][k]['label']}: {v['verdict']}" for k, v in res["gates"]["model_swap"].items())
        out += ["", f"Gates: {'all ' + str(len(res['gates']['platform'])) + ' pass' if not failed else 'FAILED: ' + '; '.join(failed)}. Model swap: {swap}.", ""]
    out.append(END)
    return "\n".join(out)


def write_all() -> list[Path]:
    paths = []
    rp = ROOT / "REPORT.md"
    rp.write_text(report_md(), encoding="utf-8")
    paths.append(rp)
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        if START in text and END in text:
            head, rest = text.split(START, 1)
            _, tail = rest.split(END, 1)
            readme.write_text(head + readme_block() + tail, encoding="utf-8")
            paths.append(readme)
    data = {"dev": json.loads((config.REPORTS / "dev.json").read_text(encoding="utf-8"))}
    held = config.REPORTS / "heldout.json"
    if held.exists():
        data["heldout"] = json.loads(held.read_text(encoding="utf-8"))
    web = ROOT / "web" / "public" / "data" / "report.json"
    web.parent.mkdir(parents=True, exist_ok=True)
    web.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    paths.append(web)
    return paths
