#!/usr/bin/env python3
import asyncio
import logging
from typing import Dict, List, Any, Callable, Set, Optional
from datetime import datetime, timedelta
import ccxt.pro

logger = logging.getLogger(__name__)

class OHLCVStreamer:
    """
    Streams OHLCV (candle) data for multiple symbols and timeframes using ccxt.pro
    """
    
    def __init__(self, exchange_id: str = 'coinbase'):
        """
        Initialize OHLCV streamer
        
        Args:
            exchange_id: CCXT.pro exchange ID to use
        """
        self.exchange_id = exchange_id
        try:
            exchange_class = getattr(ccxt.pro, self.exchange_id)
            self.exchange = exchange_class()
        except AttributeError:
            logger.error(f"Exchange {self.exchange_id} not found in ccxt.pro. Ensure it's a valid ccxt.pro exchange ID.")
            raise ValueError(f"Unsupported exchange for ccxt.pro OHLCV streaming: {self.exchange_id}")
        
        # Track requested symbol/timeframe combinations
        self.tracked_items: Dict[str, Set[int]] = {}  # {symbol: {timeframe_minutes1, ...}}
        
        # Callbacks for new data
        self.callbacks: List[Callable[[str, int, List[list]], None]] = []
        
        # Cache of latest data
        self.latest_data: Dict[str, Dict[int, List[list]]] = {}  # {symbol: {timeframe_minutes: candles}}
        
        # Flag to control the streaming loop
        self.is_running = False
        self.fetch_tasks = []
    
    @staticmethod
    def _minutes_to_timeframe_string(minutes: int) -> str:
        """Converts minutes to ccxt timeframe string (e.g., 1, 5, 15, 60 -> '1m', '5m', '15m', '1h')"""
        if minutes < 60:
            return f'{minutes}m'
        elif minutes % 60 == 0:
            hours = minutes // 60
            if hours < 24:
                return f'{hours}h'
            elif hours % 24 == 0:
                days = hours // 24
                return f'{days}d'
            else: # e.g. 36h, ccxt might not support all of these, check exchange specifics
                 return f'{hours}h' # Or handle as error/specific conversion
        else: # e.g. 90m might be '1h30m' or might not be supported directly. 
              # For simplicity, sticking to common ones. Or raise error for unsupported.
            logger.warning(f"Timeframe {minutes}m may not be directly supported by all exchanges. Attempting {minutes}m.")
            return f'{minutes}m' 

    async def initialize(self):
        """Initialize the streamer. (ccxt.pro usually connects on first watch call)"""
        pass
    
    async def close(self):
        """Clean up resources"""
        self.is_running = False
        # Cancel any running fetch tasks
        for task in self.fetch_tasks:
            if not task.done():
                task.cancel()
        if self.fetch_tasks: # Ensure all tasks are awaited
            await asyncio.gather(*self.fetch_tasks, return_exceptions=True)

        if hasattr(self.exchange, 'close'):
            await self.exchange.close()
        logger.info("OHLCVStreamer closed.")
    
    def register_callback(self, callback: Callable[[str, int, List[list]], None]):
        """
        Register a callback to be called when new data is available
        
        Args:
            callback: Function taking (symbol, timeframe_minutes, candles) arguments
        """
        self.callbacks.append(callback)
    
    def track_symbol_timeframe(self, symbol: str, timeframe_minutes: int):
        """
        Start tracking a symbol/timeframe combination
        
        Args:
            symbol: Trading symbol
            timeframe_minutes: Timeframe in minutes (e.g., 1, 5, 60)
        """
        if not self.exchange.has.get('watchOHLCV'):
            logger.error(f"Exchange {self.exchange_id} does not support watchOHLCV. Cannot track {symbol} {timeframe_minutes}m.")
            return

        timeframe_str = self._minutes_to_timeframe_string(timeframe_minutes)
        if timeframe_str not in self.exchange.timeframes:
            logger.warning(f"Timeframe {timeframe_minutes}m (parsed as {timeframe_str}) may not be supported by {self.exchange_id}. Known timeframes: {list(self.exchange.timeframes.keys()) if self.exchange.timeframes else 'None'}. Attempting anyway.")
            # Depending on strictness, one might choose to return or raise an error here.

        if symbol not in self.tracked_items:
            self.tracked_items[symbol] = set()
            self.latest_data[symbol] = {} # Initialize symbol cache
        
        is_new_tracking = timeframe_minutes not in self.tracked_items[symbol]
        self.tracked_items[symbol].add(timeframe_minutes)
        
        if symbol not in self.latest_data:
            self.latest_data[symbol] = {}
        if timeframe_minutes not in self.latest_data[symbol]:
            self.latest_data[symbol][timeframe_minutes] = [] # Initialize timeframe cache

        logger.info(f"Now tracking {symbol} with {timeframe_minutes}m timeframe (using string: {timeframe_str})")

        # If already running and this is a newly tracked item, start its watch task
        if self.is_running and is_new_tracking:
            logger.info(f"Dynamically starting OHLCV watch for newly tracked {symbol} {timeframe_minutes}m.")
            task = asyncio.create_task(self.watch_ohlcv_for_item(symbol, timeframe_minutes))
            self.fetch_tasks.append(task)
    
    async def watch_ohlcv_for_item(self, symbol: str, timeframe_minutes: int):
        """
        Continuously watch OHLCV data for a specific symbol/timeframe using ccxt.pro.
        
        Args:
            symbol: Trading symbol
            timeframe_minutes: Timeframe in minutes
        """
        timeframe_str = self._minutes_to_timeframe_string(timeframe_minutes)
        
        # Initialize cache for this symbol/timeframe if not done already (should be by track_symbol_timeframe)
        if symbol not in self.latest_data or timeframe_minutes not in self.latest_data[symbol]:
            if symbol not in self.latest_data: self.latest_data[symbol] = {}
            self.latest_data[symbol][timeframe_minutes] = []
            logger.warning(f"Cache for {symbol} {timeframe_minutes}m initialized late in watch_ohlcv_for_item.")

        logger.info(f"Starting ccxt.pro watchOHLCV loop for {symbol} {timeframe_str} (orig_min: {timeframe_minutes}m)")
        
        # Limit for watchOHLCV typically means the number of candles returned in each update list.
        # Default is often suitable, but can be specified if needed.
        # Some exchanges might have specific limits or behaviors.
        watch_limit = 100 # Number of candles to keep in the returned list from watchOHLCV

        while self.is_running and symbol in self.tracked_items and timeframe_minutes in self.tracked_items[symbol]:
            try:
                # watchOHLCV(symbol, timeframe, since=None, limit=None, params={})
                candles = await self.exchange.watchOHLCV(symbol, timeframe=timeframe_str, limit=watch_limit)
                
                if candles:
                    # self.latest_data[symbol][timeframe_minutes] = candles
                    # Filter out empty lists that some exchanges might send during subscription or initial connection
                    if not isinstance(candles, list) or not all(isinstance(c, list) for c in candles):
                        logger.warning(f"Received non-standard OHLCV data for {symbol} {timeframe_str}: {candles}")
                        continue # Skip this update
                    
                    # Ensure candles are not empty before proceeding
                    if not candles:
                        logger.debug(f"Received empty candle list for {symbol} {timeframe_str}. Skipping update.")
                        continue

                    # Update cache. watchOHLCV returns the list of candles. 
                    # It's important to understand if this is incremental or the full historical set (up to a limit).
                    # CCXT Pro typically provides the most recent set of N candles.
                    self.latest_data[symbol][timeframe_minutes] = candles
                    
                    # Notify callbacks
                    for callback in self.callbacks:
                        try:
                            # Ensure callback is awaitable if it does I/O
                            if asyncio.iscoroutinefunction(callback):
                                await callback(symbol, timeframe_minutes, candles)
                            else:
                                callback(symbol, timeframe_minutes, candles)
                        except Exception as e:
                            logger.error(f"Error in OHLCV callback for {symbol} {timeframe_minutes}m: {e}", exc_info=True)
                else:
                    logger.debug(f"watchOHLCV for {symbol} {timeframe_str} returned no data (None or empty list).")

            except ccxt.pro.NetworkError as e:
                logger.error(f"ccxt.pro NetworkError for {symbol} {timeframe_str}: {e}. Retrying connection...")
                await asyncio.sleep(5) # Wait before retrying
            except ccxt.pro.ExchangeError as e:
                logger.error(f"ccxt.pro ExchangeError for {symbol} {timeframe_str}: {e}. May need to handle specific errors.")
                await asyncio.sleep(5) 
            except asyncio.CancelledError:
                logger.info(f"OHLCV watch for {symbol} {timeframe_str} was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error watching OHLCV for {symbol} {timeframe_str}: {e}", exc_info=True)
                # Basic backoff, ccxt.pro might handle some retries internally too.
                await asyncio.sleep(self.exchange.rateLimit / 1000 if hasattr(self.exchange, 'rateLimit') else 1)
            
            # No explicit sleep needed here; watchOHLCV is a long-polling or websocket method.
            # It resolves when new data is available or a timeout occurs internally (which ccxt.pro handles).

    def get_latest_data(self, symbol: str, timeframe_minutes: int) -> List[list]:
        """
        Get the latest data for a symbol/timeframe
        
        Args:
            symbol: Trading symbol
            timeframe_minutes: Timeframe in minutes
            
        Returns:
            Latest OHLCV candles or empty list if not available
        """
        return self.latest_data.get(symbol, {}).get(timeframe_minutes, [])
    
    async def start(self):
        """Start streaming data for all tracked symbols/timeframes"""
        if not self.exchange.has.get('watchOHLCV'):
            logger.error(f"Exchange {self.exchange_id} does not support watchOHLCV. OHLCVStreamer cannot start.")
            self.is_running = False
            return

        self.is_running = True
        self.fetch_tasks = [] # Clear any previous tasks
        
        logger.info(f"Starting OHLCVStreamer with exchange: {self.exchange_id}")
        # Start a watch task for each symbol/timeframe combination
        for symbol, timeframes in list(self.tracked_items.items()): # Iterate over a copy
            for timeframe_minutes in list(timeframes): # Iterate over a copy
                # Ensure cache is initialized before starting task
                if symbol not in self.latest_data:
                    self.latest_data[symbol] = {}
                if timeframe_minutes not in self.latest_data[symbol]:
                    self.latest_data[symbol][timeframe_minutes] = []
                
                task = asyncio.create_task(self.watch_ohlcv_for_item(symbol, timeframe_minutes))
                self.fetch_tasks.append(task)
                
        if self.fetch_tasks:
            logger.info(f"Started OHLCV streaming for {len(self.fetch_tasks)} symbol/timeframe combinations using ccxt.pro")
        else:
            logger.info("No symbol/timeframe combinations to stream OHLCV for.")
    
    async def stop(self):
        """Stop streaming data"""
        self.is_running = False
        await self.close() 