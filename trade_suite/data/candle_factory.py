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
        self.timeframe_seconds = timeframe_to_seconds(self.timeframe_str)
        self.last_candle_timestamp = None

        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        self._trade_queue = deque()
        self.max_trades_per_candle_update = 5

        self._register_event_listeners()

    def _register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self._on_new_trade,
            Signals.NEW_CANDLES: self._on_new_candles,
            Signals.TIMEFRAME_CHANGED: self._on_new_timeframe,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def _on_new_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab:
            self.ohlcv = candles
    
    def _on_new_timeframe(self, tab, exchange, new_timeframe):
        if tab == self.tab:
            self.timeframe_str = new_timeframe
            self.timeframe_str = timeframe_to_seconds(timeframe_str=new_timeframe)

    def _on_new_trade(self, tab, exchange, trade_data):
        if tab == self.tab:
            self._trade_queue.append(trade_data)
            current_time = time.time()

            # Check if time or count threshold is reached
            if len(self._trade_queue) >= self.max_trades_per_candle_update or (
                self.last_candle_timestamp is not None
                and current_time - self.last_candle_timestamp >= self.timeframe_seconds
            ):
                self._build_candle_from_batch(tab, exchange)

    def _build_candle_from_batch(self, tab, exchange):
        if self._trade_queue:
            # Assuming trade_data has 'timestamp', 'price', 'amount'
            batch_trades = list(self._trade_queue)
            self._trade_queue.clear()

            # Process the batch to create a new candle
            # Logic to compute OHLC and volume for the batch
            # Update self.ohlcv with the new candle
            for trade in batch_trades:
                self._build_candles(tab, exchange, trade)

            # Emit the updated candles
            self.emitter.emit(
                Signals.UPDATED_CANDLES,
                tab=self.tab,
                exchange=exchange,
                candles=self.ohlcv,
            )

    def _build_candles(self, tab, exchange, trade_data):
        if tab == self.tab:
            timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
            price = trade_data["price"]
            volume = trade_data["amount"]

            # Adjust the timestamp to the nearest minute less than or equal to the timestamp
            adjusted_timestamp = timestamp - (timestamp % self.timeframe_seconds)

            if self.last_candle_timestamp is None:
                self.last_candle_timestamp = adjusted_timestamp

            if (
                adjusted_timestamp
                >= self.last_candle_timestamp + self.timeframe_seconds
            ):
                # Start a new candle
                new_candle = {
                    "dates": self.last_candle_timestamp + self.timeframe_seconds,
                    "opens": price,
                    "highs": price,
                    "lows": price,
                    "closes": price,
                    "volumes": volume,
                }
                # Convert the new candle dictionary to a DataFrame before concatenating
                new_candle_df = pd.DataFrame([new_candle])
                self.ohlcv = pd.concat([self.ohlcv, new_candle_df], ignore_index=True)
                self.last_candle_timestamp += self.timeframe_seconds
            elif not self.ohlcv.empty:  # Check if the dataframe is not empty before accessing
                # Update the current candle
                self.ohlcv.at[self.ohlcv.index[-1], "highs"] = max(
                    self.ohlcv.at[self.ohlcv.index[-1], "highs"], price
                )
                self.ohlcv.at[self.ohlcv.index[-1], "lows"] = min(
                    self.ohlcv.at[self.ohlcv.index[-1], "lows"], price
                )
                self.ohlcv.at[self.ohlcv.index[-1], "closes"] = price
                self.ohlcv.at[self.ohlcv.index[-1], "volumes"] += volume
            else:
                # Handle the case where ohlcv is empty by creating a new candle
                new_candle = {
                    "dates": adjusted_timestamp,
                    "opens": price,
                    "highs": price,
                    "lows": price,
                    "closes": price,
                    "volumes": volume,
                }
                # Convert the new candle dictionary to a DataFrame
                new_candle_df = pd.DataFrame([new_candle])
                self.ohlcv = new_candle_df
                self.last_candle_timestamp = adjusted_timestamp


    def try_resample(self, new_timeframe: str, active_exchange):
        new_timeframe_in_seconds = timeframe_to_seconds(new_timeframe)
        
        # If the new timeframe is larger than the old one, we can aggregate the dataset ourselves
        if new_timeframe_in_seconds > self.timeframe_seconds:
            ohlcv = self.data.agg.resample_data(self.ohlcv, new_timeframe)
            
            # Emit an event to update the candles
            self.emitter.emit(
                Signals.UPDATED_CANDLES,
                tab=self.tab,
                exchange=active_exchange,
                candles=ohlcv,
            )
            
            # Update the ohlcv and timeframe_seconds attributes
            self.ohlcv = ohlcv
            self.timeframe_seconds = new_timeframe_in_seconds
            
            # Return True to indicate successful resampling
            return True
        else:
            # If the new timeframe is smaller or equal to the old one, we can't resample
            # Update the timeframe_seconds attribute
            self.timeframe_seconds = new_timeframe_in_seconds
            
            # Return False to indicate unsuccessful resampling
            return False


    def set_trade_batch(self, sender, app_data, user_data):
        self.max_trades_per_candle_update = app_data