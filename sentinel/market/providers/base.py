from __future__ import annotations

from abc import ABC, abstractmethod

from sentinel.market.models import (
    BarSeries,
    CompanyProfile,
    CorporateAction,
    EquityInstrument,
    NewsItem,
    QuoteSnapshot,
)
from sentinel.market.query import HistoricalBarsQuery


class EquityProvider(ABC):
    provider_name: str

    @abstractmethod
    async def search_symbol(self, text: str, limit: int = 10) -> list[EquityInstrument]:
        raise NotImplementedError

    @abstractmethod
    async def resolve_symbol(self, symbol: str) -> EquityInstrument | None:
        raise NotImplementedError

    @abstractmethod
    async def get_company_profile(self, symbol: str) -> CompanyProfile | None:
        raise NotImplementedError

    @abstractmethod
    async def get_quote_snapshot(self, symbol: str) -> QuoteSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    async def get_historical_bars(self, query: HistoricalBarsQuery) -> BarSeries:
        raise NotImplementedError

    @abstractmethod
    async def get_corporate_actions(
        self,
        symbol: str,
        *,
        start=None,
        end=None,
    ) -> list[CorporateAction]:
        raise NotImplementedError

    @abstractmethod
    async def get_news(self, symbol: str, limit: int = 20) -> list[NewsItem]:
        raise NotImplementedError
