#!/usr/bin/env python3
import ccxt
import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CCXTFetcher:
    """
    Data fetcher using CCXT library for exchange data
    """
    
    def __init__(self, 
                 exchange_id: str = 'coinbase',
                 rate_limit_sleep: float = 1.0):
        """
        Initialize CCXT fetcher
        
        Args:
            exchange_id: CCXT exchange ID to use
            rate_limit_sleep: Sleep time between API requests to avoid rate limits
        """
        self.exchange_id = exchange_id
        self.rate_limit_sleep = rate_limit_sleep
        self.exchange = getattr(ccxt, exchange_id)()
        
        # Cache for market info
        self.markets = {}
        self.last_ticker_prices: Dict[str, Dict[str, Any]] = {}
        self.ohlcv_data: Dict[str, Dict[str, List[list]]] = {}
        self.last_ohlcv_fetch_time: Dict[str, Dict[str, datetime]] = {}
        
        # Try to load exchange markets
        try:
            self.exchange.load_markets()
            self.markets = self.exchange.markets
            logger.info(f"Loaded {len(self.markets)} markets from {exchange_id}")
        except Exception as e:
            logger.error(f"Error loading markets from {exchange_id}: {e}")
    
    def get_supported_symbols(self) -> List[str]:
        """Get list of supported trading symbols"""
        return list(self.markets.keys())
    
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data for symbol
        
        Args:
            symbol: Trading symbol (e.g., BTC/USD)
            
        Returns:
            Ticker data dictionary with at least 'last' price
            
        Raises:
            Exception if fetch fails
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            self.last_ticker_prices[symbol] = ticker
            time.sleep(self.rate_limit_sleep)  # Avoid rate limits
            logger.debug(f"Fetched ticker for {symbol}: {ticker['last']}")
            return ticker
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            raise
    
    def fetch_current_price(self, symbol: str) -> float:
        """
        Fetch just the current price for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price
            
        Raises:
            Exception if fetch fails
        """
        ticker = self.fetch_ticker(symbol)
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
    
    def fetch_ohlcv(self, symbol: str, timeframe_minutes: int, limit: int = 50) -> List[list]:
        """
        Fetch OHLCV (candle) data for a symbol
        
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
                
            candles = self.exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=limit)
            self.ohlcv_data[symbol][ccxt_tf] = candles
            self.last_ohlcv_fetch_time[symbol][ccxt_tf] = datetime.now()
            
            time.sleep(self.rate_limit_sleep)  # Avoid rate limits
            
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