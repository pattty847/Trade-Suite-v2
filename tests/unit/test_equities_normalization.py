from datetime import datetime, timezone

import pandas as pd

from sentinel.market.normalization.equity_normalizer import EquityNormalizer


def test_normalize_bars_sorts_and_deduplicates() -> None:
    index = pd.to_datetime(
        [
            "2026-01-02T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ]
    )
    df = pd.DataFrame(
        {
            "Open": [10.0, 9.0, 9.1],
            "High": [11.0, 10.0, 10.1],
            "Low": [9.0, 8.0, 8.1],
            "Close": [10.5, 9.5, 9.6],
            "Volume": [100, 200, 300],
        },
        index=index,
    )

    normalizer = EquityNormalizer()
    series = normalizer.normalize_bars(
        symbol="AAPL",
        interval="1d",
        timezone_name="UTC",
        raw_history=df,
        adjusted=False,
        include_extended_hours=False,
    )

    assert len(series.bars) == 2
    assert series.bars[0].ts == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert series.bars[0].open == 9.1
