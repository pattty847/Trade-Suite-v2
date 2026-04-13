from __future__ import annotations

from datetime import timedelta

from sentinel.market.cache.base import CacheStore
from sentinel.market.models import BarSeries, CorporateAction, QuoteSnapshot
from sentinel.market.providers.base import EquityProvider
from sentinel.market.query import HistoricalBarsQuery


class EquitiesService:
    def __init__(
        self,
        *,
        provider: EquityProvider,
        bar_cache: CacheStore[BarSeries],
        quote_cache: CacheStore[QuoteSnapshot],
    ) -> None:
        self._provider = provider
        self._bar_cache = bar_cache
        self._quote_cache = quote_cache

    async def get_historical_bars(self, query: HistoricalBarsQuery, *, force_refresh: bool = False) -> BarSeries:
        key = self._bars_cache_key(query)
        if not force_refresh:
            cached = self._bar_cache.get(key)
            if cached is not None:
                return cached

        bars = await self._provider.get_historical_bars(query)
        ttl = timedelta(minutes=2 if query.interval.value.endswith("m") or query.interval.value.endswith("h") else 30)
        self._bar_cache.put(key, bars, ttl)
        return bars

    async def get_quote_snapshot(self, symbol: str, *, force_refresh: bool = False) -> QuoteSnapshot | None:
        key = f"quote:{symbol.upper()}"
        if not force_refresh:
            cached = self._quote_cache.get(key)
            if cached is not None:
                return cached

        quote = await self._provider.get_quote_snapshot(symbol)
        if quote is not None:
            self._quote_cache.put(key, quote, timedelta(seconds=15))
        return quote

    async def get_corporate_actions(
        self,
        symbol: str,
        *,
        start=None,
        end=None,
    ) -> list[CorporateAction]:
        return await self._provider.get_corporate_actions(symbol, start=start, end=end)

    @staticmethod
    def _bars_cache_key(query: HistoricalBarsQuery) -> str:
        return "|".join(
            [
                "bars",
                query.symbol.upper(),
                query.interval.value,
                query.start.isoformat() if query.start else "",
                query.end.isoformat() if query.end else "",
                query.period or "",
                "adj" if query.adjusted else "raw",
                "ext" if query.include_extended_hours else "rth",
                query.output_timezone,
            ]
        )
