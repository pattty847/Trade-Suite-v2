from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class QueryValidationError(ValueError):
    """Raised when a historical query cannot be satisfied."""


class Timeframe(str, Enum):
    M1 = "1m"
    M2 = "2m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"
    W1 = "1wk"
    MO1 = "1mo"


@dataclass(frozen=True, slots=True)
class HistoricalBarsQuery:
    symbol: str
    interval: Timeframe
    start: datetime | None = None
    end: datetime | None = None
    period: str | None = None
    adjusted: bool = True
    include_extended_hours: bool = False
    output_timezone: str = "UTC"

    def validate(self, now: datetime | None = None) -> None:
        if not self.symbol.strip():
            raise QueryValidationError("symbol cannot be empty")

        if self.start and self.end and self.start >= self.end:
            raise QueryValidationError("start must be before end")

        if self.period and (self.start or self.end):
            raise QueryValidationError("use either period or start/end, not both")

        if not self.period and not self.start:
            raise QueryValidationError("start is required when period is not set")

        if now is None:
            now = datetime.now(timezone.utc)

        if self.start and self.start > now + timedelta(minutes=1):
            raise QueryValidationError("start cannot be in the future")


YF_SUPPORTED_INTERVALS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(days=7),
    Timeframe.M2: timedelta(days=60),
    Timeframe.M5: timedelta(days=60),
    Timeframe.M15: timedelta(days=60),
    Timeframe.M30: timedelta(days=60),
    Timeframe.H1: timedelta(days=730),
    Timeframe.D1: timedelta(days=3650),
    Timeframe.W1: timedelta(days=3650),
    Timeframe.MO1: timedelta(days=7300),
}


def validate_yfinance_range(query: HistoricalBarsQuery, now: datetime | None = None) -> None:
    query.validate(now=now)
    if query.period:
        return

    if query.start is None:
        return

    if now is None:
        now = datetime.now(timezone.utc)

    max_span = YF_SUPPORTED_INTERVALS[query.interval]
    if now - query.start > max_span:
        raise QueryValidationError(
            f"yfinance interval {query.interval.value} supports up to {max_span.days} days"
        )
