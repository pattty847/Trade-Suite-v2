import logging
import dearpygui.dearpygui as dpg
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget


class ChartWidget(DockableWidget):
    """
    Widget for displaying candlestick charts for cryptocurrency trading.
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
            instance_id = f"{exchange}_{symbol}_{timeframe}".lower().replace("/", "")
            
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
        
        # Internal state
        self.auto_fit_enabled = True
    
    def build_menu(self) -> None:
        """Build the chart widget's menu bar."""
        with dpg.menu(label="Timeframes"):
            for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                dpg.add_menu_item(
                    label=tf,
                    callback=lambda sender, data, tf=tf: self._on_timeframe_change(tf)
                )
        
        with dpg.menu(label="View"):
            dpg.add_menu_item(
                label="Auto-fit",
                check=True,
                default_value=True,
                callback=self._toggle_auto_fit
            )
            
            dpg.add_menu_item(
                label="Fit Now",
                callback=self._fit_chart
            )
    
    def build_content(self) -> None:
        """Build the chart widget's content."""
        # Top controls
        with dpg.group(horizontal=True):
            # Symbol display
            dpg.add_text(f"{self.symbol}")
            
            # Timeframe selector
            dpg.add_combo(
                items=["1m", "5m", "15m", "1h", "4h", "1d"],
                default_value=self.timeframe,
                callback=lambda s, a: self._on_timeframe_change(a),
                width=80
            )
            
            # Placeholder for price
            self.price_tag = dpg.add_text("0.00")
        
        # Chart with subplots
        with dpg.subplots(
            rows=2,
            columns=1,
            row_ratios=[0.8, 0.2],
            link_all_x=True,
            tag=f"{self.window_tag}_subplots",
            height=-1,
            width=-1
        ):
            # Candlestick chart
            with dpg.plot(label=f"{self.symbol} | {self.timeframe}", tag=self.chart_plot_tag):
                dpg.add_plot_legend()
                
                self.x_axis_tag = dpg.add_plot_axis(
                    dpg.mvXAxis,
                    scale=dpg.mvPlotScale_Time,
                    no_tick_marks=True,
                    no_tick_labels=True,
                )
                
                with dpg.plot_axis(dpg.mvYAxis, label="Price", tag=self.y_axis_tag):
                    self.candle_series_tag = dpg.add_candle_series(
                        dates=[],
                        opens=[],
                        closes=[],
                        lows=[],
                        highs=[],
                        time_unit=dpg.mvTimeUnit_Min,
                        label=self.symbol
                    )
                    
            # Volume chart
            with dpg.plot(label="Volume", tag=self.volume_plot_tag, no_title=True):
                dpg.add_plot_legend()
                
                dpg.add_plot_axis(
                    dpg.mvXAxis,
                    scale=dpg.mvPlotScale_Time
                )
                
                with dpg.plot_axis(dpg.mvYAxis, label="Volume", tag=self.volume_y_axis_tag):
                    self.volume_series_tag = dpg.add_bar_series(
                        x=[],
                        y=[],
                        weight=0.7,
                        label="Volume"
                    )
    
    def build_status_bar(self) -> None:
        """Build the chart widget's status bar."""
        dpg.add_text("Last Update: ")
        self.last_update_tag = dpg.add_text("Never")
        dpg.add_spacer(width=20)
        dpg.add_text("O: ")
        self.open_tag = dpg.add_text("0.00")
        dpg.add_spacer(width=10)
        dpg.add_text("H: ")
        self.high_tag = dpg.add_text("0.00")
        dpg.add_spacer(width=10)
        dpg.add_text("L: ")
        self.low_tag = dpg.add_text("0.00")
        dpg.add_spacer(width=10)
        dpg.add_text("C: ")
        self.close_tag = dpg.add_text("0.00")
    
    def register_handlers(self) -> None:
        """Register event handlers for chart-related signals."""
        self.emitter.register(Signals.NEW_CANDLES, self._on_new_candles)
        self.emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        self.emitter.register(Signals.NEW_TRADE, self._on_new_trade)
    
    def update(self, data: pd.DataFrame) -> None:
        """
        Update the chart with new OHLCV data.
        
        Args:
            data: DataFrame with OHLCV data
        """
        if isinstance(data, pd.DataFrame) and not data.empty:
            self.ohlcv = data
            self._update_chart()
    
    def _update_chart(self) -> None:
        """Update the chart display with current OHLCV data."""
        if self.ohlcv.empty:
            return
            
        # Ensure timestamps are in seconds (not milliseconds)
        if "dates" in self.ohlcv.columns and self.ohlcv["dates"].max() > 1e12:
            self.ohlcv['dates'] = self.ohlcv['dates'] / 1000
        
        # Update candle series
        dpg.configure_item(
            self.candle_series_tag,
            dates=self.ohlcv["dates"].tolist(),
            opens=self.ohlcv["opens"].tolist(),
            highs=self.ohlcv["highs"].tolist(),
            lows=self.ohlcv["lows"].tolist(),
            closes=self.ohlcv["closes"].tolist(),
        )
        
        # Update volume series
        dpg.configure_item(
            self.volume_series_tag,
            x=self.ohlcv["dates"].tolist(),
            y=self.ohlcv["volumes"].tolist(),
        )
        
        # Update status bar with latest candle
        if not self.ohlcv.empty:
            last_candle = self.ohlcv.iloc[-1]
            dpg.set_value(self.open_tag, f"{last_candle['opens']:.2f}")
            dpg.set_value(self.high_tag, f"{last_candle['highs']:.2f}")
            dpg.set_value(self.low_tag, f"{last_candle['lows']:.2f}")
            dpg.set_value(self.close_tag, f"{last_candle['closes']:.2f}")
            dpg.set_value(self.price_tag, f"${last_candle['closes']:.2f}")
            
            # Update last update timestamp
            from datetime import datetime
            timestamp = datetime.fromtimestamp(last_candle['dates'])
            dpg.set_value(self.last_update_tag, timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        
        # Auto-fit if enabled
        if self.auto_fit_enabled:
            self._fit_chart()
    
    def _on_new_candles(self, tab, exchange, candles):
        """Handler for NEW_CANDLES signal."""
        # Filter events for this chart
        if tab == self.window_tag and exchange == self.exchange:
            self.update(candles)
    
    def _on_updated_candles(self, tab, exchange, candles):
        """Handler for UPDATED_CANDLES signal."""
        # Filter events for this chart
        if tab == self.window_tag and exchange == self.exchange:
            self.update(candles)
    
    def _on_new_trade(self, tab, exchange, trade_data):
        """Handler for NEW_TRADE signal."""
        # Filter events for this chart
        if tab == self.window_tag and exchange == self.exchange:
            # Update price display with latest trade
            price = trade_data.get("price", 0)
            dpg.set_value(self.price_tag, f"${price:.2f}")
            
            # Draw a circle for the trade (optional visualization)
            timestamp = trade_data.get("timestamp", 0) / 1000  # Convert to seconds
            volume = trade_data.get("amount", 0)
            
            # Only draw if we have meaningful data
            if timestamp > 0 and price > 0:
                dpg.draw_circle(
                    parent=self.chart_plot_tag,
                    center=[timestamp, price],
                    radius=max(1, volume * 5),  # Scale radius by volume
                    color=[255, 255, 255, 100],  # White with transparency
                    fill=[255, 255, 255, 50],    # Filled with more transparency
                    thickness=1
                )
    
    def _on_timeframe_change(self, new_timeframe: str) -> None:
        """Change the chart timeframe."""
        if new_timeframe == self.timeframe:
            return
            
        logging.info(f"Changing timeframe from {self.timeframe} to {new_timeframe}")
        self.timeframe = new_timeframe
        
        # Update chart title
        dpg.configure_item(
            self.chart_plot_tag, 
            label=f"{self.symbol} | {self.timeframe}"
        )
        
        # Emit signal to request data for new timeframe
        self.emitter.emit(
            Signals.TIMEFRAME_CHANGED,
            exchange=self.exchange,
            tab=self.window_tag,
            new_timeframe=new_timeframe,
        )
    
    def _toggle_auto_fit(self, sender, value):
        """Toggle automatic chart fitting."""
        self.auto_fit_enabled = value
        if value:
            self._fit_chart()
    
    def _fit_chart(self):
        """Fit chart axes to the data."""
        dpg.fit_axis_data(self.x_axis_tag)
        dpg.fit_axis_data(self.y_axis_tag)
        dpg.fit_axis_data(self.volume_y_axis_tag) 