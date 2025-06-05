import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional
import pandas as pd

from trade_suite.analysis.market_aggregator import MarketAggregator
from trade_suite.data.ccxt_interface import CCXTInterface
from trade_suite.data.influx import InfluxDB
from trade_suite.gui.signals import SignalEmitter

from .cache_store import CacheStore
from .candle_fetcher import CandleFetcher
from .streamer import Streamer


class Data(CCXTInterface):
    """Facade coordinating cache, fetching and streaming components."""

    def __init__(
        self,
        influx: InfluxDB,
        emitter: SignalEmitter,
        exchanges: List[str] | None = None,
        force_public: bool = False,
    ) -> None:
        super().__init__(exchanges, force_public=force_public)
        self.influx = influx
        self.emitter = emitter
        self.agg = MarketAggregator(influx, emitter)

        self.cache_store = CacheStore()
        self.fetcher = CandleFetcher(self.cache_store, influx)
        self.streamer = Streamer(emitter, self.agg, influx)

    async def load_exchanges(self, exchanges: List[str] | None = None) -> None:
        await super().load_exchanges(exchanges)
        # Provide loaded exchanges to helper components
        self.fetcher.set_exchange_list(self.exchange_list)
        self.streamer.set_exchange_list(self.exchange_list)

    def set_ui_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.streamer.set_ui_loop(loop)

    # --- Streaming wrappers -------------------------------------------------
    async def watch_trades_list(
        self,
        symbols: List[str],
        stop_event: asyncio.Event,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
    ) -> None:
        await self.streamer.watch_trades_list(symbols, stop_event, track_stats, write_trades, write_stats)

    async def watch_trades(
        self,
        symbol: str,
        exchange: str,
        stop_event: asyncio.Event,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
        sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        queue: asyncio.Queue | None = None,
    ) -> None:
        await self.streamer.watch_trades(
            symbol,
            exchange,
            stop_event,
            track_stats,
            write_trades,
            write_stats,
            sink,
            queue,
        )

    async def watch_orderbooks(self, symbols: List[str], stop_event: asyncio.Event) -> None:
        await self.streamer.watch_orderbooks(symbols, stop_event)

    async def watch_orderbook(
        self,
        exchange: str,
        symbol: str,
        stop_event: asyncio.Event,
        sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        queue: asyncio.Queue | None = None,
        cadence_ms: int = 500,
    ) -> None:
        await self.streamer.watch_orderbook(exchange, symbol, stop_event, sink, queue, cadence_ms)

    async def watch_ticker(self, exchange_id: str, symbol: str, stop_event: asyncio.Event) -> None:
        await self.streamer.watch_ticker(exchange_id, symbol, stop_event)

    # --- Historical / candle data ------------------------------------------
    async def fetch_candles(
        self,
        exchanges: List[str],
        symbols: List[str],
        since: str,
        timeframes: List[str],
        write_to_db: bool = False,
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        return await self.fetcher.fetch_candles(exchanges, symbols, since, timeframes, write_to_db)

