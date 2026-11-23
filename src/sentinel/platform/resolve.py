"""Entity resolution. A name never decides on its own: a supplier matches on stem, legal form and country."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..domain import MasterData
from .evidence import Glossary


@dataclass(frozen=True)
class Resolution:
    outcome: Literal["match", "not_ours", "ambiguous"]
    supplier_id: str | None
    reason: str


def resolve_supplier(name: str, country: str | None, md: MasterData, g: Glossary, strict: bool = True) -> Resolution:
    stem, form = g.split_legal(name)
    cands = [s for s in md.suppliers.values() if g.split_legal(s.legal_name)[0].lower() == stem.lower()]
    if not cands:
        return Resolution("not_ours", None, f"no supplier named '{stem}'")
    if not strict:
        return Resolution("match", cands[0].supplier_id, "matched on name only")
    if form is not None:
        cands = [s for s in cands if g.split_legal(s.legal_name)[1] == form]
        if not cands:
            return Resolution("not_ours", None, f"'{name}' has another legal form than our '{stem}'")
    if country is None:
        return Resolution("ambiguous", None, f"'{stem}' matches our supplier but the country is not backed by a quote")
    cands = [s for s in cands if s.country == country]
    if not cands:
        return Resolution("not_ours", None, f"our '{stem}' sits in another country")
    if len(cands) > 1:
        return Resolution("ambiguous", None, f"{len(cands)} suppliers match '{stem}' in {country}")
    return Resolution("match", cands[0].supplier_id, "stem, legal form and country match")
