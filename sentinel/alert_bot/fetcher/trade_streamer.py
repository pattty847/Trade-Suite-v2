#!/usr/bin/env python3
import asyncio
import logging
from typing import Dict, List, Any, Callable, Set, Optional
from datetime import datetime, timedelta
from collections import deque
import ccxt.pro

logger = logging.getLogger(__name__)

class TradeData:
    """Represents a single trade"""
    def __init__(self, timestamp: datetime, price: float, volume: float, side: str):
        self.timestamp = timestamp
        self.price = price
        self.volume = volume
        self.side = side  # 'buy' or 'sell'
        self.delta = volume if side == 'buy' else -volume
    
    def __repr__(self):
        return f"Trade({self.side}, {self.price}, {self.volume}, {self.timestamp})"

class CVDCalculator:
    """Calculates Cumulative Volume Delta from trade data"""
    
    def __init__(self, lookback_minutes: int = 60):
        self.lookback_minutes = lookback_minutes
        self.trades: deque = deque()  # Store TradeData objects
        self.cvd_value = 0.0
        self.last_update = datetime.now()
    
    def add_trade(self, trade: TradeData):
        """Add a new trade and update CVD"""
        self.trades.append(trade)
        self.cvd_value += trade.delta
        self.last_update = trade.timestamp
        
        # Clean old trades outside lookback window
        cutoff_time = trade.timestamp - timedelta(minutes=self.lookback_minutes)
        while self.trades and self.trades[0].timestamp < cutoff_time:
            old_trade = self.trades.popleft()
            self.cvd_value -= old_trade.delta
    
    def get_cvd(self) -> float:
        """Get current CVD value"""
        return self.cvd_value
    
    def get_cvd_change(self, minutes: int) -> Optional[float]:
        """Get CVD change over specified minutes"""
        if not self.trades:
            return None
            
        cutoff_time = self.last_update - timedelta(minutes=minutes)
        
        # Find first trade within the window
        cvd_at_start = 0.0
        for trade in self.trades:
            if trade.timestamp >= cutoff_time:
                break
            cvd_at_start += trade.delta
        
        return self.cvd_value - cvd_at_start
    
    def get_buy_sell_ratio(self, minutes: int = None) -> Dict[str, float]:
        """Get buy/sell volume ratio over specified period"""
        if minutes:
            cutoff_time = self.last_update - timedelta(minutes=minutes)
            relevant_trades = [t for t in self.trades if t.timestamp >= cutoff_time]
        else:
            relevant_trades = list(self.trades)
        
        buy_volume = sum(t.volume for t in relevant_trades if t.side == 'buy')
        sell_volume = sum(t.volume for t in relevant_trades if t.side == 'sell')
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return {'buy_ratio': 0.5, 'sell_ratio': 0.5, 'buy_volume': 0, 'sell_volume': 0}
        
        return {
            'buy_ratio': buy_volume / total_volume,
            'sell_ratio': sell_volume / total_volume,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume
        }

class TradeStreamer:
    """
    Streams individual trades for CVD calculation
    """
    
    def __init__(self, exchange_id: str = 'coinbase', lookback_minutes: int = 60):
        """
        Initialize trade streamer
        
        Args:
            exchange_id: CCXT exchange ID to use
            lookback_minutes: How many minutes of trade history to maintain for CVD
        """
        self.exchange_id = exchange_id
        self.lookback_minutes = lookback_minutes
        try:
            exchange_class = getattr(ccxt.pro, self.exchange_id)
            self.exchange = exchange_class()
        except AttributeError:
            logger.error(f"Exchange {self.exchange_id} not found in ccxt.pro. Ensure it's a valid ccxt.pro exchange ID.")
            raise ValueError(f"Unsupported exchange for ccxt.pro: {self.exchange_id}")

        # Track requested symbols
        self.tracked_symbols: Set[str] = set()
        
        # CVD calculators for each symbol
        self.cvd_calculators: Dict[str, CVDCalculator] = {}
        
        # Callbacks for CVD updates
        self.callbacks: List[Callable[[str, float, Dict[str, Any]], None]] = []
        
        # Flag to control the streaming loop
        self.is_running = False
        self.fetch_tasks = []
    
    async def initialize(self):
        """Initialize the fetcher"""
        pass
    
    async def close(self):
        """Clean up resources"""
        self.is_running = False
        # Cancel any running fetch tasks
        for task in self.fetch_tasks:
            if not task.done():
                task.cancel()
        
        # Ensure all tasks are awaited to allow cleanup
        if self.fetch_tasks:
            await asyncio.gather(*self.fetch_tasks, return_exceptions=True)
        
        if hasattr(self.exchange, 'close'):
            await self.exchange.close()
        logger.info("TradeStreamer closed.")
    
    def register_callback(self, callback: Callable[[str, float, Dict[str, Any]], None]):
        """
        Register a callback to be called when CVD data is updated
        
        Args:
            callback: Function taking (symbol, cvd_value, extra_data) arguments
        """
        self.callbacks.append(callback)
    
    def track_symbol(self, symbol: str):
        """
        Start tracking trades for a symbol
        
        Args:
            symbol: Trading symbol
        """
        self.tracked_symbols.add(symbol)
        if symbol not in self.cvd_calculators:
            self.cvd_calculators[symbol] = CVDCalculator(self.lookback_minutes)
        logger.debug(f"Now tracking trades for {symbol}")
    
    def untrack_symbol(self, symbol: str):
        """Remove a symbol from tracking"""
        if symbol in self.tracked_symbols:
            self.tracked_symbols.remove(symbol)
            logger.debug(f"Stopped tracking trades for {symbol}")
    
    async def fetch_trades_for_symbol(self, symbol: str):
        """
        Continuously fetch trades for a symbol using ccxt.pro
        
        Args:
            symbol: Trading symbol
        """
        logger.info(f"Starting ccxt.pro trade watch loop for {symbol}")
        
        while self.is_running and symbol in self.tracked_symbols:
            try:
                # ccxt.pro watch_trades fetches trades since the last call
                trades_raw = await self.exchange.watch_trades(symbol)
                
                if trades_raw:
                    cvd_calc = self.cvd_calculators[symbol]
                    new_trades_count = 0
                    
                    # Sort trades by timestamp just in case, though watch_trades should provide them in order
                    # and usually only new ones.
                    sorted_trades_raw = sorted(trades_raw, key=lambda t: t['timestamp'])

                    for trade_raw in sorted_trades_raw:
                        trade = self.parse_trade(trade_raw)
                        if trade:
                            # The CVD calculator handles its own time window.
                            # We just add all new trades received.
                            cvd_calc.add_trade(trade)
                            new_trades_count += 1
                    
                    if new_trades_count > 0:
                        cvd_value = cvd_calc.get_cvd()
                        extra_data = {
                            'cvd_change_5m': cvd_calc.get_cvd_change(5),
                            'cvd_change_15m': cvd_calc.get_cvd_change(15),
                            'cvd_change_30m': cvd_calc.get_cvd_change(30),
                            'buy_sell_ratio_5m': cvd_calc.get_buy_sell_ratio(5),
                            'buy_sell_ratio_15m': cvd_calc.get_buy_sell_ratio(15),
                            'trades_count': len(cvd_calc.trades),
                            'last_update': cvd_calc.last_update
                        }
                        
                        for callback in self.callbacks:
                            try:
                                # Ensure callback is awaitable if it does I/O
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(symbol, cvd_value, extra_data)
                                else:
                                    callback(symbol, cvd_value, extra_data)
                            except Exception as e:
                                logger.error(f"Error in CVD callback for {symbol}: {e}")
                        
                        logger.debug(f"Updated CVD for {symbol}: {cvd_value:.2f} ({new_trades_count} new trades)")
            
            except ccxt.pro.NetworkError as e:
                logger.error(f"ccxt.pro NetworkError for {symbol}: {e}. Retrying connection...")
                await asyncio.sleep(5) # Wait before retrying
            except ccxt.pro.ExchangeError as e:
                logger.error(f"ccxt.pro ExchangeError for {symbol}: {e}. May need to handle specific errors.")
                await asyncio.sleep(5) # Wait before retrying or specific handling
            except asyncio.CancelledError:
                logger.info(f"Trade watch for {symbol} was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error watching trades for {symbol}: {e}", exc_info=True)
                # Implement a backoff strategy for repeated errors
                await asyncio.sleep(self.exchange.rateLimit / 1000 if hasattr(self.exchange, 'rateLimit') else 1) # Basic backoff
                            
    async def fetch_recent_trades(self, symbol: str, since: Optional[datetime] = None, limit: int = 100) -> List[dict]:
        """
        Fetch recent trades from exchange.
        This method is now primarily for fetching initial history if needed, 
        as live trades come from watch_trades.
        
        Args:
            symbol: Trading symbol
            since: Fetch trades since this timestamp (datetime object)
            limit: Maximum number of trades to fetch
            
        Returns:
            List of raw trade dictionaries
        """
        if not hasattr(self.exchange, 'fetch_trades'):
            logger.warning(f"Exchange {self.exchange_id} does not support fetch_trades. Cannot fetch initial history.")
            return []
        try:
            since_ms = int(since.timestamp() * 1000) if since else None
            
            # Note: ccxt.pro exchange instances can also call regular ccxt methods
            trades = await self.exchange.fetch_trades(symbol, since=since_ms, limit=limit)
            
            # No explicit rate_limit_sleep needed here usually, ccxt handles it.
            # If using a non-pro exchange instance (fallback, not recommended for streaming), 
            # then manual rate limiting might be needed.
            
            return trades
            
        except Exception as e:
            logger.error(f"Error fetching initial trades for {symbol}: {e}")
            return []
    
    def parse_trade(self, trade_raw: dict) -> Optional[TradeData]:
        """
        Parse raw trade data from exchange into TradeData object
        
        Args:
            trade_raw: Raw trade dictionary from CCXT
            
        Returns:
            TradeData object or None if parsing fails
        """
        try:
            # CCXT trade format: 
            # {
            #     'id': '12345',
            #     'timestamp': 1609459200000,
            #     'datetime': '2021-01-01T00:00:00.000Z',
            #     'symbol': 'BTC/USD',
            #     'side': 'buy',  # or 'sell'
            #     'amount': 0.1,  # volume
            #     'price': 50000,
            #     'cost': 5000,   # price * amount
            #     'fee': {...}
            # }
            
            timestamp = datetime.fromtimestamp(trade_raw['timestamp'] / 1000)
            price = float(trade_raw['price'])
            volume = float(trade_raw['amount'])
            side = trade_raw['side']  # 'buy' or 'sell'
            
            return TradeData(timestamp, price, volume, side)
            
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing trade data: {e}. Trade: {trade_raw}")
            return None
    
    def get_cvd_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current CVD data for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with CVD data or None if not available
        """
        if symbol not in self.cvd_calculators:
            return None
            
        cvd_calc = self.cvd_calculators[symbol]
        return {
            'cvd': cvd_calc.get_cvd(),
            'cvd_change_5m': cvd_calc.get_cvd_change(5),
            'cvd_change_15m': cvd_calc.get_cvd_change(15),
            'cvd_change_30m': cvd_calc.get_cvd_change(30),
            'buy_sell_ratio_5m': cvd_calc.get_buy_sell_ratio(5),
            'buy_sell_ratio_15m': cvd_calc.get_buy_sell_ratio(15),
            'trades_count': len(cvd_calc.trades),
            'last_update': cvd_calc.last_update
        }
    
    async def start(self):
        """Start streaming trades for all tracked symbols"""
        if not self.exchange.has['watchTrades']:
            logger.error(f"Exchange {self.exchange_id} does not support watchTrades. TradeStreamer cannot start.")
            self.is_running = False
            return

        self.is_running = True
        self.fetch_tasks = [] # Clear any previous tasks
        
        # Start a fetch task for each symbol
        for symbol in list(self.tracked_symbols): # Iterate over a copy
            if symbol not in self.cvd_calculators: 
                 self.cvd_calculators[symbol] = CVDCalculator(self.lookback_minutes)
            
            cvd_calc = self.cvd_calculators[symbol] # Get the calculator

            # Pre-fill CVD calculator with some historical data
            initial_since = datetime.now() - timedelta(minutes=self.lookback_minutes)
            logger.info(f"Fetching initial trades for {symbol} for the last {self.lookback_minutes} minutes.")
            # Using limit=None to try and get all trades in the lookback, ccxt might cap this.
            # Some exchanges might require a smaller limit or paginated requests for very long lookbacks.
            # For a typical lookback of 60 mins, 1000-5000 trades might be a reasonable upper estimate depending on liquidity.
            # Adjust limit if necessary, or implement pagination if exchanges restrict heavily.
            initial_trades = await self.fetch_recent_trades(symbol, since=initial_since, limit=1000) 
            if initial_trades:
                # Sort by timestamp to process in order
                initial_trades_sorted = sorted(initial_trades, key=lambda t: t['timestamp'])
                for trade_raw in initial_trades_sorted:
                    trade = self.parse_trade(trade_raw)
                    if trade:
                        # Ensure not to add trades that might already be in from a previous (now defunct) run
                        # if trade.timestamp > cvd_calc.last_update (if cvd_calc.trades else True):
                        cvd_calc.add_trade(trade)
                logger.info(f"Pre-filled CVD for {symbol} with {len(initial_trades_sorted)} trades. Current CVD: {cvd_calc.get_cvd():.2f}, Last Trade: {cvd_calc.last_update}")
            else:
                logger.info(f"No initial trades found for {symbol} for pre-fill, or an error occurred.")


            task = asyncio.create_task(self.fetch_trades_for_symbol(symbol))
            self.fetch_tasks.append(task)
                
        if self.fetch_tasks:
            logger.info(f"Started trade streaming for {len(self.fetch_tasks)} symbols using ccxt.pro")
        else:
            logger.info("No symbols to stream trades for.")
    
    async def stop(self):
        """Stop streaming trades"""
        self.is_running = False
        await self.close()