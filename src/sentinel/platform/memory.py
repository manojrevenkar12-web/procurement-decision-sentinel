"""What managers already said. A card dismissed as within tolerance is not raised again unless the money grows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DismissalMemory:
    factor: float
    _within: dict[tuple[str, str], float] = field(default_factory=dict)
    _not_relevant: set[tuple[str, str]] = field(default_factory=set)

    def record(self, cat_id: str, driver: str, impact_eur: float, reason: str) -> None:
        key = (cat_id, driver)
        if reason == "within_tolerance":
            self._within[key] = max(self._within.get(key, 0.0), abs(impact_eur))

    def suppress(self, cat_id: str, driver: str, impact_eur: float) -> bool:
        if driver.startswith("supplier:"):
            return False  # a supplier in trouble is always shown
        seen = self._within.get((cat_id, driver))
        return seen is not None and abs(impact_eur) <= seen * self.factor

    def to_dict(self) -> dict[str, float]:
        return {f"{c}|{d}": v for (c, d), v in sorted(self._within.items())}
