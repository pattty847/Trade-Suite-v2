#!/usr/bin/env python3
import asyncio
import logging
from typing import Dict, List, Any, Callable, Set
from datetime import datetime
from .async_ccxt_fetcher import AsyncCCXTFetcher

logger = logging.getLogger(__name__)

class TickerStreamer:
    """
    Streams ticker data for multiple symbols
    """
    
    def __init__(self, exchange_id: str = 'coinbase', update_interval: int = 10):
        """
        Initialize ticker streamer
        
        Args:
            exchange_id: CCXT exchange ID to use
            update_interval: Seconds between ticker updates
        """
        self.exchange_id = exchange_id
        self.update_interval = update_interval
        self.fetcher = AsyncCCXTFetcher(exchange_id=exchange_id)
        
        # Track requested symbols
        self.tracked_symbols: Set[str] = set()
        
        # Callbacks for new price data
        self.callbacks: List[Callable[[str, float], None]] = []
        
        # Cache of latest prices
        self.latest_prices: Dict[str, float] = {}
        
        # Flag to control the streaming loop
        self.is_running = False
        self.task = None
    
    async def initialize(self):
        """Initialize the fetcher"""
        await self.fetcher.initialize()
    
    async def close(self):
        """Clean up resources"""
        self.is_running = False
        if self.task and not self.task.done():
            self.task.cancel()
        await self.fetcher.close()
    
    def register_callback(self, callback: Callable[[str, float], None]):
        """
        Register a callback to be called when new price data is available
        
        Args:
            callback: Function taking (symbol, price) arguments
        """
        self.callbacks.append(callback)
    
    def track_symbol(self, symbol: str):
        """
        Start tracking a symbol
        
        Args:
            symbol: Trading symbol
        """
        self.tracked_symbols.add(symbol)
        logger.debug(f"Now tracking ticker for {symbol}")
    
    def untrack_symbol(self, symbol: str):
        """Remove a symbol from tracking"""
        if symbol in self.tracked_symbols:
            self.tracked_symbols.remove(symbol)
            logger.debug(f"Stopped tracking ticker for {symbol}")
    
    async def fetch_loop(self):
        """Main fetch loop for all tracked symbols"""
        logger.info(f"Starting ticker fetch loop for {len(self.tracked_symbols)} symbols (interval: {self.update_interval}s)")
        
        while self.is_running and self.tracked_symbols:
            try:
                # Use the existing fetcher instance to fetch prices individually
                prices = {}
                for symbol in self.tracked_symbols:
                    try:
                        price = await self.fetcher.fetch_current_price(symbol)
                        prices[symbol] = price
                    except Exception as e:
                        logger.error(f"Error fetching price for {symbol}: {e}")
                        prices[symbol] = None
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Process results
                for symbol, price in prices.items():
                    if price is not None:  # Skip failed fetches
                        # Update cache
                        self.latest_prices[symbol] = price
                        
                        # Log at different levels based on frequency
                        logger.debug(f"[{timestamp}] {symbol}: {self.fetcher.format_price(symbol, price)}")
                        
                        # Notify callbacks
                        for callback in self.callbacks:
                            try:
                                callback(symbol, price)
                            except Exception as e:
                                logger.error(f"Error in ticker callback for {symbol}: {e}")
            
            except asyncio.CancelledError:
                logger.info("Ticker fetch loop was cancelled")
                break
            except Exception as e:
                logger.error(f"Error in ticker fetch loop: {e}")
                
            # Wait for next update
            await asyncio.sleep(self.update_interval)
    
    def get_latest_price(self, symbol: str) -> float:
        """
        Get the latest price for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Latest price or None if not available
        """
        return self.latest_prices.get(symbol)
    
    async def start(self):
        """Start streaming data for all tracked symbols"""
        self.is_running = True
        self.task = asyncio.create_task(self.fetch_loop())
        logger.info(f"Started ticker streaming for {len(self.tracked_symbols)} symbols")
    
    async def stop(self):
        """Stop streaming data"""
        self.is_running = False
        await self.close() 