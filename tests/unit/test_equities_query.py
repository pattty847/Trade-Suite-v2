from datetime import datetime, timedelta, timezone

import pytest

from sentinel.market.query import HistoricalBarsQuery, QueryValidationError, Timeframe, validate_yfinance_range


def test_query_rejects_period_and_range_mix() -> None:
    query = HistoricalBarsQuery(
        symbol="AAPL",
        interval=Timeframe.D1,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period="1mo",
    )
    with pytest.raises(QueryValidationError):
        query.validate(now=datetime(2026, 1, 2, tzinfo=timezone.utc))


def test_validate_yfinance_range_rejects_old_intraday() -> None:
    now = datetime(2026, 4, 13, tzinfo=timezone.utc)
    query = HistoricalBarsQuery(
        symbol="AAPL",
        interval=Timeframe.M1,
        start=now - timedelta(days=30),
        end=now,
    )
    with pytest.raises(QueryValidationError):
        validate_yfinance_range(query, now=now)
