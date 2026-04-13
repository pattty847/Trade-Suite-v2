from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from sentinel.market.models import (
    AssetClass,
    BarSeries,
    CompanyProfile,
    CorporateAction,
    EquityInstrument,
    NewsItem,
    QuoteSnapshot,
)
from sentinel.market.normalization.equity_normalizer import EquityNormalizer
from sentinel.market.providers.base import EquityProvider
from sentinel.market.query import HistoricalBarsQuery, validate_yfinance_range


class YFinanceEquityProvider(EquityProvider):
    provider_name = "yfinance"

    def __init__(self, normalizer: EquityNormalizer | None = None) -> None:
        self._normalizer = normalizer or EquityNormalizer()

    async def search_symbol(self, text: str, limit: int = 10) -> list[EquityInstrument]:
        # yfinance does not provide a robust search endpoint.
        # Keep this provider-neutral seam so another provider can support real discovery.
        if not text.strip():
            return []
        resolved = await self.resolve_symbol(text.strip().upper())
        return [resolved] if resolved else []

    async def resolve_symbol(self, symbol: str) -> EquityInstrument | None:
        ticker = await self._ticker(symbol)
        fast_info = await asyncio.to_thread(lambda: ticker.fast_info)
        if fast_info is None:
            return EquityInstrument(symbol=symbol, provider_symbol=symbol)
        return EquityInstrument(
            symbol=symbol,
            provider_symbol=symbol,
            exchange=_fast_info_attr(fast_info, "exchange"),
            currency=_fast_info_attr(fast_info, "currency"),
            timezone=_fast_info_attr(fast_info, "timezone"),
            asset_class=AssetClass.EQUITY,
        )

    async def get_company_profile(self, symbol: str) -> CompanyProfile | None:
        ticker = await self._ticker(symbol)
        info = await asyncio.to_thread(lambda: ticker.info or {})
        if not info:
            return None
        return CompanyProfile(
            symbol=symbol,
            display_name=info.get("longName") or info.get("shortName"),
            long_business_summary=info.get("longBusinessSummary"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            country=info.get("country"),
            website=info.get("website"),
            market_cap=float(info["marketCap"]) if info.get("marketCap") else None,
            employee_count=int(info["fullTimeEmployees"]) if info.get("fullTimeEmployees") else None,
        )

    async def get_quote_snapshot(self, symbol: str) -> QuoteSnapshot | None:
        ticker = await self._ticker(symbol)
        fast_info = await asyncio.to_thread(lambda: ticker.fast_info)
        if fast_info is None:
            return None
        slow_info = await asyncio.to_thread(lambda: ticker.info or {})
        return QuoteSnapshot(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            last=_as_float(_fast_info_attr(fast_info, "last_price")),
            bid=_as_float(slow_info.get("bid")),
            ask=_as_float(slow_info.get("ask")),
            open=_as_float(_fast_info_attr(fast_info, "open")),
            high=_as_float(_fast_info_attr(fast_info, "day_high")),
            low=_as_float(_fast_info_attr(fast_info, "day_low")),
            previous_close=_as_float(_fast_info_attr(fast_info, "previous_close")),
            volume=_as_float(_fast_info_attr(fast_info, "last_volume")),
            currency=_fast_info_attr(fast_info, "currency"),
            market_state=slow_info.get("marketState"),
        )

    async def get_historical_bars(self, query: HistoricalBarsQuery) -> BarSeries:
        validate_yfinance_range(query)
        ticker = await self._ticker(query.symbol)

        history = await asyncio.to_thread(
            ticker.history,
            interval=query.interval.value,
            start=query.start,
            end=query.end,
            period=query.period,
            auto_adjust=query.adjusted,
            prepost=query.include_extended_hours,
            actions=False,
        )

        return self._normalizer.normalize_bars(
            symbol=query.symbol,
            interval=query.interval.value,
            timezone_name=query.output_timezone,
            raw_history=history,
            adjusted=query.adjusted,
            include_extended_hours=query.include_extended_hours,
        )

    async def get_corporate_actions(
        self,
        symbol: str,
        *,
        start=None,
        end=None,
    ) -> list[CorporateAction]:
        ticker = await self._ticker(symbol)
        dividends = await asyncio.to_thread(lambda: ticker.dividends)
        splits = await asyncio.to_thread(lambda: ticker.splits)
        actions = self._normalizer.normalize_actions(symbol=symbol, dividends=dividends, splits=splits)
        if start or end:
            return [a for a in actions if (not start or a.ex_date >= start) and (not end or a.ex_date <= end)]
        return actions

    async def get_news(self, symbol: str, limit: int = 20) -> list[NewsItem]:
        ticker = await self._ticker(symbol)
        raw_news = await asyncio.to_thread(lambda: ticker.news or [])
        items: list[NewsItem] = []
        for article in raw_news[:limit]:
            items.append(
                NewsItem(
                    symbol=symbol,
                    headline=article.get("title", ""),
                    publisher=article.get("publisher"),
                    url=article.get("link"),
                    published_at=datetime.fromtimestamp(article["providerPublishTime"], tz=timezone.utc)
                    if article.get("providerPublishTime")
                    else None,
                    summary=article.get("summary"),
                )
            )
        return items

    async def _ticker(self, symbol: str):
        return yf.Ticker(symbol)


def _as_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _fast_info_attr(fast_info: object, name: str):
    value = getattr(fast_info, name, None)
    if value is None and hasattr(fast_info, "__getitem__"):
        try:
            return fast_info[name]
        except Exception:
            return None
    return value
