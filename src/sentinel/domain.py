"""Shared shapes. Master data and messages are what the sentinel may see; the truth is defined in world/."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["commodity_move", "tariff", "supplier_event", "other"]
EventType = Literal["insolvency", "outage", "sanction", "esg"]
Status = Literal["confirmed", "unconfirmed", "withdrawn"]
Mechanism = Literal["index_linked", "fixed", "cost_plus"]
FIELDS = ("commodity", "magnitude", "country", "supplier", "supplier_country", "event")


# --- master data: the buyer's own systems (spend cube, supplier master, contracts, disclosures) ---


@dataclass(frozen=True)
class CategoryMD:
    cat_id: str
    label: str
    spend_eur: float
    weights: dict[str, float]  # should-cost estimates, not the truth
    manager: int


@dataclass(frozen=True)
class SupplierMD:
    supplier_id: str
    legal_name: str
    country: str


@dataclass(frozen=True)
class ContractMD:
    contract_id: str
    supplier_id: str
    cat_id: str
    annual_spend_eur: float
    mechanism: Mechanism
    index_commodity: str | None
    renewal_day: int | None


@dataclass(frozen=True)
class Tier2MD:
    supplier_id: str
    commodity: str
    country: str
    share: float


@dataclass(frozen=True)
class MasterData:
    categories: dict[str, CategoryMD]
    suppliers: dict[str, SupplierMD]
    contracts: tuple[ContractMD, ...]
    tier2: tuple[Tier2MD, ...]


@dataclass(frozen=True)
class Message:
    msg_id: str
    source: str
    published_h: float
    headline: str
    body: str

    @property
    def text(self) -> str:
        return self.headline + "\n" + self.body


# --- what a model returns: a claim about one article, with quotes ---


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["commodity", "magnitude", "country", "supplier", "supplier_country", "event", "status"]
    quote: str = Field(max_length=600)


class SignalRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    commodity: str | None = None
    country: str | None = None
    supplier_name: str | None = None
    supplier_country: str | None = None
    magnitude_pct: float | None = Field(default=None, ge=-100, le=100)
    event: EventType | None = None
    status: Status
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    affected_categories: list[str] = Field(default_factory=list, max_length=20)  # read only by the model-alone design
    urgency: Literal["low", "medium", "high"] = "low"


@dataclass(frozen=True)
class Prompt:
    msg_id: str
    system: str
    user: str
    mode: Literal["extract", "alone"]
    attempt: int = 0
    previous_error: str | None = None


@dataclass(frozen=True)
class Reply:
    text: str
    tokens_in: int
    tokens_cached: int
    tokens_out: int
    latency_s: float


# --- what code decided ---


@dataclass(frozen=True)
class Facts:
    """Checked facts. Every field here was quoted from the article or set by a person at the desk."""

    kind: Kind
    status: Status
    commodity: str | None = None
    country: str | None = None
    supplier_id: str | None = None
    magnitude: float | None = None  # fraction, signed
    event: EventType | None = None
    quotes: tuple[tuple[str, str], ...] = ()  # (field, quote)
    source: Literal["model", "desk"] = "model"

    def driver(self) -> str:
        if self.kind == "commodity_move":
            return f"commodity:{self.commodity}"
        if self.kind == "tariff":
            return f"tariff:{self.country}:{self.commodity}"
        return f"supplier:{self.supplier_id}:{self.event}"

    def fact_key(self, bucket: float) -> str:
        mag = "" if self.magnitude is None else str(round(self.magnitude * 100 / bucket))
        return f"{self.driver()}:{mag}"


@dataclass(frozen=True)
class Exposure:
    cat_id: str
    impact_eur: float
    lever: str
    path: tuple[str, ...]
    contract_id: str


@dataclass
class Card:
    card_id: str
    key: str
    cat_id: str
    driver: str
    kind: Kind
    impact_eur: float
    lever: str
    path: tuple[str, ...]
    evidence: tuple[tuple[str, str], ...]
    msg_ids: list[str]
    created_h: float
    manager: int
    status: Literal["open", "accepted", "dismissed", "suppressed"] = "open"
    corroborations: int = 0
    notes: list[str] = field(default_factory=list)
