#!/usr/bin/env python3
import ccxt.async_support as ccxt_async
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger(__name__)

class AsyncCCXTFetcher:
    """
    Asynchronous data fetcher using CCXT library's async support
    """
    
    def __init__(self, 
                 exchange_id: str = 'coinbase',
                 rate_limit_sleep: float = 1.0):
        """
        Initialize async CCXT fetcher
        
        Args:
            exchange_id: CCXT exchange ID to use
            rate_limit_sleep: Sleep time between API requests to avoid rate limits
        """
        self.exchange_id = exchange_id
        self.rate_limit_sleep = rate_limit_sleep
        
        # Create async exchange instance
        self.exchange = getattr(ccxt_async, exchange_id)()
        
        # Cache for market info
        self.markets = {}
        self.last_ticker_prices: Dict[str, Dict[str, Any]] = {}
        self.ohlcv_data: Dict[str, Dict[str, List[list]]] = {}
        self.last_ohlcv_fetch_time: Dict[str, Dict[str, datetime]] = {}
    
    async def initialize(self):
        """Initialize exchange and load markets"""
        try:
            await self.exchange.load_markets()
            self.markets = self.exchange.markets
            logger.info(f"Loaded {len(self.markets)} markets from {self.exchange_id}")
        except Exception as e:
            logger.error(f"Error loading markets from {self.exchange_id}: {e}")
        
    def _convert_symbol_format(self, symbol: str) -> str:
        """
        Convert symbol format if needed for specific exchanges
        
        Args:
            symbol: Trading symbol (e.g., BTC/USD)
            
        Returns:
            Properly formatted symbol for the current exchange
        """
        # Check if the symbol exists as-is in the markets
        if symbol in self.markets:
            return symbol
            
        # Try different formats based on exchange
        if self.exchange_id == 'coinbase':
            # Try with dash instead of slash
            alt_symbol = symbol.replace('/', '-')
            if alt_symbol in self.markets:
                logger.debug(f"Converted symbol format from {symbol} to {alt_symbol}")
                return alt_symbol
        
        # Default to original symbol if no conversion worked
        return symbol
        
    async def close(self):
        """Close the exchange connection"""
        await self.exchange.close()
        
    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols"""
        return list(self.markets.keys())
    
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Asynchronously fetch current ticker data for symbol
        
        Args:
            symbol: Trading symbol (e.g., BTC/USD)
            
        Returns:
            Ticker data dictionary with at least 'last' price
            
        Raises:
            Exception if fetch fails
        """
        try:
            # Use the symbol as is in the cache
            formatted_symbol = symbol
            
            # Try to fetch with the original symbol
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
            except Exception as first_error:
                # If that fails, try with an alternative format
                logger.debug(f"Initial fetch for {symbol} failed, trying alternative format")
                formatted_symbol = self._convert_symbol_format(symbol)
                
                if formatted_symbol != symbol:
                    ticker = await self.exchange.fetch_ticker(formatted_symbol)
                else:
                    # If no alternative format was found, re-raise the original error
                    raise first_error
                
            self.last_ticker_prices[symbol] = ticker
            await asyncio.sleep(self.rate_limit_sleep)  # Avoid rate limits
            logger.debug(f"Fetched ticker for {symbol}: {ticker['last']}")
            return ticker
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            raise
    
    async def fetch_current_price(self, symbol: str) -> float:
        """
        Asynchronously fetch just the current price for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price
            
        Raises:
            Exception if fetch fails
        """
        ticker = await self.fetch_ticker(symbol)
        return ticker['last']
    
    def _get_ccxt_timeframe(self, minutes: int) -> Optional[str]:
        """
        Convert minutes to CCXT timeframe string
        
        Args:
            minutes: Timeframe in minutes
            
        Returns:
            CCXT timeframe string or None if invalid
        """
        if minutes < 1:
            return None
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:  # Less than a day
            hours = minutes // 60
            return f"{hours}h"
        else:  # Days
            days = minutes // 1440
            return f"{days}d"
    
    async def fetch_ohlcv(self, symbol: str, timeframe_minutes: int, limit: int = 50) -> List[list]:
        """
        Asynchronously fetch OHLCV (candle) data for a symbol
        
        Args:
            symbol: Trading symbol
            timeframe_minutes: Timeframe in minutes
            limit: Number of candles to fetch
            
        Returns:
            List of OHLCV candles [timestamp, open, high, low, close, volume]
            
        Raises:
            Exception if fetch fails
        """
        ccxt_tf = self._get_ccxt_timeframe(timeframe_minutes)
        if not ccxt_tf:
            raise ValueError(f"Invalid timeframe: {timeframe_minutes} minutes")
        
        try:
            # Create nested dictionaries if they don't exist
            if symbol not in self.ohlcv_data:
                self.ohlcv_data[symbol] = {}
            if symbol not in self.last_ohlcv_fetch_time:
                self.last_ohlcv_fetch_time[symbol] = {}
            
            # Try with original symbol first
            try:
                candles = await self.exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=limit)
            except Exception as first_error:
                # If that fails, try with an alternative format
                formatted_symbol = self._convert_symbol_format(symbol)
                
                if formatted_symbol != symbol:
                    candles = await self.exchange.fetch_ohlcv(formatted_symbol, timeframe=ccxt_tf, limit=limit)
                else:
                    # If no alternative format was found, re-raise the original error
                    raise first_error
                    
            self.ohlcv_data[symbol][ccxt_tf] = candles
            self.last_ohlcv_fetch_time[symbol][ccxt_tf] = datetime.now()
            
            await asyncio.sleep(self.rate_limit_sleep)  # Avoid rate limits
            
            logger.debug(f"Fetched {len(candles)} OHLCV candles for {symbol} ({ccxt_tf})")
            return candles
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} ({ccxt_tf}): {e}")
            raise
    
    def format_price(self, symbol: str, price: float) -> str:
        """
        Format price with appropriate precision for the symbol
        
        Args:
            symbol: Trading symbol
            price: Price to format
            
        Returns:
            Formatted price string
        """
        try:
            # Get market precision from CCXT if available
            if symbol in self.markets:
                precision_info = self.markets[symbol].get('precision', {})
                price_precision = precision_info.get('price')
                
                if price_precision is not None:
                    # Handle float precision (e.g., 0.00000001)
                    if isinstance(price_precision, float):
                        decimal_places = len(format(price_precision, '.10f').split('.')[1].rstrip('0'))
                        return f"{price:.{decimal_places}f}"
                    # Handle integer precision (number of decimal places)
                    else:
                        return f"{price:.{int(price_precision)}f}"
                        
            # Fallbacks based on price value if no precision info
            if abs(price) > 0 and abs(price) < 0.001:  # Very small prices
                return f"{price:.8f}"
            return f"{price:.2f}"  # Default format
            
        except Exception as e:
            logger.error(f"Error formatting price for {symbol} ({price}): {e}. Defaulting to .2f")
            return f"{price:.2f}"

    @staticmethod
    async def fetch_prices_for_symbols(symbols: List[str], exchange_id: str = 'coinbase') -> Dict[str, float]:
        """
        Static helper method to asynchronously fetch prices for multiple symbols
        
        Args:
            symbols: List of trading symbols
            exchange_id: CCXT exchange ID to use
            
        Returns:
            Dictionary mapping symbols to their current prices
        """
        fetcher = AsyncCCXTFetcher(exchange_id=exchange_id)
        try:
            await fetcher.initialize()
            
            # Create tasks for all symbol price fetches
            tasks = [fetcher.fetch_current_price(symbol) for symbol in symbols]
            prices = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Create result dict, handling any exceptions
            result = {}
            for symbol, price in zip(symbols, prices):
                if isinstance(price, Exception):
                    logger.error(f"Error fetching price for {symbol}: {price}")
                    result[symbol] = None
                else:
                    result[symbol] = price
                    
            return result
        finally:
            await fetcher.close() 