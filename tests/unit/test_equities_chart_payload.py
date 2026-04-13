from datetime import datetime, timezone

from sentinel.market.models import Bar, BarSeries, CorporateAction, CorporateActionType
from sentinel.market.prep.chart_payload_builder import CandleChartPayloadBuilder


def test_chart_payload_builder_includes_action_markers() -> None:
    bars = (
        Bar(ts=datetime(2026, 1, 1, tzinfo=timezone.utc), open=10, high=11, low=9, close=10.5, volume=1000),
        Bar(ts=datetime(2026, 1, 2, tzinfo=timezone.utc), open=10.5, high=12, low=10, close=11.5, volume=1200),
    )
    series = BarSeries(
        symbol="AAPL",
        interval="1d",
        timezone="UTC",
        bars=bars,
        adjusted=True,
        include_extended_hours=False,
    )
    actions = [
        CorporateAction(
            symbol="AAPL",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            value=0.2,
        )
    ]

    payload = CandleChartPayloadBuilder().build(series, actions)

    assert payload.price_min == 9
    assert payload.price_max == 12
    assert len(payload.markers) == 1
    assert payload.markers[0].label == "dividend"
