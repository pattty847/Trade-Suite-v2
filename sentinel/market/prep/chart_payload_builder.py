from __future__ import annotations

from sentinel.market.models import BarSeries, CandleChartPayload, CorporateAction, Marker


class CandleChartPayloadBuilder:
    def build(self, bar_series: BarSeries, actions: list[CorporateAction] | None = None) -> CandleChartPayload:
        bars = bar_series.bars
        x = tuple(bar.ts.timestamp() for bar in bars)
        opens = tuple(bar.open for bar in bars)
        highs = tuple(bar.high for bar in bars)
        lows = tuple(bar.low for bar in bars)
        closes = tuple(bar.close for bar in bars)
        volumes = tuple(bar.volume for bar in bars)

        markers: list[Marker] = []
        if actions:
            for action in actions:
                markers.append(
                    Marker(
                        ts=action.ex_date,
                        label=action.action_type.value,
                        kind="corporate_action",
                        value=action.value,
                    )
                )

        return CandleChartPayload(
            symbol=bar_series.symbol,
            interval=bar_series.interval,
            timezone=bar_series.timezone,
            x=x,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            price_min=min(lows) if lows else None,
            price_max=max(highs) if highs else None,
            markers=tuple(markers),
        )
