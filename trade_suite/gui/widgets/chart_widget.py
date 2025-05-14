import logging
import time
import dearpygui.dearpygui as dpg
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime # Added for status bar update

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget
from trade_suite.gui.utils import timeframe_to_dpg_time_unit

# Forward declaration for type hinting
if TYPE_CHECKING:
    from trade_suite.gui.task_manager import TaskManager


class ChartWidget(DockableWidget):
    """
    Widget for displaying candlestick charts for cryptocurrency trading.
    Includes basic indicator support (EMA).
    """
    
    def __init__(
        self,
        emitter: SignalEmitter,
        task_manager: 'TaskManager', # Added TaskManager
        exchange: str,
        symbol: str,
        timeframe: str,
        instance_id: Optional[str] = None,
        width: int = 800,
        height: int = 500,
    ):
        """
        Initialize a chart widget.
        
        Args:
            emitter: Signal emitter
            task_manager: Task manager instance
            exchange: Exchange name (e.g., 'coinbase')
            symbol: Trading pair (e.g., 'BTC/USD')
            timeframe: Timeframe (e.g., '1m', '1h')
            instance_id: Optional unique instance identifier
            width: Initial widget width
            height: Initial widget height
        """
        # Create a unique ID if not provided
        if instance_id is None:
            # Append timeframe to instance ID for uniqueness if multiple timeframes allowed
            instance_id = f"{exchange}_{symbol}_{timeframe}".lower().replace("/", "")
            
        # IMPORTANT: The window_tag property from DockableWidget base class is used as the widget's unique identifier
        # This tag is used to:
        # 1. Reference the DPG window item
        # 2. Store configuration (exchange, symbol, timeframe)
        # 3. Setup DearPyGui specific elements for the chart
        # The id format is "widget_chart_[instance_id]" from the DockableWidget class
        super().__init__(
            title=f"Chart - {exchange.upper()} {symbol} ({timeframe})",
            widget_type="chart",
            emitter=emitter,
            task_manager=task_manager, # Pass task_manager to base
            instance_id=instance_id,
            width=width,
            height=height,
        )
        
        # Chart configuration
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Chart data
        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        
        # Cached python lists for fast incremental updates (avoids DataFrame -> list conversion each frame)
        self._dates_list: list[float] = []
        self._opens_list: list[float] = []
        self._highs_list: list[float] = []
        self._lows_list: list[float] = []
        self._closes_list: list[float] = []
        self._volumes_list: list[float] = []
        
        # UI components
        self.chart_plot_tag = f"{self.window_tag}_plot"
        self.volume_plot_tag = f"{self.window_tag}_volume"
        self.candle_series_tag = f"{self.window_tag}_candles"
        self.volume_series_tag = f"{self.window_tag}_volumes"
        self.x_axis_tag = f"{self.window_tag}_xaxis"
        self.y_axis_tag = f"{self.window_tag}_yaxis"
        self.volume_y_axis_tag = f"{self.window_tag}_volume_yaxis"
        # Status bar tags
        self.last_update_tag = f"{self.window_tag}_last_update"
        self.open_tag = f"{self.window_tag}_open"
        self.high_tag = f"{self.window_tag}_high"
        self.low_tag = f"{self.window_tag}_low"
        self.close_tag = f"{self.window_tag}_close"
        self.price_tag = f"{self.window_tag}_price" # Tag for price display in top controls
        
        # Internal state
        self.auto_fit_enabled = True
        self.initial_load_complete = False # Flag to track if initial data loaded
        self.symbol_input_tag = f"{self.window_tag}_symbol_input" # Add tag for symbol input
        
        # Indicator State
        self.show_ema = False
        self.ema_spans = [10, 25, 50, 100, 200]
        self.ema_series_tags: Dict[int, int] = {} # {span: series_tag}
    
    def get_requirements(self) -> Dict[str, Any]:
        """Define the data requirements for the ChartWidget."""
        return {
            "type": "candles",
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Returns the configuration needed to recreate this ChartWidget."""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }
    
    def build_menu(self) -> None:
        """Build the chart widget's menu bar."""
        # Add Symbol Change UI
        with dpg.menu(label="Symbol"):
            dpg.add_listbox(
                items=list(self.task_manager.data.exchange_list[self.exchange].symbols),
                callback=self._on_symbol_change,
                width=120,
                num_items=10
            )

        # Add Timeframe Change UI
        with dpg.menu(label="Timeframes"):
            # TODO: Potentially make timeframes dynamic based on exchange capabilities
            dpg.add_listbox(
                items=list(self.task_manager.data.exchange_list[self.exchange].timeframes),
                callback=self._on_timeframe_change,
                width=120,
                num_items=10
            )
        
        with dpg.menu(label="View"):
            dpg.add_menu_item(
                label="Auto-fit",
                check=True,
                default_value=self.auto_fit_enabled,
                callback=self._toggle_auto_fit
            )
            
            dpg.add_menu_item(
                label="Fit Now (F)",
                callback=self._fit_chart,
                shortcut="F"
            )
        
        # Indicators Menu
        with dpg.menu(label="Indicators"):
            with dpg.menu(label="Moving Averages"):
                dpg.add_checkbox(
                    label="Show EMAs",
                    default_value=self.show_ema,
                    callback=self._toggle_ema_visibility
                )
                # TODO: Add options for configuring EMA spans
    
    def build_content(self) -> None:
        """Build the chart widget's content."""
        # Top controls (Consider moving timeframe selector to menu/toolbar)
        with dpg.group(horizontal=True):
            dpg.add_text(f"{self.symbol}") # Display symbol
            # Placeholder for current price
            dpg.add_text(" | Price:", tag=self.price_tag)
            dpg.add_spacer(width=20)
            
            # Add a fit button for quick access
            dpg.add_button(
                label="Fit Chart",
                callback=self._fit_chart,
                width=80
            )
        
        # Chart with subplots
        with dpg.subplots(
            rows=2,
            columns=1,
            row_ratios=[0.8, 0.2],
            link_all_x=True,
            tag=f"{self.window_tag}_subplots",
            height=-1, # Fill available space
            width=-1
        ):
            # Candlestick chart plot
            with dpg.plot(label=f"Price Action", tag=self.chart_plot_tag, no_title=True):
                dpg.add_plot_legend()
                
                # X Axis (hidden ticks/labels, linked)
                self.x_axis_tag = dpg.add_plot_axis(
                    dpg.mvXAxis,
                    scale=dpg.mvPlotScale_Time, # Use time scale
                    no_tick_marks=True,
                    no_tick_labels=True,
                    tag=f"{self.window_tag}_xaxis_price" # Unique tag
                )
                
                # Y Axis (Price)
                with dpg.plot_axis(dpg.mvYAxis, label="Price", tag=self.y_axis_tag) as y_axis:
                    self.candle_series_tag = dpg.add_candle_series(
                        dates=[], opens=[], closes=[], lows=[], highs=[],
                        label=self.symbol,
                        time_unit=timeframe_to_dpg_time_unit(self.timeframe),
                        weight=0.2
                    )
                    # Indicator series will be added here dynamically
            
            # Volume chart plot
            with dpg.plot(label="Volume", tag=self.volume_plot_tag, no_title=True):
                dpg.add_plot_legend()
                
                # X Axis (visible ticks/labels, linked)
                dpg.add_plot_axis(
                    dpg.mvXAxis,
                    time=True,
                    tag=f"{self.window_tag}_xaxis_volume" # Unique tag
                )
                
                # Y Axis (Volume)
                with dpg.plot_axis(dpg.mvYAxis, label="Volume", tag=self.volume_y_axis_tag):
                    self.volume_series_tag = dpg.add_bar_series(
                        x=[], y=[], label="Volume",
                    )
    
    def build_status_bar(self) -> None:
        """Build the chart widget's status bar."""
        dpg.add_text("Last Update: ")
        dpg.add_text("Never", tag=self.last_update_tag)
        dpg.add_spacer(width=20)
        dpg.add_text("O: ")
        dpg.add_text("0.00", tag=self.open_tag)
        dpg.add_spacer(width=10)
        dpg.add_text("H: ")
        dpg.add_text("0.00", tag=self.high_tag)
        dpg.add_spacer(width=10)
        dpg.add_text("L: ")
        dpg.add_text("0.00", tag=self.low_tag)
        dpg.add_spacer(width=10)
        dpg.add_text("C: ")
        dpg.add_text("0.00", tag=self.close_tag)
    
    def register_handlers(self) -> None:
        """Register event handlers for chart-related signals."""
        # Listen for initial candle data
        self.emitter.register(Signals.NEW_CANDLES, self._on_new_candles)
        # Listen for updates to candles (e.g., from real-time trades)
        self.emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        # Note: Timeframe changes are handled by the menu callback (_on_timeframe_change)
        # Note: Symbol changes are handled by the menu callback (_on_symbol_change)
        # Note: NEW_TRADE is handled by CandleFactory/ChartProcessor upstream
    
    def update(self, data: pd.DataFrame | None) -> None:
        """
        Update the chart with new OHLCV data. Assumes 'dates' are numeric timestamps (seconds or ms).

        Args:
            data: DataFrame with OHLCV data, or None. An empty DataFrame clears the chart.
            Chart widget_chart_coinbase_btcusd_1h received data:               
                          dates     opens     highs      lows    closes     volumes
            0     1741482000000  86393.89  86480.00  86042.75  86169.04   71.885963
        """
        if isinstance(data, pd.DataFrame) and not data.empty:
            processed_data = data.copy() # Work with a copy

            # Ensure 'dates' column is numeric, log error if not
            if not pd.api.types.is_numeric_dtype(processed_data['dates']):
                logging.error(f"Chart {self.window_tag} received non-numeric 'dates'. Cannot update.")
                return

            # Ensure timestamps are in seconds, converting from milliseconds if necessary
            # Use simpler heuristic: > 2 billion suggests milliseconds
            if not processed_data['dates'].isna().all() and processed_data['dates'].max() > 2_000_000_000:
                 logging.debug(f"Chart {self.window_tag}: Detected potential millisecond timestamps, converting to seconds.")
                 processed_data['dates'] = processed_data['dates'] / 1000
            
            # Ensure numeric types for OHLCV columns (handles potential strings)
            for col in ["opens", "highs", "lows", "closes", "volumes"]:
                 if col in processed_data.columns and not pd.api.types.is_numeric_dtype(processed_data[col]):
                     processed_data[col] = pd.to_numeric(processed_data[col], errors='coerce')
                     # Optionally handle NaNs introduced by coercion if necessary
                     if processed_data[col].isnull().any():
                         logging.warning(f"Chart {self.window_tag}: Found non-numeric values in column '{col}' after conversion. NaNs introduced.")
                         # Depending on requirements, you might dropna, fillna, or return

            # Replace internal DataFrame and rebuild caches
            self.ohlcv = processed_data
            self._dates_list = self.ohlcv["dates"].tolist()
            self._opens_list = self.ohlcv["opens"].tolist()
            self._highs_list = self.ohlcv["highs"].tolist()
            self._lows_list = self.ohlcv["lows"].tolist()
            self._closes_list = self.ohlcv["closes"].tolist()
            self._volumes_list = self.ohlcv["volumes"].tolist()
            self._update_chart(partial=False)
            
        elif isinstance(data, pd.DataFrame): # Handle case where an empty dataframe is sent to clear the chart
            logging.debug(f"Chart {self.window_tag} received empty candle update, clearing chart.")
            # Set ohlcv to an empty dataframe with the correct columns to clear
            self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            self._dates_list = []
            self._opens_list = []
            self._highs_list = []
            self._lows_list = []
            self._closes_list = []
            self._volumes_list = []
            self._update_chart(partial=False) # Update to show empty state
        elif data is None:
             logging.debug(f"Chart {self.window_tag} received None data, ignoring update.")
        else:
             logging.warning(f"Chart {self.window_tag} received unexpected data type: {type(data)}")
    
    def _update_chart(self, partial: bool = True) -> None:
        """Update the chart display with current OHLCV data and indicators."""
        if not self.is_created:
             logging.warning(f"Attempted to update chart {self.window_tag} before creation.")
             return

        dates_list = self._dates_list if not self.ohlcv.empty else []

        # --- Update Core Series ---
        # Log data being sent to DPG
        if not self.ohlcv.empty:
            logging.debug(f"Chart {self.window_tag} Sending to DPG - Shape: {self.ohlcv.shape}")
            logging.debug(f"Chart {self.window_tag} Sending to DPG - Last Row:\n{self.ohlcv.iloc[-1:].to_string()}")
        else:
            logging.debug(f"Chart {self.window_tag} Sending empty data to DPG.")

        # Update candle series
        if dpg.does_item_exist(self.candle_series_tag):
             dpg.configure_item(
                 self.candle_series_tag,
                 dates=dates_list,
                 opens=self._opens_list if not self.ohlcv.empty else [],
                 highs=self._highs_list if not self.ohlcv.empty else [],
                 lows=self._lows_list if not self.ohlcv.empty else [],
                 closes=self._closes_list if not self.ohlcv.empty else [],
                 time_unit=timeframe_to_dpg_time_unit(self.timeframe) # Add time_unit update
             )
        else:
            logging.warning(f"Candle series {self.candle_series_tag} not found for update.")

        # Update volume series
        if dpg.does_item_exist(self.volume_series_tag):
             dpg.configure_item(
                 self.volume_series_tag,
                 x=dates_list,
                 y=self._volumes_list if not self.ohlcv.empty else [],
             )
        else:
             logging.warning(f"Volume series {self.volume_series_tag} not found for update.")

        # --- Update Indicators ---
        self._update_indicator_series() # Update EMA lines based on current data and state

        # --- Update Status Bar & Price Display ---
        if not self.ohlcv.empty:
            last_candle = self.ohlcv.iloc[-1]
            # Use try-except for safety as items might not exist briefly during setup/teardown
            try:
                if dpg.does_item_exist(self.open_tag): dpg.set_value(self.open_tag, f"{last_candle['opens']:.4f}")
                if dpg.does_item_exist(self.high_tag): dpg.set_value(self.high_tag, f"{last_candle['highs']:.4f}")
                if dpg.does_item_exist(self.low_tag): dpg.set_value(self.low_tag, f"{last_candle['lows']:.4f}")
                if dpg.does_item_exist(self.close_tag): dpg.set_value(self.close_tag, f"{last_candle['closes']:.4f}")
                if dpg.does_item_exist(self.price_tag): dpg.set_value(self.price_tag, f" | Price: ${last_candle['closes']:.2f}") # Update top price display
                if dpg.does_item_exist(self.last_update_tag):
                     timestamp = datetime.fromtimestamp(last_candle['dates'])
                     dpg.set_value(self.last_update_tag, timestamp.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception as e:
                 logging.warning(f"Error updating status bar for {self.window_tag}: {e}")
        else:
             # Clear status bar if no data
             try:
                 if dpg.does_item_exist(self.open_tag): dpg.set_value(self.open_tag, "N/A")
                 if dpg.does_item_exist(self.high_tag): dpg.set_value(self.high_tag, "N/A")
                 if dpg.does_item_exist(self.low_tag): dpg.set_value(self.low_tag, "N/A")
                 if dpg.does_item_exist(self.close_tag): dpg.set_value(self.close_tag, "N/A")
                 if dpg.does_item_exist(self.price_tag): dpg.set_value(self.price_tag, " | Price: N/A")
                 if dpg.does_item_exist(self.last_update_tag): dpg.set_value(self.last_update_tag, "Never")
             except Exception as e:
                 logging.warning(f"Error clearing status bar for {self.window_tag}: {e}")
        
        logging.debug(f"Chart {self.window_tag} updated with {len(self.ohlcv)} candles.")
    
    def _on_new_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):
        """Handle initial bulk loading of candle data."""
        if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:
            logging.info(f"Chart {self.window_tag} ({exchange}/{symbol}/{timeframe}) received NEW_CANDLES")
            # Perform the full update, replacing existing data
            self.update(candles)
            
            # Fit chart after initial load if auto-fit is enabled
            if self.auto_fit_enabled:
                self._fit_chart() # Fit after the first full data load
            self._update_indicator_series() # Calculate indicators after initial load
    
    def _on_updated_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):
        """Handle incremental updates to candle data (append or update last candle)."""
        if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:
            logging.debug(f"Chart {self.window_tag} ({exchange}/{symbol}/{timeframe}) received UPDATED_CANDLES - Shape: {candles.shape}")
            logging.debug(f"Chart {self.window_tag} Received Candle Data:\n{candles.to_string()}")
            
            if candles is None or candles.empty:
                 logging.debug(f"Chart {self.window_tag} received empty UPDATED_CANDLES, ignoring.")
                 return

            # Ensure incoming dates are numeric (seconds) like in self.update
            try:
                 processed_candles = candles.copy()
                 if not pd.api.types.is_numeric_dtype(processed_candles['dates']):
                     if pd.api.types.is_datetime64_any_dtype(processed_candles['dates']):
                          # Convert nanoseconds to seconds
                          processed_candles['dates'] = processed_candles['dates'].astype(np.int64) // 1_000_000_000
                     else:
                          # Try converting other types (e.g., object)
                          processed_candles['dates'] = pd.to_datetime(processed_candles['dates'], errors='coerce')
                          if pd.api.types.is_datetime64_any_dtype(processed_candles['dates']):
                              processed_candles['dates'] = processed_candles['dates'].astype(np.int64) // 1_000_000_000
                          else:
                              # Fallback: try direct numeric conversion (might be ms/s)
                              processed_candles['dates'] = pd.to_numeric(processed_candles['dates'], errors='coerce')
                              # Check for potential ms using simpler heuristic
                              if pd.api.types.is_numeric_dtype(processed_candles['dates']) and not processed_candles['dates'].isna().all() and processed_candles['dates'].max() > 2_000_000_000:
                                   logging.debug(f"_on_updated_candles {self.window_tag}: converting potential ms to s.")
                                   processed_candles['dates'] = processed_candles['dates'] / 1000
                 elif not processed_candles['dates'].isna().all() and processed_candles['dates'].max() > 2_000_000_000:
                     logging.debug(f"_on_updated_candles {self.window_tag}: numeric dates, converting potential ms to s.")
                     processed_candles['dates'] = processed_candles['dates'] / 1000

                 if processed_candles['dates'].isnull().any():
                      logging.error(f"UPDATED_CANDLES for chart {self.window_tag} contained invalid dates after conversion.")
                      return

            except Exception as e:
                 logging.error(f"Failed to process dates in UPDATED_CANDLES for chart {self.window_tag}: {e}")
                 return

            # Factory now sends only the single, latest candle row as a DataFrame.
            # Extract it as a Series.
            if len(processed_candles) == 1:
                 update_row = processed_candles.iloc[0] # Get the single row as a Series
            else:
               # Should not happen if Factory is correct, but handle defensively
               logging.error(f"Chart {self.window_tag} received {len(processed_candles)} rows in UPDATED_CANDLES, expected 1. Ignoring update.")
               return

            # --- Pre-Update Logging ---
            if self.ohlcv is not None and not self.ohlcv.empty:
                 logging.debug(f"Chart {self.window_tag} BEFORE update - Last OHLCV Row:\n{self.ohlcv.iloc[-1:].to_string()}")
            else:
                 logging.debug(f"Chart {self.window_tag} BEFORE update - OHLCV is empty.")
            # -------------------------

            if self.ohlcv is not None and not self.ohlcv.empty:
                 # Check if the incoming candle timestamp matches the last candle we have
                 last_candle_time = self.ohlcv['dates'].iloc[-1]
                 update_time = update_row['dates']

                 if update_time == last_candle_time:
                      # Update the last row in place
                      logging.debug(f"Chart {self.window_tag}: Updating last candle at {update_time}")
                      self.ohlcv.iloc[-1] = update_row # Replace the last row's data
                      # Reflect change in cached lists (last index)
                      last_idx = -1
                      self._dates_list[last_idx] = update_row["dates"]
                      self._opens_list[last_idx] = update_row["opens"]
                      self._highs_list[last_idx] = update_row["highs"]
                      self._lows_list[last_idx] = update_row["lows"]
                      self._closes_list[last_idx] = update_row["closes"]
                      self._volumes_list[last_idx] = update_row["volumes"]
                 elif update_time > last_candle_time:
                      # Append the new candle row
                      logging.debug(f"Chart {self.window_tag}: Appending new candle at {update_time}")
                      # Use pd.concat instead of append for future-proofing
                      self.ohlcv = pd.concat([self.ohlcv, update_row.to_frame().T], ignore_index=True)
                      # Append to cached lists
                      self._dates_list.append(update_row["dates"])
                      self._opens_list.append(update_row["opens"])
                      self._highs_list.append(update_row["highs"])
                      self._lows_list.append(update_row["lows"])
                      self._closes_list.append(update_row["closes"])
                      self._volumes_list.append(update_row["volumes"])
                 else:
                      # Incoming update is older than last candle? Ignore or handle?
                      logging.warning(f"Chart {self.window_tag}: Received out-of-order candle update (time {update_time} <= last time {last_candle_time}). Ignoring.")
                      return # Don't update chart for out-of-order data

            else:
                 # If self.ohlcv is empty, initialize it with the update
                 logging.info(f"Chart {self.window_tag}: Initializing OHLCV with first UPDATED_CANDLES.")
                 self.ohlcv = update_row.to_frame().T
                 self._dates_list = [update_row["dates"]]
                 self._opens_list = [update_row["opens"]]
                 self._highs_list = [update_row["highs"]]
                 self._lows_list = [update_row["lows"]]
                 self._closes_list = [update_row["closes"]]
                 self._volumes_list = [update_row["volumes"]]

            # --- Post-Update Logging ---
            if self.ohlcv is not None and not self.ohlcv.empty:
                logging.debug(f"Chart {self.window_tag} AFTER update - Last OHLCV Row:\n{self.ohlcv.iloc[-1:].to_string()}")
            else:
                logging.debug(f"Chart {self.window_tag} AFTER update - OHLCV is unexpectedly empty.")
            # ------------------------

            # Update the chart display with the modified self.ohlcv
            self._update_chart(partial=True)
            self._update_indicator_series() # Recalculate indicators with the new data

    def _update_status_bar(self, latest_candle):
         """Updates the status bar with the latest candle data."""
         if not self.is_created or latest_candle is None:
             return
         
         try:
             if dpg.does_item_exist(self.last_update_tag):
                  # Format timestamp nicely
                  dt_object = pd.to_datetime(latest_candle['dates'], unit='s')
                  dpg.set_value(self.last_update_tag, dt_object.strftime("%Y-%m-%d %H:%M:%S"))
             if dpg.does_item_exist(self.open_tag):
                  dpg.set_value(self.open_tag, f"{latest_candle['opens']:.2f}")
             if dpg.does_item_exist(self.high_tag):
                  dpg.set_value(self.high_tag, f"{latest_candle['highs']:.2f}")
             if dpg.does_item_exist(self.low_tag):
                  dpg.set_value(self.low_tag, f"{latest_candle['lows']:.2f}")
             if dpg.does_item_exist(self.close_tag):
                  dpg.set_value(self.close_tag, f"{latest_candle['closes']:.2f}")
         except Exception as e:
             logging.error(f"Error updating status bar for {self.window_tag}: {e}")

    def _toggle_ema_visibility(self, sender, app_data, user_data):
         self.show_ema = app_data
         self._update_indicator_series() # Update to show/hide
    
    def _update_indicator_series(self):
        """Calculates and updates/creates/hides EMA line series."""
        if not self.is_created or not dpg.does_item_exist(self.y_axis_tag):
            # Don't attempt updates if widget or axis isn't ready
            return

        if self.show_ema and not self.ohlcv.empty and 'closes' in self.ohlcv.columns:
            dates = self.ohlcv["dates"].tolist()
            close_prices = self.ohlcv["closes"]

            for span in self.ema_spans:
                try:
                     # Calculate EMA
                     ema_values = close_prices.ewm(span=span, adjust=False).mean().tolist()
                     series_tag = self.ema_series_tags.get(span)

                     if series_tag and dpg.does_item_exist(series_tag):
                         # Update existing series
                         dpg.set_value(series_tag, [dates, ema_values])
                         dpg.configure_item(series_tag, show=True) # Ensure visible
                     elif not series_tag:
                         # Create new series
                         new_tag = dpg.add_line_series(
                             dates,
                             ema_values,
                             label=f"EMA {span}",
                             parent=self.y_axis_tag, # Attach to price axis
                             show=True
                         )
                         self.ema_series_tags[span] = new_tag
                         logging.debug(f"Created EMA {span} series (tag {new_tag}) for {self.window_tag}")

                except Exception as e:
                     logging.error(f"Failed to calculate or plot EMA {span} for {self.window_tag}: {e}")

        else:
            # Hide all existing EMA series if show_ema is False or ohlcv is empty
            for span, series_tag in self.ema_series_tags.items():
                if dpg.does_item_exist(series_tag):
                    dpg.configure_item(series_tag, show=False)
    
    # --- Event Handlers & Callbacks ---
    
    def _on_symbol_change(self, sender=None, app_data=None, user_data=None):
        """Handles symbol changes initiated from the UI menu."""
        new_symbol = app_data
        
        # Basic validation
        if not new_symbol or new_symbol == self.symbol:
             logging.debug(f"Symbol change aborted for {self.window_tag}. New symbol same as old or empty: '{new_symbol}'")
             # Reset input field if it was different but invalid?
             dpg.set_value(self.symbol_input_tag, self.symbol)
             return
        
        logging.info(f"Symbol change requested for {self.window_tag} from {self.symbol} to {new_symbol}")

        # 1. Unsubscribe from old requirements
        self.initial_load_complete = False # Reset flag before unsubscribe/resubscribe
        try:
            self.task_manager.unsubscribe(self)
            logging.info(f"Unsubscribed {self.window_tag} before symbol change.")
        except Exception as e:
             logging.error(f"Error unsubscribing {self.window_tag} before symbol change: {e}", exc_info=True)
             # Proceeding might lead to duplicate subscriptions, maybe return?
             return

        # 2. Update internal state and UI elements
        self.symbol = new_symbol
        # Keep the current timeframe

        # Update window title
        new_title = f"Chart - {self.exchange.upper()} {self.symbol} ({self.timeframe})"
        if dpg.does_item_exist(self.window_tag):
            dpg.set_item_label(self.window_tag, new_title)

        # Clear existing data and series
        self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
        self._dates_list = []
        self._opens_list = []
        self._highs_list = []
        self._lows_list = []
        self._closes_list = []
        self._volumes_list = []
        self._clear_indicator_series() # Clear EMA lines
        self._update_chart(partial=False) # Update chart to show empty state (or loading state)

        # Update the symbol display text (top control)
        # TODO: Find the actual tag for the symbol display if it exists
        # For now, assume title update is sufficient or handled elsewhere.

        # 3. Subscribe to new requirements
        try:
            new_requirements = self.get_requirements() # Get requirements with the new symbol
            self.task_manager.subscribe(self, new_requirements)
            logging.info(f"Resubscribed {self.window_tag} with new requirements: {new_requirements}")
        except Exception as e:
            logging.error(f"Error resubscribing {self.window_tag} after symbol change: {e}", exc_info=True)
            # Widget might be left in a state without data.

        # Clear existing data and series
        self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
        self._dates_list = []
        self._opens_list = []
        self._highs_list = []
        self._lows_list = []
        self._closes_list = []
        self._volumes_list = []
        self._clear_indicator_series() # Clear EMA lines
        self._update_chart(partial=False) # Update chart to show empty state

        # TODO: IMPORTANT - Need to signal upstream (e.g., DashboardProgram)
        # to stop the old data stream and start one for the new symbol/timeframe.
        # This widget should not manage data streams directly.
        # Emitting a specific signal might be appropriate here, or relying on
        # the upstream controller that initiated the SYMBOL_CHANGED signal.
        logging.warning(f"Symbol changed for {self.window_tag}. Upstream needs to handle data stream restart.")
    
    def _on_timeframe_change(self, sender, app_data, user_data) -> None:
        logging.info(f"Timeframe change received for {self.window_tag}: {sender}, {app_data}, {user_data}")
        # new_timeframe = user_data # Incorrect, use app_data for listbox selection
        new_timeframe = app_data
        
        """Handles timeframe changes from the menu."""
        if new_timeframe is not None and new_timeframe != self.timeframe: # Add None check
            self.initial_load_complete = False # Reset flag before changing timeframe
            logging.info(f"Timeframe changing for {self.window_tag} from {self.timeframe} to {new_timeframe}")
            
            # 1. Unsubscribe from old requirements
            try:
                self.task_manager.unsubscribe(self)
                logging.info(f"Unsubscribed {self.window_tag} before timeframe change.")
            except Exception as e:
                 logging.error(f"Error unsubscribing {self.window_tag} before timeframe change: {e}", exc_info=True)
                 return # Avoid changing state if unsubscribe failed
                
            # 2. Update internal state and UI elements
            self.timeframe = new_timeframe

            # Update window title
            new_title = f"Chart - {self.exchange.upper()} {self.symbol} ({self.timeframe})"
            if dpg.does_item_exist(self.window_tag):
                dpg.set_item_label(self.window_tag, new_title)

            # Clear existing data and series
            self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            self._dates_list = []
            self._opens_list = []
            self._highs_list = []
            self._lows_list = []
            self._closes_list = []
            self._volumes_list = []
            self._clear_indicator_series()
            
            # Reset the candle series with the new time unit
            if dpg.does_item_exist(self.candle_series_tag):
                dpg.configure_item(
                    self.candle_series_tag,
                    time_unit=timeframe_to_dpg_time_unit(new_timeframe)
                )
                
            self._update_chart(partial=False)

            # 3. Subscribe to new requirements
            try:
                new_requirements = self.get_requirements() # Get requirements with the new timeframe
                self.task_manager.subscribe(self, new_requirements)
                logging.info(f"Resubscribed {self.window_tag} with new requirements: {new_requirements}")
            except Exception as e:
                logging.error(f"Error resubscribing {self.window_tag} after timeframe change: {e}", exc_info=True)
    
    def _toggle_auto_fit(self, sender, value):
        """Toggle auto-fitting of chart axes."""
        self.auto_fit_enabled = value
        if self.auto_fit_enabled:
            self._fit_chart()
    
    def _fit_chart(self):
        """Fit the plot axes to the data."""
        if self.is_created:
             if dpg.does_item_exist(self.chart_plot_tag): dpg.fit_axis_data(self.y_axis_tag)
             if dpg.does_item_exist(self.volume_plot_tag): dpg.fit_axis_data(self.volume_y_axis_tag)
             # Fitting X axis might be needed too, especially if not auto-linked fully
             if dpg.does_item_exist(self.chart_plot_tag): dpg.fit_axis_data(self.x_axis_tag)
    
    def _clear_indicator_series(self):
         """Deletes existing EMA DPG items."""
         for span, tag in self.ema_series_tags.items():
             if dpg.does_item_exist(tag):
                 dpg.delete_item(tag)
                 logging.debug(f"Deleted EMA {span} series (tag {tag}) for {self.window_tag}")
         self.ema_series_tags.clear()
    
    # Helper to get defaults (could be moved to config/utils)
    def _get_default_timeframe(self) -> str:
         # Simplified - assumes '1h' default
         return '1h'
    
    # --- Overrides or specific implementations ---
    def close(self) -> None:
        """Close and destroy the widget, including cleanup."""
        logging.info(f"Closing ChartWidget: {self.window_tag}")
        # Any ChartWidget-specific cleanup needed before DPG deletion could go here.
        # (e.g., removing plot items if not handled automatically by deleting the window)
        self._clear_indicator_series() # Example: Clear indicators before closing
        
        # Call the base class close method to handle unsubscription and DPG item deletion
        super().close()

        # Unsubscribe from signals (optional - depends on emitter implementation)
        # self.emitter.unregister_all(self)
        
        # Call base class close
        # super().close()

        # Unsubscribe from signals (optional - depends on emitter implementation)
        # self.emitter.unregister_all(self)
        
        # Call base class close
        # super().close() 