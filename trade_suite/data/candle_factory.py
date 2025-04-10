from collections import deque
import time
import pandas as pd
import asyncio
import logging
from trade_suite.data.data_source import Data
from typing import Dict, List

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import timeframe_to_seconds
from trade_suite.analysis.chart_processor import ChartProcessor


class CandleFactory:
    def __init__(
        self,
        exchange,
        tab,
        emitter: SignalEmitter,
        task_manager: TaskManager,
        data: Data,
        exchange_settings,
        timeframe_str,
    ) -> None:
        self.exchange = exchange
        self.tab = tab
        self.emitter = emitter
        self.task_manager = task_manager
        self.data = data
        self.exchange_settings = exchange_settings
        self.timeframe_str = timeframe_str
        
        # Get default symbol to initialize the processor
        self.symbol = exchange_settings.get("last_symbol", "BTC/USD")
        
        # Get market info for price precision, if available
        price_precision = 0.00001  # Default value
        try:
            market_info = self.data.exchange_list[self.exchange].market(self.symbol)
            if market_info and "precision" in market_info:
                price_precision = market_info["precision"].get("price", 0.00001)
        except Exception as e:
            logging.warning(f"Could not get price precision for {self.symbol}: {e}")
            
        # Initialize the chart processor
        self.processor = ChartProcessor(
            exchange=self.exchange,
            symbol=self.symbol,
            timeframe=timeframe_str,
            price_precision=price_precision
        )
        
        # Queue for batching trades
        self._trade_queue = deque()
        self.max_trades_per_candle_update = 5
        self.last_update_time = None

        self._register_event_listeners()

    def _register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self._on_new_trade,
            Signals.NEW_CANDLES: self._on_new_candles,
            Signals.TIMEFRAME_CHANGED: self._on_timeframe_changed,
            Signals.SYMBOL_CHANGED: self._on_symbol_changed,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def _on_new_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab:
            # Use the processor to process the candles
            processed_candles = self.processor.process_candles(candles)
            
            # No need to emit; this is a response to receiving candles
    
    def _on_timeframe_changed(self, exchange, tab, new_timeframe):
        if tab == self.tab:
            # Update the timeframe in the processor
            self.timeframe_str = new_timeframe
            self.processor.set_timeframe(new_timeframe)

    def _on_symbol_changed(self, exchange, tab, new_symbol):
        if tab == self.tab and exchange == self.exchange:
            self.symbol = new_symbol
            
            # Get price precision for the new symbol
            price_precision = None
            try:
                market_info = self.data.exchange_list[self.exchange].market(new_symbol)
                if market_info and "precision" in market_info:
                    price_precision = market_info["precision"].get("price")
            except Exception as e:
                logging.warning(f"Could not get price precision for {new_symbol}: {e}")
            
            # Update the processor with the new symbol
            self.processor.set_symbol(new_symbol, price_precision)

    def _on_new_trade(self, tab, exchange, trade_data):
        if tab == self.tab:
            # Add to queue
            self._trade_queue.append(trade_data)
            current_time = time.time()

            # Check if we should process the queued trades
            if (len(self._trade_queue) >= self.max_trades_per_candle_update or
                (self.last_update_time is not None and 
                 current_time - self.last_update_time >= self.processor.timeframe_seconds)):
                self._process_trade_batch()

    def _process_trade_batch(self):
        if not self._trade_queue:
            return
            
        # Get trades and clear queue
        batch_trades = list(self._trade_queue)
        self._trade_queue.clear()
        
        # Process the batch using the processor
        updated_candles = self.processor.process_trade_batch(batch_trades)
        
        # If candles were updated, emit the update
        if updated_candles is not None:
            self.emitter.emit(
                Signals.UPDATED_CANDLES,
                tab=self.tab,
                exchange=self.exchange,
                candles=updated_candles,
            )
            
        self.last_update_time = time.time()

    def try_resample(self, new_timeframe: str, active_exchange):
        # Use the processor to attempt resampling
        success, resampled_data = self.processor.try_resample(new_timeframe)
        
        if success and resampled_data is not None:
            # Emit an event to update the candles
            self.emitter.emit(
                Signals.UPDATED_CANDLES,
                tab=self.tab,
                exchange=active_exchange,
                candles=resampled_data,
            )
            
            # Update the timeframe string
            self.timeframe_str = new_timeframe
            
            return True
        else:
            # If resampling was not successful, just update the timeframe
            self.timeframe_str = new_timeframe
            return False

    def set_trade_batch(self, sender, app_data, user_data):
        self.max_trades_per_candle_update = app_data