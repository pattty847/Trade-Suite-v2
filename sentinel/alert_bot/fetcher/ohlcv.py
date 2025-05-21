#!/usr/bin/env python3
import asyncio
import logging
from typing import Dict, List, Any, Callable, Set
from datetime import datetime, timedelta
from .async_ccxt_fetcher import AsyncCCXTFetcher

logger = logging.getLogger(__name__)

class OHLCVStreamer:
    """
    Streams OHLCV (candle) data for multiple symbols and timeframes
    """
    
    def __init__(self, exchange_id: str = 'coinbase'):
        """
        Initialize OHLCV streamer
        
        Args:
            exchange_id: CCXT exchange ID to use
        """
        self.exchange_id = exchange_id
        self.fetcher = AsyncCCXTFetcher(exchange_id=exchange_id)
        
        # Track requested symbol/timeframe combinations
        self.tracked_items: Dict[str, Set[int]] = {}  # {symbol: {timeframe1, timeframe2, ...}}
        
        # Callbacks for new data
        self.callbacks: List[Callable[[str, int, List[list]], None]] = []
        
        # Cache of latest data
        self.latest_data: Dict[str, Dict[int, List[list]]] = {}  # {symbol: {timeframe: candles}}
        
        # Fetch intervals (how often to refresh data for each timeframe)
        self.fetch_intervals: Dict[int, int] = {}  # {timeframe_minutes: interval_seconds}
        
        # Flag to control the streaming loop
        self.is_running = False
        self.fetch_tasks = []
    
    async def initialize(self):
        """Initialize the fetcher"""
        await self.fetcher.initialize()
    
    async def close(self):
        """Clean up resources"""
        self.is_running = False
        # Cancel any running fetch tasks
        for task in self.fetch_tasks:
            if not task.done():
                task.cancel()
        await self.fetcher.close()
    
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
            timeframe_minutes: Timeframe in minutes
        """
        if symbol not in self.tracked_items:
            self.tracked_items[symbol] = set()
        
        self.tracked_items[symbol].add(timeframe_minutes)
        logger.debug(f"Now tracking {symbol} with {timeframe_minutes}m timeframe")
        
        # Set up fetch interval for this timeframe (if not already set)
        if timeframe_minutes not in self.fetch_intervals:
            # Set fetch interval to half the timeframe, but minimum 30 seconds
            interval_seconds = max(30, timeframe_minutes * 60 // 2)
            self.fetch_intervals[timeframe_minutes] = interval_seconds
    
    async def fetch_symbol_timeframe(self, symbol: str, timeframe_minutes: int):
        """
        Continuously fetch data for a symbol/timeframe
        
        Args:
            symbol: Trading symbol
            timeframe_minutes: Timeframe in minutes
        """
        interval_seconds = self.fetch_intervals[timeframe_minutes]
        
        # Initialize cache for this symbol/timeframe if needed
        if symbol not in self.latest_data:
            self.latest_data[symbol] = {}
        
        logger.info(f"Starting OHLCV fetch loop for {symbol} {timeframe_minutes}m (interval: {interval_seconds}s)")
        
        while self.is_running and symbol in self.tracked_items and timeframe_minutes in self.tracked_items[symbol]:
            try:
                # Request 100 candles to ensure we have enough historical data for all rule types
                candles = await self.fetcher.fetch_ohlcv(symbol, timeframe_minutes, limit=100)
                
                if candles:
                    # Update cache
                    self.latest_data[symbol][timeframe_minutes] = candles
                    
                    # Notify callbacks
                    for callback in self.callbacks:
                        try:
                            callback(symbol, timeframe_minutes, candles)
                        except Exception as e:
                            logger.error(f"Error in OHLCV callback for {symbol}: {e}")
            
            except asyncio.CancelledError:
                logger.info(f"OHLCV fetch for {symbol} {timeframe_minutes}m was cancelled")
                break
            except Exception as e:
                logger.error(f"Error fetching OHLCV for {symbol} {timeframe_minutes}m: {e}")
                
            # Wait for next fetch interval
            await asyncio.sleep(interval_seconds)
    
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
        self.is_running = True
        
        # Start a fetch task for each symbol/timeframe combination
        for symbol, timeframes in self.tracked_items.items():
            for timeframe in timeframes:
                task = asyncio.create_task(self.fetch_symbol_timeframe(symbol, timeframe))
                self.fetch_tasks.append(task)
                
        logger.info(f"Started OHLCV streaming for {len(self.fetch_tasks)} symbol/timeframe combinations")
    
    async def stop(self):
        """Stop streaming data"""
        self.is_running = False
        await self.close() 