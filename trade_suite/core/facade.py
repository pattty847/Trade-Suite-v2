import logging
import asyncio
from typing import Callable

from .signals import SignalEmitter, Signals
from .task_manager import TaskManager
from .data.data_source import Data
from .data.influx import InfluxDB
from .data.sec_api import SECDataFetcher


logger = logging.getLogger(__name__)

class CoreServicesFacade:
    """
    The CoreServicesFacade is the single, official entry point for any client
    wishing to use the backend services of Trade-Suite.

    It initializes and holds the instances of TaskManager, Data, and SignalEmitter,
    and exposes a clean, high-level API for clients to use.
    """
    def __init__(
        self,
        force_public: bool = True,
        task_mode: str = "thread",
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        """
        Initializes all core backend services. This is a synchronous operation.
        The TaskManager will start its own asyncio event loop in a background thread.
        
        Args:
            force_public (bool): If True, initializes exchange connections
                                 without private API credentials.
        """
        self.emitter = SignalEmitter()
        
        # Initialize components that do not depend on the loop first
        self.influx = InfluxDB()
        self.sec_fetcher = SECDataFetcher()
        self.data = Data(influx=self.influx, emitter=self.emitter, force_public=force_public)

        # The TaskManager is the owner of the asyncio event loop.
        # It creates the loop in a separate thread upon initialization.
        self.task_manager = TaskManager(
            data=self.data,
            sec_fetcher=self.sec_fetcher,
            mode=task_mode,
            loop=loop,
        )
        
        # Now that the TaskManager has a running loop, provide it to the emitter
        # and data source for thread-safe operations.
        self.emitter.set_loop(self.task_manager.loop)
        self.data.task_manager = self.task_manager
        
        logger.info("CoreServicesFacade initialized.")

    def start(self, exchanges: list[str]):
        """
        Starts the core services and loads the necessary exchange data.
        This is a blocking operation that waits for the exchanges to be loaded.

        Args:
            exchanges (list[str]): A list of exchange IDs to load (e.g., ['coinbase', 'binance']).
        """
        if self.task_manager.mode == "external":
            raise RuntimeError("Use await start_async() when TaskManager is in external mode.")
        # Use the task manager to run the async load_exchanges method and wait for it to complete.
        self.task_manager.run_task_until_complete(
            self.data.load_exchanges(exchanges)
        )
        logger.info(f"Core services started for exchanges: {exchanges}")

    async def start_async(self, exchanges: list[str]):
        """Starts core services asynchronously (required for external loop mode)."""
        await self.data.load_exchanges(exchanges)
        logger.info("Core services started asynchronously for exchanges: %s", exchanges)

    def subscribe_to_candles(self, exchange: str, symbol: str, timeframe: str, widget_instance: object):
        """
        High-level method for a client widget to subscribe to candle data.
        
        Args:
            exchange (str): The exchange ID.
            symbol (str): The trading symbol.
            timeframe (str): The candle timeframe (e.g., '1m', '5m', '1h').
            widget_instance (object): The client object (e.g., a GUI widget or a service module)
                                      that is making the subscription. Used for reference counting.
        """
        requirements = {
            "type": "candles",
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
        }
        self.task_manager.subscribe(widget_instance, requirements)
        logger.info(f"Subscription request for candles: {exchange}/{symbol}/{timeframe} for widget {id(widget_instance)}")

    def subscribe_to_trades(self, exchange: str, symbol: str, widget_instance: object):
        """High-level method to subscribe to live trades."""
        requirements = {"type": "trades", "exchange": exchange, "symbol": symbol}
        self.task_manager.subscribe(widget_instance, requirements)
        logger.info(f"Subscription request for trades: {exchange}/{symbol} for widget {id(widget_instance)}")

    def subscribe_to_orderbook(self, exchange: str, symbol: str, widget_instance: object):
        """High-level method to subscribe to order book updates."""
        requirements = {"type": "orderbook", "exchange": exchange, "symbol": symbol}
        self.task_manager.subscribe(widget_instance, requirements)
        logger.info(f"Subscription request for orderbook: {exchange}/{symbol} for widget {id(widget_instance)}")
        
    def subscribe_to_ticker(self, exchange: str, symbol: str, widget_instance: object):
        """High-level method to subscribe to ticker updates."""
        requirements = {"type": "ticker", "exchange": exchange, "symbol": symbol}
        self.task_manager.subscribe(widget_instance, requirements)
        logger.info(f"Subscription request for ticker: {exchange}/{symbol} for widget {id(widget_instance)}")


    def cleanup(self):
        """Shuts down all core services gracefully."""
        logger.info("CoreServicesFacade cleanup initiated.")
        if self.task_manager.mode == "external":
            raise RuntimeError("Use await aclose() in external mode.")
        self.task_manager.cleanup()
        logger.info("CoreServicesFacade cleanup complete.")

    async def aclose(self):
        """Async shutdown path for external loop integrations."""
        logger.info("CoreServicesFacade async cleanup initiated.")
        await self.task_manager.aclose()
        logger.info("CoreServicesFacade async cleanup complete.")
