import logging
import time
import dearpygui.dearpygui as dpg
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime # Added for status bar update

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget
from trade_suite.gui.utils import timeframe_to_dpg_time_unit


class ChartWidget(DockableWidget):
    """
    Widget for displaying candlestick charts for cryptocurrency trading.
    Includes basic indicator support (EMA).
    """
    
    def __init__(
        self,
        emitter: SignalEmitter,
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
        # 2. Connect the widget to data streams via the TaskManager (as 'tab' parameter)
        # 3. Route signals from emitters to the correct widget instance
        # The id format is "widget_chart_[instance_id]" from the DockableWidget class
        super().__init__(
            title=f"Chart - {exchange.upper()} {symbol} ({timeframe})",
            widget_type="chart",
            emitter=emitter,
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
        
        # Indicator State
        self.show_ema = False
        self.ema_spans = [10, 25, 50, 100, 200]
        self.ema_series_tags: Dict[int, int] = {} # {span: series_tag}
    
    def build_menu(self) -> None:
        """Build the chart widget's menu bar."""
        with dpg.menu(label="Timeframes"):
            # TODO: Potentially make timeframes dynamic based on exchange capabilities
            for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                # Use radio buttons for single selection feel
                dpg.add_radio_button(
                    items=[tf], # Hacky way to use radio for single item selection visual
                    label=tf,
                    default_value=tf if tf == self.timeframe else "",
                    callback=lambda s, a, u: self._on_timeframe_change(u),
                    user_data=tf
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
                        time_unit=timeframe_to_dpg_time_unit(self.timeframe)
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
                        x=[], y=[], weight=0.7, label="Volume"
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
        # Listen for symbol changes originating elsewhere
        self.emitter.register(Signals.SYMBOL_CHANGED, self._on_symbol_change)
        # Note: Timeframe changes are handled by the menu callback (_on_timeframe_change)
        # Note: NEW_TRADE is handled by CandleFactory/ChartProcessor upstream
    
    def update(self, data: pd.DataFrame) -> None:
        """
        Update the chart with new OHLCV data.
        
        Args:
            data: DataFrame with OHLCV data
        """
        if isinstance(data, pd.DataFrame) and not data.empty:
            # Ensure timestamps are numeric (seconds since epoch)
            if not pd.api.types.is_numeric_dtype(data['dates']):
                 # Attempt conversion if datetime-like
                try:
                    data['dates'] = data['dates'].astype(np.int64) // 10**9
                except Exception as e:
                    logging.error(f"Failed to convert dates to numeric for chart {self.window_tag}: {e}")
                    return # Cannot plot non-numeric dates

            # Handle potential milliseconds
            if data['dates'].max() > time.time() * 2: # Heuristic: if max date is > 2x current time, likely ms
                 data['dates'] = data['dates'] / 1000

            self.ohlcv = data.copy() # Work with a copy
            self._update_chart()
        elif data is not None: # Handle case where empty dataframe is sent
             self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
             self._update_chart() # Update to clear the chart
    
    def _update_chart(self) -> None:
        """Update the chart display with current OHLCV data and indicators."""
        if not self.is_created:
             logging.warning(f"Attempted to update chart {self.window_tag} before creation.")
             return

        dates_list = self.ohlcv["dates"].tolist() if not self.ohlcv.empty else []

        # --- Update Core Series ---
        # Update candle series
        if dpg.does_item_exist(self.candle_series_tag):
             dpg.configure_item(
                 self.candle_series_tag,
                 dates=dates_list,
                 opens=self.ohlcv["opens"].tolist() if not self.ohlcv.empty else [],
                 highs=self.ohlcv["highs"].tolist() if not self.ohlcv.empty else [],
                 lows=self.ohlcv["lows"].tolist() if not self.ohlcv.empty else [],
                 closes=self.ohlcv["closes"].tolist() if not self.ohlcv.empty else [],
             )
        else:
            logging.warning(f"Candle series {self.candle_series_tag} not found for update.")


        # Update volume series
        if dpg.does_item_exist(self.volume_series_tag):
             dpg.configure_item(
                 self.volume_series_tag,
                 x=dates_list,
                 y=self.ohlcv["volumes"].tolist() if not self.ohlcv.empty else [],
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

        # We no longer auto-fit on every update, just on initial load and manual requests
    
    def _on_new_candles(self, tab, exchange, candles):
        """Handler for NEW_CANDLES signal (initial load)."""
        # Filter events specific to this widget instance based on its unique tag
        if tab == self.window_tag and exchange == self.exchange:
             logging.info(f"Chart {self.window_tag} received NEW_CANDLES")
             self.update(candles)
             # Auto-fit only on initial load, not on real-time updates
             if self.auto_fit_enabled:
                 self._fit_chart()
    
    def _on_updated_candles(self, tab, exchange, candles):
        """Handler for UPDATED_CANDLES signal (real-time updates)."""
        # Filter events specific to this widget instance
        if tab == self.window_tag and exchange == self.exchange:
             logging.debug(f"Chart {self.window_tag} received UPDATED_CANDLES - shape: {candles.shape if isinstance(candles, pd.DataFrame) else 'Not DataFrame'}")
             
             # Add more diagnostic logging
             if isinstance(candles, pd.DataFrame) and not candles.empty:
                 last_candle = candles.iloc[-1]
                 logging.debug(f"Last candle timestamp: {datetime.fromtimestamp(last_candle['dates'])} - close: {last_candle['closes']}")
             
             self.update(candles)
             # Don't auto-fit on updates to avoid constant rescaling
        elif tab == self.window_tag:
             # This log would catch mismatches in exchange
             logging.warning(f"Chart {self.window_tag} filtered out UPDATED_CANDLES - expected exchange {self.exchange} but got {exchange}")
        elif exchange == self.exchange:
             # This log would catch mismatches in tab
             logging.warning(f"Chart {self.window_tag} filtered out UPDATED_CANDLES - expected tab {self.window_tag} but got {tab}")
    
    # --- Indicator Methods ---
    
    def _toggle_ema_visibility(self, sender, app_data, user_data):
        """Callback for the EMA checkbox in the menu."""
        self.show_ema = app_data # Checkbox passes its state directly
        logging.info(f"EMA visibility toggled to {self.show_ema} for {self.window_tag}")
        self._update_indicator_series()
    
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
    
    def _on_symbol_change(self, exchange, tab, new_symbol):
        """Handles symbol changes initiated from signals (e.g., another widget)."""
        if exchange == self.exchange and tab == self.window_tag:
            logging.info(f"Symbol change detected for {self.window_tag} to {new_symbol}")
            self.symbol = new_symbol
            self.timeframe = self._get_default_timeframe() # Reset timeframe? Or keep? Let's keep for now.

            # Update window title
            new_title = f"Chart - {self.exchange.upper()} {self.symbol} ({self.timeframe})"
            if dpg.does_item_exist(self.window_tag):
                dpg.set_item_label(self.window_tag, new_title)

            # Clear existing data and series
            self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            self._clear_indicator_series() # Clear EMA lines
            self._update_chart() # Update chart to show empty state

            # TODO: IMPORTANT - Need to signal upstream (e.g., DashboardProgram)
            # to stop the old data stream and start one for the new symbol/timeframe.
            # This widget should not manage data streams directly.
            # Emitting a specific signal might be appropriate here, or relying on
            # the upstream controller that initiated the SYMBOL_CHANGED signal.
            logging.warning(f"Symbol changed for {self.window_tag}. Upstream needs to handle data stream restart.")
    
    def _on_timeframe_change(self, new_timeframe: str) -> None:
        """Handles timeframe changes from the menu."""
        if new_timeframe != self.timeframe:
            logging.info(f"Timeframe changing for {self.window_tag} from {self.timeframe} to {new_timeframe}")
            self.timeframe = new_timeframe

            # Update window title
            new_title = f"Chart - {self.exchange.upper()} {self.symbol} ({self.timeframe})"
            if dpg.does_item_exist(self.window_tag):
                dpg.set_item_label(self.window_tag, new_title)

            # Clear existing data and series
            self.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            self._clear_indicator_series()
            
            # Reset the candle series with the new time unit
            if dpg.does_item_exist(self.candle_series_tag):
                dpg.configure_item(
                    self.candle_series_tag,
                    time_unit=timeframe_to_dpg_time_unit(new_timeframe)
                )
                
            self._update_chart()

            # Signal upstream to change the data stream
            self.emitter.emit(
                Signals.TIMEFRAME_CHANGED,
                exchange=self.exchange,
                tab=self.window_tag, # Send own tag to identify source
                new_timeframe=new_timeframe
            )
            logging.warning(f"Timeframe changed for {self.window_tag}. Upstream needs to handle data stream restart.")
    
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
        """Clean up chart-specific resources before closing."""
        logging.info(f"Closing chart widget {self.window_tag}")
        # Potentially signal upstream to stop data streams associated with this widget
        # self.emitter.emit(Signals.WIDGET_CLOSING, widget_tag=self.window_tag, ...)
        self._clear_indicator_series() # Clean up DPG items
        super().close() # Call base class close to delete window 