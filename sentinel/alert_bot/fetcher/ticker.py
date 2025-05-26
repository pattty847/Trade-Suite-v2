#!/usr/bin/env python3
import asyncio
import logging
from typing import Dict, List, Any, Callable, Set, Optional
from datetime import datetime
import ccxt.pro

logger = logging.getLogger(__name__)

class TickerStreamer:
    """
    Streams ticker data for multiple symbols using ccxt.pro
    """
    
    def __init__(self, exchange_id: str = 'coinbase'):
        """
        Initialize ticker streamer
        
        Args:
            exchange_id: CCXT.pro exchange ID to use
        """
        self.exchange_id = exchange_id
        try:
            exchange_class = getattr(ccxt.pro, self.exchange_id)
            self.exchange = exchange_class()
        except AttributeError:
            logger.error(f"Exchange {self.exchange_id} not found in ccxt.pro. Ensure it's a valid ccxt.pro exchange ID.")
            raise ValueError(f"Unsupported exchange for ccxt.pro Ticker streaming: {self.exchange_id}")
        
        # Track requested symbols
        self.tracked_symbols: Set[str] = set()
        
        # Callbacks for new price data
        self.callbacks: List[Callable[[str, float], None]] = []
        
        # Cache of latest prices
        self.latest_prices: Dict[str, float] = {}
        
        # Flag to control the streaming loop
        self.is_running = False
        self.watch_tasks: Dict[str, asyncio.Task] = {}
        self.master_watch_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Initialize the streamer. (ccxt.pro usually connects on first watch call)"""
        pass
    
    async def close(self):
        """Clean up resources"""
        self.is_running = False

        # Cancel master task if it exists
        if self.master_watch_task and not self.master_watch_task.done():
            self.master_watch_task.cancel()
            try:
                await self.master_watch_task
            except asyncio.CancelledError:
                logger.info("Master ticker watch task cancelled.")
        self.master_watch_task = None

        # Cancel individual tasks if they exist
        tasks_to_await = []
        for symbol, task in list(self.watch_tasks.items()):
            if task and not task.done():
                task.cancel()
                tasks_to_await.append(task)
            if symbol in self.watch_tasks:
                 del self.watch_tasks[symbol]
        
        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)
            logger.info(f"Cancelled {len(tasks_to_await)} individual ticker watch tasks.")
        self.watch_tasks.clear()

        if hasattr(self.exchange, 'close'):
            try:
                await self.exchange.close()
                logger.info("ccxt.pro exchange connection closed for TickerStreamer.")
            except Exception as e:
                logger.error(f"Error closing ccxt.pro exchange connection in TickerStreamer: {e}")
        logger.info("TickerStreamer closed.")
    
    def register_callback(self, callback: Callable[[str, float], None]):
        """
        Register a callback to be called when new price data is available
        
        Args:
            callback: Function taking (symbol, price) arguments
        """
        self.callbacks.append(callback)
    
    def _process_ticker_data(self, symbol: str, ticker_data: Dict[str, Any]):
        """Extracts price, updates cache, and calls callbacks."""
        # Standard ccxt ticker structure has 'last', 'close', 'bid', 'ask'
        # Prefer 'last' if available, then 'close'. Adjust if your exchange uses others primarily.
        price = ticker_data.get('last')
        if price is None:
            price = ticker_data.get('close')
        
        if price is not None:
            self.latest_prices[symbol] = float(price)
            # timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # ccxt ticker has 'timestamp' and 'datetime'
            iso_datetime = ticker_data.get('datetime', datetime.now().isoformat())
            logger.debug(f"[{iso_datetime}] Ticker {symbol}: {price}")
            for cb in self.callbacks:
                try:
                    # Ensure callback is awaitable if it does I/O
                    if asyncio.iscoroutinefunction(cb):
                        # Create a task for the callback to avoid blocking the streamer loop
                        asyncio.create_task(cb(symbol, float(price)))
                    else:
                        cb(symbol, float(price))
                except Exception as e:
                    logger.error(f"Error in Ticker callback for {symbol}: {e}", exc_info=True)
        else:
            logger.warning(f"Could not extract price (last/close) from ticker data for {symbol}: {ticker_data}")

    async def _watch_individual_ticker(self, symbol: str):
        """Watches a single symbol using watchTicker."""
        logger.info(f"Starting watchTicker for {symbol}")
        while self.is_running and symbol in self.tracked_symbols:
            if symbol not in self.watch_tasks or self.watch_tasks[symbol].done(): # Task might have been cancelled
                break
            try:
                ticker = await self.exchange.watchTicker(symbol)
                self._process_ticker_data(symbol, ticker)
            except ccxt.pro.NetworkError as e:
                logger.error(f"watchTicker NetworkError for {symbol}: {e}. Retrying...")
                if not self.is_running: break
                await asyncio.sleep(5)
            except ccxt.pro.ExchangeError as e:
                logger.error(f"watchTicker ExchangeError for {symbol}: {e}. Retrying...")
                if not self.is_running: break
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                logger.info(f"watchTicker for {symbol} cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in watchTicker for {symbol}: {e}", exc_info=True)
                if not self.is_running: break
                await asyncio.sleep(1) # Brief pause before retrying
        logger.info(f"Stopping watchTicker for {symbol}")
        if symbol in self.watch_tasks: # Clean up task entry if it still exists
            del self.watch_tasks[symbol]

    async def _watch_all_tickers(self):
        """Watches all tracked symbols using watchTickers."""
        logger.info(f"Starting watchTickers for symbols: {list(self.tracked_symbols)}")
        symbols_to_watch = list(self.tracked_symbols) # Initial list

        while self.is_running and symbols_to_watch:
            if self.master_watch_task is None or self.master_watch_task.done(): # Task might have been cancelled
                break
            try:
                # Re-check tracked_symbols in case of changes during an error/retry sleep
                current_tracked_symbols_list = list(self.tracked_symbols)
                if not current_tracked_symbols_list: # All symbols untracked
                    logger.info("No symbols left to watch with watchTickers.")
                    break
                
                if set(current_tracked_symbols_list) != set(symbols_to_watch):
                    logger.info(f"Symbol list changed for watchTickers. Old: {symbols_to_watch}, New: {current_tracked_symbols_list}. Restarting watchTickers.")
                    # This will break the loop and _start_streaming_logic will be called by track/untrack to restart with new symbols
                    # A more direct restart could also be done here, but requires careful state management.
                    # For now, rely on track/untrack to manage the restart of master_watch_task.
                    # To make it more direct, we would cancel and nullify self.master_watch_task here,
                    # then call self._start_streaming_logic() or just restart the loop with new symbols.
                    # However, ccxt.pro's watchTickers might handle dynamic symbols internally if params are updated.
                    # For now, we assume a restart is needed if the symbol list changes significantly.
                    # Let's try to pass the new list directly if the API supports it.
                    # Some ccxt.pro exchanges might allow passing symbols=[] to unsubscribe all, 
                    # then resubscribe. Others require a fresh call. The simplest is a fresh call.
                    symbols_to_watch = current_tracked_symbols_list # Update the list for the next call
                    # No need to break if we are just updating the list for the next call, unless the API needs a full reset.
                    # Let's assume watchTickers can be called again with the new list.

                tickers_data = await self.exchange.watchTickers(symbols_to_watch)
                for symbol, ticker_data in tickers_data.items():
                    if symbol in self.tracked_symbols: # Process only if still tracked
                        self._process_ticker_data(symbol, ticker_data)
            
            except ccxt.pro.NetworkError as e:
                logger.error(f"watchTickers NetworkError: {e}. Retrying...")
                if not self.is_running: break
                await asyncio.sleep(5)
            except ccxt.pro.ExchangeError as e:
                logger.error(f"watchTickers ExchangeError: {e}. Retrying...")
                if not self.is_running: break
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                logger.info("watchTickers task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in watchTickers: {e}", exc_info=True)
                if not self.is_running: break
                await asyncio.sleep(1) # Brief pause before retrying
        logger.info("Stopping watchTickers loop.")
        self.master_watch_task = None # Ensure it's cleared

    def track_symbol(self, symbol: str):
        """
        Start tracking a symbol. Restarts watcher if needed.
        """
        if symbol in self.tracked_symbols:
            logger.debug(f"Symbol {symbol} is already tracked for tickers.")
            return

        self.tracked_symbols.add(symbol)
        self.latest_prices[symbol] = self.latest_prices.get(symbol, None) # Ensure key exists
        logger.info(f"Now tracking ticker for {symbol}. Total: {len(self.tracked_symbols)}")

        if self.is_running:
            self._stop_and_clear_watch_tasks() # Stop existing tasks
            self._start_streaming_logic()      # Restart with new symbol list
    
    def untrack_symbol(self, symbol: str):
        """Remove a symbol from tracking. Restarts watcher if needed."""
        if symbol in self.tracked_symbols:
            self.tracked_symbols.remove(symbol)
            if symbol in self.latest_prices: del self.latest_prices[symbol]
            logger.info(f"Stopped tracking ticker for {symbol}. Remaining: {len(self.tracked_symbols)}")
            
            if self.is_running:
                self._stop_and_clear_watch_tasks() # Stop existing tasks
                if self.tracked_symbols: # Only restart if there are symbols left
                    self._start_streaming_logic() 
                else:
                    logger.info("No symbols left to track for tickers. Watcher stopped.")
        else:
            logger.debug(f"Symbol {symbol} was not tracked for tickers.")

    def _stop_and_clear_watch_tasks(self):
        """Internal helper to stop and clear all current watch tasks."""
        logger.debug("Stopping and clearing existing ticker watch tasks before restart.")
        # Cancel master task
        if self.master_watch_task and not self.master_watch_task.done():
            self.master_watch_task.cancel()
            # Don't await here to avoid deadlock if called from within the task itself (should not happen with current logic)
        self.master_watch_task = None

        # Cancel individual tasks
        for task in list(self.watch_tasks.values()):
            if task and not task.done():
                task.cancel()
        self.watch_tasks.clear()
        # Give a moment for tasks to be cancelled if needed, though cancellation is cooperative
        # await asyncio.sleep(0.01) # Usually not needed for cancellation itself

    def _start_streaming_logic(self):
        """Internal method to decide and start the appropriate watch strategy."""
        if not self.is_running or not self.tracked_symbols:
            logger.debug("Not starting streaming logic: not running or no symbols.")
            return

        # Prefer watchTickers if available and symbols are being tracked
        if self.exchange.has.get('watchTickers') and self.tracked_symbols:
            logger.info(f"Using watchTickers for symbols: {list(self.tracked_symbols)}")
            self.master_watch_task = asyncio.create_task(self._watch_all_tickers())
        elif self.exchange.has.get('watchTicker') and self.tracked_symbols:
            logger.info("Using individual watchTicker for each symbol.")
            for symbol in list(self.tracked_symbols): # Iterate over a copy
                if symbol not in self.watch_tasks or self.watch_tasks[symbol].done():
                    self.watch_tasks[symbol] = asyncio.create_task(self._watch_individual_ticker(symbol))
        else:
            if not self.tracked_symbols:
                logger.info("No symbols to track for TickerStreamer.")
            else:
                logger.error(
                    f"Exchange {self.exchange_id} supports neither watchTickers nor watchTicker. TickerStreamer cannot stream."
                )
                self.is_running = False # Cannot run
    
    def get_latest_price(self, symbol: str) -> Optional[float]: # Return Optional[float]
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
        if not self.tracked_symbols:
            logger.info("TickerStreamer: No symbols to track. Call track_symbol() first.")
            # self.is_running = False # Or keep it true, and let it start once symbols are added?
            # For now, let's allow start, and it will pick up symbols when added if running.
            # Or, require symbols before start for clarity.
            # Let's make it explicit: only start if symbols exist.
            # self.is_running = False
            # return # Exit if no symbols

        self.is_running = True
        logger.info(f"TickerStreamer starting. Currently tracked symbols: {len(self.tracked_symbols)}")
        self._start_streaming_logic()
    
    async def stop(self):
        """Stop streaming data. This now calls the more comprehensive close()"""
        logger.info("TickerStreamer stop() called. Initiating full closure.")
        await self.close() # close() already handles stopping tasks and exchange connection 