from collections import deque
import time
import pandas as pd
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime
import numpy as np

from ..signals import SignalEmitter, Signals
from trade_suite.gui.utils import timeframe_to_seconds

if TYPE_CHECKING:
    from .data_source import Data
    from ..task_manager import TaskManager


class CandleFactory:
    def __init__(
        self,
        exchange: str,
        symbol: str,
        timeframe_str: str,
        emitter: "SignalEmitter",
        task_manager: "TaskManager",
        data: "Data",
        initial_candles: Optional[pd.DataFrame] = None,
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe_str = timeframe_str
        self.emitter = emitter
        self.task_manager = task_manager
        self.data = data

        # Set timeframe in minutes and seconds for calculations
        self.timeframe_in_seconds = self.data.exchange_list[self.exchange].parse_timeframe(timeframe_str)
        
        # Get market info for price precision, if available
        price_precision = 0.00001  # Default value
        try:
            market_info = self.data.exchange_list[self.exchange].market(self.symbol)
            if market_info and "precision" in market_info:
                price_precision = market_info["precision"].get("price", 0.00001)
        except Exception as e:
            logging.warning(f"Could not get price precision for {self.symbol}: {e}")
            
        # Initialize empty OHLCV dataframe
        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        self.last_candle_timestamp = None
        self.price_precision = price_precision # Store precision if needed later
        # Convert precision to number of decimal digits for rounding
        if 0 < price_precision < 1:
            self.precision_digits = int(round(-np.log10(price_precision)))
        else:
            self.precision_digits = 0

        # Queue for batching trades
        self._trade_queue = deque()
        self.max_trades_per_candle_update = 5
        # Time-based flush interval (seconds) to send updates to UI even when trade volume is low
        # Helps maintain high refresh rates (e.g., 144 Hz means frame every ~0.007 s, but we only need ~4–8 fps for charts)
        self.flush_interval = 0.25  # seconds
        self.last_update_time = time.time()

        self._register_event_listeners()

    def _register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self._on_new_trade,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def _on_new_trade(self, exchange: str, trade_data: dict):
        """Handles incoming trade data, queues it, and triggers batch processing."""
        trade_symbol = trade_data.get('symbol')
        # Filter based on the factory's configured exchange and symbol
        if exchange == self.exchange and trade_symbol == self.symbol:
            # Log trade receipt for this factory instance
            logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) received trade: {trade_symbol} @ {trade_data.get('price')} - Time: {datetime.fromtimestamp(trade_data.get('timestamp')/1000).strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Pre-round price once and enqueue trade for later batch processing
            processed_trade = {
                **trade_data,
                "price": round(trade_data["price"], self.precision_digits),
            }
            self._trade_queue.append(processed_trade)
            current_time = time.time()

            # Check if we should process the queued trades
            # We flush when either we have accumulated enough trades OR the flush interval has elapsed.
            if (
                len(self._trade_queue) >= self.max_trades_per_candle_update
                or (current_time - self.last_update_time) >= self.flush_interval
            ):
                logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) processing trade batch - queue size: {len(self._trade_queue)}")
                self._process_trade_batch()
        # else:
            # Log if the trade wasn't for this factory instance (optional, can be noisy)
            # logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) ignored trade for {exchange}/{trade_symbol}")
            

    def _process_trade_batch(self):
        """Processes queued trades and emits updated candle data."""
        if not self._trade_queue:
            # logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) tried to process empty trade queue") # Can be noisy
            return
            
        # Get trades and clear queue
        batch_trades = list(self._trade_queue)
        self._trade_queue.clear()
        
        logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) processing {len(batch_trades)} trades")
        
        # --- Start: Migrated Logic from ChartProcessor.process_trade_batch ---
        if not batch_trades:
            # logging.warning(f"CandleFactory received empty trade batch for {self.symbol}") # Already logged upstream
            return

        # Sort trades by timestamp to ensure proper processing
        batch_trades.sort(key=lambda x: x["timestamp"])

        # Process each trade and track if any update occurred
        updated = False
        for trade in batch_trades:
            if self._process_trade(trade): # Call the internal processing method
                 updated = True

        updated_candles = self.ohlcv if updated else None # Return the internal df if updated
        # --- End: Migrated Logic ---

        # If candles were updated, emit the update with full market identifiers
        if updated_candles is not None and not updated_candles.empty:
            # Get the last row, which is the updated candle
            last_candle_series = self.ohlcv.iloc[-1]
            
            # Create a new DataFrame from this series.
            last_candle_df = pd.DataFrame([last_candle_series])
            
            # Set the index to be a DatetimeIndex, but KEEP the original 'dates' column.
            # This makes the format consistent with the initial historical data load.
            last_candle_df.set_index(pd.to_datetime(last_candle_df['dates'], unit='s'), inplace=True, drop=False)
            
            logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) emitting UPDATED_CANDLES signal")
            self.emitter.emit(
                Signals.UPDATED_CANDLES,
                exchange=self.exchange,
                symbol=self.symbol,
                timeframe=self.timeframe_str,
                candles=last_candle_df,
            )
            
        self.last_update_time = time.time()

    def _process_trade(self, trade_data: Dict) -> bool:
        """
        Process a single trade and update the internal OHLCV data if needed.

        Args:
            trade_data: Dictionary containing trade information

        Returns:
            True if candle was updated, False otherwise
        """
        timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
        price = round(trade_data["price"], self.precision_digits)
        volume = trade_data["amount"]

        # Adjust timestamp to the candle boundary
        adjusted_timestamp = timestamp - (timestamp % self.timeframe_in_seconds)

        # --- Debug Logging Start ---
        log_prefix = f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) _process_trade:"
        logging.debug(f"{log_prefix} Trade(ts={timestamp}, adj_ts={adjusted_timestamp}), LastCandle(ts={self.last_candle_timestamp}), TF(s)={self.timeframe_in_seconds}, OHLCV_Empty={self.ohlcv.empty}")
        # --- Debug Logging End ---

        # Initialize last candle timestamp if not set
        if self.last_candle_timestamp is None and not self.ohlcv.empty:
            self.last_candle_timestamp = self.ohlcv["dates"].iloc[-1]
        elif self.last_candle_timestamp is None:
            # If OHLCV is empty and no last timestamp, this is the very first trade
            logging.info(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) processing first trade.")
            self.last_candle_timestamp = adjusted_timestamp

        # Check if this trade belongs to a new candle
        # Use >= for safety, although > should be sufficient if timestamps are precise
        if adjusted_timestamp >= self.last_candle_timestamp + self.timeframe_in_seconds:
            logging.debug(f"{log_prefix} Branch 1: New Candle") # Debug
            # Start a new candle
            logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) starting new candle at {datetime.fromtimestamp(self.last_candle_timestamp + self.timeframe_in_seconds)}")
            new_candle = {
                "dates": self.last_candle_timestamp + self.timeframe_in_seconds,
                "opens": price,
                "highs": price,
                "lows": price,
                "closes": price,
                "volumes": volume,
            }
            # Add new candle to the dataframe
            new_candle_df = pd.DataFrame([new_candle])
            self.ohlcv = pd.concat([self.ohlcv, new_candle_df], ignore_index=True)
            self.last_candle_timestamp += self.timeframe_in_seconds
            return True # Candle data changed

        elif not self.ohlcv.empty and adjusted_timestamp == self.last_candle_timestamp:
            logging.debug(f"{log_prefix} Branch 2: Update Current Candle") # Debug
            # Update the current (last) candle if the trade falls within its boundary
            logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) updating current candle.")
            last_idx = self.ohlcv.index[-1]
            self.ohlcv.at[last_idx, "highs"] = max(
                self.ohlcv.at[last_idx, "highs"], price
            )
            self.ohlcv.at[last_idx, "lows"] = min(
                self.ohlcv.at[last_idx, "lows"], price
            )
            self.ohlcv.at[last_idx, "closes"] = price
            self.ohlcv.at[last_idx, "volumes"] += volume
            return True # Candle data changed

        elif self.ohlcv.empty:
            logging.debug(f"{log_prefix} Branch 3: Initialize First Candle") # Debug
            # Initialize the first candle if ohlcv is empty
            logging.info(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initializing first candle.")
            new_candle = {
                "dates": adjusted_timestamp,
                "opens": price,
                "highs": price,
                "lows": price,
                "closes": price,
                "volumes": volume,
            }
            # Convert to DataFrame
            new_candle_df = pd.DataFrame([new_candle])
            self.ohlcv = new_candle_df
            self.last_candle_timestamp = adjusted_timestamp
            return True # Candle data changed

        else:
             logging.debug(f"{log_prefix} Branch 4: Ignore Trade (Else condition)") # Debug
             # Trade might be older than the last candle or have other issues, ignore for now
             logging.warning(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) ignoring trade timestamp {timestamp} relative to last candle {self.last_candle_timestamp}")
             return False

    def try_resample(self, new_timeframe: str, active_exchange):
        """Attempts to resample existing candle data to a new timeframe."""
        # --- Start: Migrated Logic from ChartProcessor.try_resample ---
        new_timeframe_seconds = timeframe_to_seconds(new_timeframe)
        success = False
        resampled_data = None

        # Can only resample to larger timeframes if data exists
        if new_timeframe_seconds <= self.timeframe_in_seconds or self.ohlcv.empty:
            logging.warning(f"CandleFactory ({self.exchange}/{self.symbol}) cannot resample from {self.timeframe_str} to {new_timeframe} (or no data).")
            # Still update internal timeframe if needed, but report failure
            # self.timeframe_str = new_timeframe # Decided against this - let ChartWidget manage this
            # self.timeframe_seconds = new_timeframe_seconds
            success = False
            resampled_data = None
        else:
            try:
                logging.info(f"CandleFactory ({self.exchange}/{self.symbol}) attempting resample from {self.timeframe_str} to {new_timeframe}")
                df_copy = self.ohlcv.copy()

                # Convert timestamps to pandas datetime
                if "dates" in df_copy.columns:
                    df_copy["dates_dt"] = pd.to_datetime(df_copy["dates"], unit='s')
                    df_copy.set_index("dates_dt", inplace=True)

                    # Resample to the new timeframe
                    rule = self.__timeframe_to_pandas_rule(new_timeframe)
                    resampled = pd.DataFrame()

                    # Apply resampling rules for OHLCV
                    resampled["opens"] = df_copy["opens"].resample(rule).first()
                    resampled["highs"] = df_copy["highs"].resample(rule).max()
                    resampled["lows"] = df_copy["lows"].resample(rule).min()
                    resampled["closes"] = df_copy["closes"].resample(rule).last()
                    resampled["volumes"] = df_copy["volumes"].resample(rule).sum()

                    # Drop rows where all OHLCV values are NaN (can happen with empty intervals)
                    resampled.dropna(subset=["opens", "highs", "lows", "closes"], how='all', inplace=True)

                    if not resampled.empty:
                        # Convert timestamps back to seconds
                        resampled["dates"] = resampled.index.astype('int64') // 10**9

                        # Reset index to get dates as a column
                        resampled_data = resampled.reset_index(drop=True)[["dates", "opens", "highs", "lows", "closes", "volumes"]] # Ensure column order

                        # Update internal state ONLY if resampling succeeded
                        self.ohlcv = resampled_data.copy() # Store the resampled data
                        self.timeframe_str = new_timeframe
                        self.timeframe_in_seconds = new_timeframe_seconds
                        self.last_candle_timestamp = self.ohlcv["dates"].iloc[-1] # Update last timestamp
                        success = True
                        logging.info(f"CandleFactory ({self.exchange}/{self.symbol}) successfully resampled {len(self.ohlcv)} candles to {new_timeframe}")
                    else:
                         logging.warning(f"CandleFactory ({self.exchange}/{self.symbol}) resampling to {new_timeframe} resulted in empty DataFrame.")
                         success = False
                         resampled_data = None

            except Exception as e:
                 logging.error(f"CandleFactory ({self.exchange}/{self.symbol}) failed during resampling to {new_timeframe}: {e}", exc_info=True)
                 success = False
                 resampled_data = None
        # --- End: Migrated Logic ---

        if success and resampled_data is not None and not resampled_data.empty:
            logging.info(f"CandleFactory ({self.exchange}/{self.symbol}) successfully resampled to {new_timeframe}")
            # Emit an event to update the candles with full market identifiers
            self.emitter.emit(
                Signals.UPDATED_CANDLES,
                exchange=self.exchange,
                symbol=self.symbol,
                timeframe=self.timeframe_str,
                candles=resampled_data,
            )
            
            # Update the timeframe string internally *after* emitting with the new timeframe
            self.timeframe_str = new_timeframe
            
            return True
        else:
            logging.warning(f"CandleFactory ({self.exchange}/{self.symbol}) failed to resample to {new_timeframe}")
            # If resampling was not successful, just update the internal timeframe
            self.timeframe_str = new_timeframe # Still update internal state
            # Do not emit candles if resampling failed
            return False

    def __timeframe_to_pandas_rule(self, timeframe: str) -> str:
        """Converts a timeframe string (e.g., '1m', '1h') to a pandas resampling rule string."""
        if timeframe.endswith('m'):
            return timeframe[:-1] + 'T'  # Use 'T' for minutes
        elif timeframe.endswith('h'):
            return timeframe[:-1] + 'H'
        elif timeframe.endswith('d'):
            return timeframe[:-1] + 'D'
        elif timeframe.endswith('w'):
            return timeframe[:-1] + 'W'
        else:
            # Default or raise error? Let's default to minutes for safety
            logging.warning(f"Could not convert timeframe '{timeframe}' to pandas rule, defaulting to 'T'.")
            return 'T'

    def get_candle_data(self) -> pd.DataFrame:
        """Returns the current internal OHLCV DataFrame."""
        return self.ohlcv.copy() # Return a copy to prevent external modification

    def set_trade_batch(self, sender, app_data, user_data):
        self.max_trades_per_candle_update = app_data

    def set_initial_data(self, initial_candles_df: pd.DataFrame):
        """Sets the initial historical data for the factory."""
        if initial_candles_df is not None and not initial_candles_df.empty:
            # Ensure correct dtypes, especially for dates (assuming seconds since epoch)
            try:
                df_copy = initial_candles_df.copy()
                if 'dates' in df_copy.columns:
                    # Log original dtype and max value for debugging
                    logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initial 'dates' dtype: {df_copy['dates'].dtype}, max: {df_copy['dates'].max() if not df_copy.empty else 'N/A'}")

                    if not pd.api.types.is_numeric_dtype(df_copy['dates']):
                        if pd.api.types.is_datetime64_any_dtype(df_copy['dates']):
                             # Datetime64 is likely nanoseconds since epoch
                             df_copy['dates'] = df_copy['dates'].astype(np.int64) // 1_000_000_000 # Convert ns to s
                        else:
                             # Attempt conversion from other formats (e.g., object strings)
                             df_copy['dates'] = pd.to_datetime(df_copy['dates'], errors='coerce')
                             # Check if conversion worked before converting to int
                             if pd.api.types.is_datetime64_any_dtype(df_copy['dates']):
                                 df_copy['dates'] = df_copy['dates'].astype(np.int64) // 1_000_000_000 # Convert ns to s
                             else:
                                 # Handle cases where pd.to_datetime failed (result is NaT or original)
                                 # Try converting directly to numeric, assuming it might be ms/s in string/object form
                                 df_copy['dates'] = pd.to_numeric(df_copy['dates'], errors='coerce')
                                 # Now check if it needs ms -> s conversion (only if numeric)
                                 # Use a simpler heuristic: > 2 billion likely means milliseconds
                                 if pd.api.types.is_numeric_dtype(df_copy['dates']) and not df_copy['dates'].isna().all() and df_copy['dates'].max() > 2_000_000_000:
                                     logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initial 'dates' converting potential ms to s after pd.to_numeric.")
                                     df_copy['dates'] = df_copy['dates'] / 1000
                    elif not df_copy['dates'].isna().all() and df_copy['dates'].max() > 2_000_000_000:
                        # Already numeric, check if it's milliseconds
                        logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initial 'dates' are numeric, converting potential ms to s.")
                        df_copy['dates'] = df_copy['dates'] / 1000
                    
                    # Log after conversion attempts
                    logging.debug(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) 'dates' after conversion - dtype: {df_copy['dates'].dtype}, max: {df_copy['dates'].max() if not df_copy.empty and pd.api.types.is_numeric_dtype(df_copy['dates']) and not df_copy['dates'].isna().all() else 'N/A or Non-numeric'}")

                    # Drop rows with invalid dates (NaT or NaN) after conversion
                    df_copy.dropna(subset=['dates'], inplace=True)
                else:
                    logging.error(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initial data missing 'dates' column.")
                    return

                if not df_copy.empty:
                     self.ohlcv = df_copy.reset_index(drop=True) # Ensure clean index
                     # Ensure we take the last timestamp *after* potential ms -> s conversion
                     self.last_candle_timestamp = self.ohlcv["dates"].iloc[-1] # This should now be in seconds
                     logging.info(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initialized with {len(self.ohlcv)} historical candles. Last timestamp (seconds): {self.last_candle_timestamp}") # Adjusted log message
                else:
                     logging.warning(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) initial data was empty after date processing.")

            except Exception as e:
                logging.error(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) failed to set initial data: {e}", exc_info=True)
        else:
             logging.warning(f"CandleFactory ({self.exchange}/{self.symbol}/{self.timeframe_str}) received empty initial data.")
             
    def cleanup(self):
        """Unregister listeners to prevent potential memory leaks."""
        try:
            logging.info(f"Cleaning up CandleFactory for {self.exchange}/{self.symbol}/{self.timeframe_str}")
            # Unregister the specific listener method
            self.emitter.unregister(Signals.NEW_TRADE, self._on_new_trade)
            logging.debug(f"Unregistered NEW_TRADE listener for CandleFactory {self.exchange}/{self.symbol}/{self.timeframe_str}")
        except Exception as e:
            # Log if unregistering fails for some reason
            logging.error(f"Error during CandleFactory cleanup for {self.exchange}/{self.symbol}/{self.timeframe_str}: {e}", exc_info=True)