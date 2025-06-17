"""Example autonomous agent implementations."""

import asyncio
from typing import Any

from trade_suite.data.data_source import Data
from sentinel.alert_bot.manager import AlertDataManager

from .base import Agent


class MonitorAgent(Agent):
    """Agent that monitors real-time market data."""

    def __init__(self, name: str, data: Data) -> None:
        super().__init__(name)
        self.data = data

    async def run(self) -> None:
        while True:
            trades = await self.data.get_trades("coinbase", "BTC/USD", limit=10)
            self.memory["last_trades"] = trades
            await asyncio.sleep(5)


class ScraperAgent(Agent):
    """Agent that monitors SEC filings via Sentinel."""

    def __init__(self, name: str, alert_manager: AlertDataManager) -> None:
        super().__init__(name)
        self.alert_manager = alert_manager

    async def run(self) -> None:
        while True:
            await self.alert_manager.poll()
            await asyncio.sleep(10)


class SynthesisAgent(Agent):
    """Agent that synthesizes reports using CopeNet tools."""

    def __init__(self, name: str) -> None:
        super().__init__(name)

    async def run(self) -> None:
        await asyncio.sleep(1)
        # Placeholder for LLM-based report generation
