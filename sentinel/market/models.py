from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping, Sequence


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    ADR = "adr"
    UNKNOWN = "unknown"


class CorporateActionType(str, Enum):
    DIVIDEND = "dividend"
    SPLIT = "split"
    EARNINGS = "earnings"


@dataclass(frozen=True, slots=True)
class EquityInstrument:
    symbol: str
    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    timezone: str | None = None
    asset_class: AssetClass = AssetClass.UNKNOWN
    provider_symbol: str | None = None
    primary_mic: str | None = None


@dataclass(frozen=True, slots=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    vwap: float | None = None
    trade_count: int | None = None


@dataclass(frozen=True, slots=True)
class BarSeries:
    symbol: str
    interval: str
    timezone: str
    bars: tuple[Bar, ...]
    adjusted: bool
    include_extended_hours: bool
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    symbol: str
    timestamp: datetime | None
    last: float | None
    bid: float | None = None
    ask: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    volume: float | None = None
    currency: str | None = None
    market_state: str | None = None


@dataclass(frozen=True, slots=True)
class CorporateAction:
    symbol: str
    action_type: CorporateActionType
    ex_date: datetime
    value: float | None = None
    ratio_from: float | None = None
    ratio_to: float | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CompanyProfile:
    symbol: str
    display_name: str | None = None
    long_business_summary: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    website: str | None = None
    market_cap: float | None = None
    employee_count: int | None = None


@dataclass(frozen=True, slots=True)
class NewsItem:
    symbol: str
    headline: str
    publisher: str | None
    url: str | None
    published_at: datetime | None
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class Marker:
    ts: datetime
    label: str
    kind: str
    value: float | None = None


@dataclass(frozen=True, slots=True)
class CandleChartPayload:
    symbol: str
    interval: str
    timezone: str
    x: tuple[float, ...]
    opens: tuple[float, ...]
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    closes: tuple[float, ...]
    volumes: tuple[float | None, ...]
    price_min: float | None
    price_max: float | None
    markers: Sequence[Marker] = field(default_factory=tuple)
    overlays: Mapping[str, Sequence[float]] = field(default_factory=dict)
