import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING
import pandas as pd

from trade_suite.analysis.market_aggregator import MarketAggregator
from .ccxt_interface import CCXTInterface
from .influx import InfluxDB
from ..signals import SignalEmitter
from ..task_manager import TaskManager

from .cache_store import CacheStore
from .candle_fetcher import CandleFetcher
from .streamer import Streamer

if TYPE_CHECKING:
    from sentinel.supervisor import Supervisor as SentinelSupervisor
    from sentinel.alert_bot.manager import AlertDataManager


class Data(CCXTInterface):
    """Facade coordinating cache, fetching and streaming components."""

    def __init__(
        self,
        influx: InfluxDB,
        emitter: SignalEmitter,
        task_manager: Optional[TaskManager] = None,
        exchanges: List[str] | None = None,
        force_public: bool = False,
    ) -> None:
        super().__init__(exchanges, force_public=force_public)
        self.influx = influx
        self.emitter = emitter
        self.task_manager = task_manager
        self.agg = MarketAggregator(influx, emitter)

        self.cache_store = CacheStore()
        self.fetcher = CandleFetcher(self.cache_store, influx)
        self.streamer = Streamer(emitter, self.agg, influx)

        # Placeholders for Sentinel components
        self.sentinel_supervisor: Optional["SentinelSupervisor"] = None
        self.alert_manager: Optional["AlertDataManager"] = None

    async def load_exchanges(self, exchanges: List[str] | None = None) -> None:
        await super().load_exchanges(exchanges)
        # Provide loaded exchanges to helper components
        self.fetcher.set_exchange_list(self.exchange_list)
        self.streamer.set_exchange_list(self.exchange_list)

    def set_ui_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.streamer.set_ui_loop(loop)

    def initialize_sentinel(self, alert_config_path: str):
        """
        Initializes and starts Sentinel components (Supervisor and AlertDataManager).
        """
        # --- Local imports to break circular dependency ---
        from sentinel.supervisor import Supervisor as SentinelSupervisor
        from sentinel.alert_bot.manager import AlertDataManager
        
        logging.info("Initializing Sentinel services within TradeSuite...")

        # 1. Initialize AlertDataManager
        if self.task_manager:
            self.alert_manager = AlertDataManager(
                data_source=self,
                task_manager=self.task_manager,
                signal_emitter=self.emitter,
                config_file_path=alert_config_path
            )
            logging.info("AlertDataManager initialized.")
            # Start monitoring in the background
            asyncio.create_task(self.alert_manager.start_monitoring())
        else:
            logging.warning("TaskManager not provided. Cannot initialize AlertDataManager.")

        # 2. Initialize Sentinel Supervisor
        # We will need to modify Supervisor to accept 'self' as the data_source
        self.sentinel_supervisor = SentinelSupervisor(data_source=self)
        logging.info("Sentinel Supervisor initialized.")
        # Start the supervisor's tasks in the background
        asyncio.create_task(self.sentinel_supervisor.start())

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

    async def fetch_historical_trades(self, exchange: str, symbol: str, since: Optional[int] = None, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetches historical trade data for a given symbol from an exchange.

        This is a passthrough to the underlying ccxt_interface method.
        """
        logging.debug(f"Fetching historical trades for {symbol} on {exchange} (since: {since}, limit: {limit})")
        
        exchange_instance = self.exchange_list.get(exchange)
        if not exchange_instance:
            logging.error(f"Exchange '{exchange}' not loaded in CCXTInterface.")
            return []
            
        try:
            # CCXT's fetch_trades returns a list of trade dicts
            trades = await exchange_instance.fetch_trades(symbol, since=since, limit=limit)
            logging.info(f"Fetched {len(trades)} historical trades for {symbol} on {exchange}.")
            return trades
        except Exception as e:
            logging.error(f"Error fetching historical trades for {symbol} on {exchange}: {e}", exc_info=True)
            return []

