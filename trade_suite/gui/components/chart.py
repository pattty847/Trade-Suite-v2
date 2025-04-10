import asyncio
import logging
from typing import Dict, List

import dearpygui.dearpygui as dpg
import pandas as pd
from trade_suite.config import ConfigManager

from trade_suite.data.candle_factory import CandleFactory
from trade_suite.data.data_source import Data
from trade_suite.gui.components.indicators import Indicators
from trade_suite.gui.components.orderbook import OrderBook
from trade_suite.gui.components.trading import Trading
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import create_timed_popup, searcher
from trade_suite.data.state import StateManager
from trade_suite.gui.components.test_ob import TestOB


class Chart:
    def __init__(self, parent, exchange, emitter, data, task_manager, config_manager, state_manager):
        self._initialize_attributes(
            parent, exchange, emitter, data, task_manager, config_manager, state_manager
        )
        self._initialize_components()
        self._setup_ui_elements()
        self._register_event_listeners()
        self._start_data_stream()

    def _initialize_attributes(
        self, parent, exchange, emitter, data, task_manager, config_manager, state_manager
    ):
        self.tab_id = dpg.generate_uuid()
        self.parent: str = parent
        self.emitter: SignalEmitter = emitter
        self.data: Data = data
        self.task_manager: TaskManager = task_manager
        self.config_manager: ConfigManager = config_manager
        self.state_manager: StateManager = state_manager
        self.exchange: str = exchange
        self.exchange_settings = self.config_manager.get_setting(exchange) or {}
        
        # Initialize basic chart data structure
        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        
        # UI state
        self.auto_fit_enabled = True
        
        # Symbol and timeframe
        self.timeframe = self._get_default_timeframe()
        self.symbol = self._get_default_symbol()

    def _initialize_components(self):
        # Initialize the candle factory (which now uses ChartProcessor)
        self.candle_factory = CandleFactory(
            self.exchange,
            self.tab_id,
            self.emitter,
            self.task_manager,
            self.data,
            self.exchange_settings,
            self.timeframe,
        )
        
        # All of these classes need listeners for the updated candles
        self.indicators = Indicators(
            self.tab_id, 
            self.exchange, 
            self.emitter, 
            self.exchange_settings
        )
        self.trading = Trading(
            self.tab_id,
            self.exchange,
            self.emitter,
            self.data,
            self.config_manager,
            self.task_manager,
        )
        self.orderbook = OrderBook(
            self.tab_id,
            self.exchange,
            self.symbol,
            self.emitter,
            self.data,
            self.config_manager,
        )
        self.test_ob = TestOB(
            self.tab_id, 
            self.data, 
            self.emitter
        )

    def _start_data_stream(self):
        if self.exchange:
            self.task_manager.start_stream_for_chart(
                self.tab_id,
                exchange=self.exchange,
                symbol=self.symbol,
                timeframe=self.timeframe,
            )

    def _setup_ui_elements(self):
        with dpg.tab(label=self.exchange.upper(), tag=self.tab_id, parent=self.parent):
            with dpg.child_window(menubar=True, no_scrollbar=True):
                self._setup_menus()
                
                # Horizontally align the Chart and Orderbook
                with dpg.group(horizontal=True):
                    
                    # Chart group
                    with dpg.group(
                        width=dpg.get_viewport_width() * 0.7,
                        height=-1,
                        tag=self.orderbook.charts_group,
                    ):

                        self._setup_candlestick_chart()
                
                    # Order book group
                    with dpg.group(width=-1, tag=self.orderbook.order_book_group):
                        self.orderbook.draw_orderbook_plot()
                        self.test_ob.launch()
                    
                
            with dpg.child_window(width=-1, height=200) as self.trading_window_id: 
                self.trading.build_trading_panel()

    def _setup_menus(self):
        with dpg.menu_bar():
            self._setup_exchange_menu()
            self.trading.setup_trading_menu()
            self.indicators.create_indicators_menu()
            self.orderbook.setup_orderbook_menu()
            dpg.add_menu_item(label="Test Orderbook", callback=self.test_ob.launch)
            self._setup_settings_menu()

    def _register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self._on_new_trade,
            Signals.NEW_CANDLES: self._on_new_candles,
            Signals.UPDATED_CANDLES: self._on_updated_candles,
            Signals.VIEWPORT_RESIZED: self._on_viewport_resize,
            Signals.TRADE_STAT_UPDATE: self._on_trade_stat_update,
            Signals.SYMBOL_CHANGED: self._on_symbol_change,
            Signals.TIMEFRAME_CHANGED: self._on_timeframe_change,
            Signals.ORDERBOOK_VISIBILITY_CHANGED: self._on_orderbook_visibility_changed,
        }

        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def _setup_exchange_menu(self):
        with dpg.menu(label="Markets"):
            dpg.add_text("Symbols")
            # Search box for symbols
            input_tag = dpg.add_input_text(label="Search")
            symbols_list = dpg.add_listbox(
                items=self.data.exchange_list[self.exchange].symbols,
                default_value=self.symbol,
                callback=lambda sender, symbol, user_data: self.emitter.emit(
                    Signals.SYMBOL_CHANGED,
                    exchange=self.exchange,
                    tab=self.tab_id,
                    new_symbol=symbol,
                ),
                num_items=8,
            )
            dpg.set_item_callback(
                input_tag,
                callback=lambda: searcher(
                    input_tag,
                    symbols_list,
                    self.data.exchange_list[self.exchange].symbols,
                ),
            )

            dpg.add_text("Timeframe")
            dpg.add_listbox(
                items=list(self.data.exchange_list[self.exchange].timeframes.keys()),
                default_value=self.timeframe,
                callback=lambda sender, timeframe, user_data: self.emitter.emit(
                    Signals.TIMEFRAME_CHANGED,
                    exchange=self.exchange,
                    tab=self.tab_id,
                    new_timeframe=timeframe,
                ),
                num_items=5,
            )

    def _setup_settings_menu(self):
        with dpg.menu(label="Settings"):
            dpg.add_slider_float(
                label="Candle Width",
                min_value=0.1,
                max_value=1,
                callback=lambda s, a, u: dpg.configure_item(
                    self.candle_series, weight=a
                ),
            )
            
            dpg.add_slider_int(
                label="Trades/Candle Update",
                default_value=5,
                min_value=1,
                max_value=50,
                callback=self.candle_factory.set_trade_batch
            )
            
            dpg.add_menu_item(
                label="Stop All Streaming", callback=self.task_manager.stop_all_tasks
            )

    def _setup_candlestick_chart(self):
        with dpg.subplots(
            rows=2,
            columns=1,
            row_ratios=[0.8, 0.2],
            link_all_x=True,
            label=f"{self.symbol} | {self.timeframe}",
            width=-1,
        ) as self.subplots:

            # Candlestick Chart
            with dpg.plot() as self.candlestick_plot:
                dpg.add_plot_legend()

                # Belongs to: self.candlestick_plot
                self.trading.trade_mode_drag_line_tag = dpg.add_drag_line(
                    label="Order",
                    show=False,
                    color=[255, 255, 255, 255],
                    vertical=False,
                    callback=self.trading.set_order_line_price,
                )

                self.candle_series_xaxis = dpg.add_plot_axis(
                    dpg.mvXAxis,
                    time=True,
                    no_tick_marks=True,
                    no_tick_labels=True,
                )

                with dpg.plot_axis(
                    dpg.mvYAxis, label="USD"
                ) as self.candle_series_yaxis:
                    # Ensure data is populated before adding series
                    self.candle_series = dpg.add_candle_series(
                        list(self.ohlcv["dates"]),
                        list(self.ohlcv["opens"]),
                        list(self.ohlcv["closes"]),
                        list(self.ohlcv["lows"]),
                        list(self.ohlcv["highs"]),
                        time_unit=dpg.mvTimeUnit_Min,
                        label=f"{self.symbol}",
                    )

                    self.trading.candlestick_plot = self.candlestick_plot
                    self.indicators.candle_series_yaxis = (
                        self.candle_series_yaxis
                    )

            # Volume Chart
            with dpg.plot(label="Volume Chart", no_title=True):
                dpg.add_plot_legend()
                self.volume_series_xaxis = dpg.add_plot_axis(
                    dpg.mvXAxis, time=True
                )
                with dpg.plot_axis(
                    dpg.mvYAxis, label="Volume"
                ) as self.volume_series_yaxis:
                    # Ensure data is populated before adding series
                    self.volume_series = dpg.add_bar_series(
                        list(self.ohlcv["dates"]),
                        list(self.ohlcv["volumes"]),
                        weight=100,
                    )

    def _update_chart_settings_and_stream(
        self, exchange, settings, tab, symbol, timeframe
    ):
        # Update UI labels
        dpg.configure_item(
            self.subplots, label=f"{symbol} | {timeframe}"
        )
        dpg.configure_item(
            self.candle_series, label=f"{symbol} | {timeframe}"
        )
        
        # Save settings
        self.config_manager.update_setting(exchange, settings)
        
        # Start streaming data
        self.task_manager.start_stream_for_chart(tab, exchange, symbol, timeframe)

    def _on_symbol_change(self, exchange, tab, new_symbol: str):
        if tab == self.tab_id:
            logging.info(
                f"{exchange}: Symbol change - from {self.symbol} to {new_symbol}"
            )

            # Update settings
            new_settings = {
                "last_symbol": new_symbol,
                "last_timeframe": self.timeframe,
            }
            
            # Update chart settings and restart stream
            self._update_chart_settings_and_stream(
                exchange, new_settings, tab, new_symbol, self.timeframe
            )
            
            # Update local state
            self.symbol = new_symbol

    def _on_timeframe_change(self, exchange, tab, new_timeframe: str):
        if tab == self.tab_id:
            logging.info(
                f"{exchange}: Timeframe change - from {self.timeframe} to {new_timeframe}"
            )

            # Update settings
            new_settings = {
                "last_symbol": self.symbol,
                "last_timeframe": new_timeframe,
            }
            
            # Try to resample with the candle factory
            can_resample = self.candle_factory.try_resample(new_timeframe, self.exchange)

            # If resampling couldn't be performed, update the chart settings and start a new data stream
            if not can_resample:
                self._update_chart_settings_and_stream(
                    exchange, new_settings, tab, self.symbol, new_timeframe
                )
            else:
                # If resampling was successful, update the subplot label to the new timeframe
                dpg.configure_item(
                    self.subplots, label=f"{self.symbol} | {new_timeframe}"
                )
                
            # Update the timeframe attribute
            self.timeframe = new_timeframe

    # Called anytime this class receives new candles
    def _on_new_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab_id:
            # Update the local DataFrame for UI rendering
            self.ohlcv = candles
            if "dates" in self.ohlcv.columns and self.ohlcv["dates"].max() > 1e12:
                self.ohlcv['dates'] = self.ohlcv['dates'] / 1000
                
            # Update the chart UI
            self._update_candle_chart()
            
            # Auto-fit axes
            self._fit_axes()

    def _on_new_trade(self, tab, exchange, trade_data):
        if tab != self.tab_id:
            return
        
        # CandleFactory/ChartProcessor handle the data processing
        # This method only needs to handle the UI aspects
        
        # Display the trade on the chart as a circle
        timestamp = trade_data["timestamp"] // 1000  # Convert ms to seconds
        price = trade_data["price"]
        volume = trade_data["amount"]
        
        # Adjust for visual placement in the chart
        half_interval = 5 * 60 * 0.25 / 2
        adjusted_timestamp = timestamp - half_interval
        
        # Add circle to represent the trade
        dpg.draw_circle(
            center=[adjusted_timestamp, price],
            radius=volume * 10,
            color=[255, 255, 255, 255],
            thickness=1,
            parent=self.candlestick_plot,
        )

    def _on_updated_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab_id:
            # Update the local DataFrame for UI rendering
            self.ohlcv = candles
            
            # Update the chart UI
            self._update_candle_chart()

    def _update_candle_chart(self):
        # Update the chart UI with the current ohlcv data
        dpg.configure_item(
            self.candle_series,
            dates=self.ohlcv["dates"].tolist(),
            opens=self.ohlcv["opens"].tolist(),
            highs=self.ohlcv["highs"].tolist(),
            lows=self.ohlcv["lows"].tolist(),
            closes=self.ohlcv["closes"].tolist(),
        )
        dpg.configure_item(
            self.volume_series,
            x=self.ohlcv["dates"].tolist(),
            y=self.ohlcv["volumes"].tolist(),
        )

    def _fit_axes(self):
        """Fit all chart axes to the data"""
        dpg.fit_axis_data(self.candle_series_xaxis)
        dpg.fit_axis_data(self.candle_series_yaxis)
        dpg.fit_axis_data(self.volume_series_xaxis)
        dpg.fit_axis_data(self.volume_series_yaxis)

    def _on_trade_stat_update(self, symbol, stats):
        # Placeholder for future implementation
        pass

    def _on_viewport_resize(self, width, height):
        # Calculate new width for the charts and order book based on viewport size
        charts_width = width * 0.7

        # Update the width of the groups
        dpg.configure_item(self.orderbook.charts_group, width=charts_width)
        dpg.configure_item(self.orderbook.order_book_group, width=-1)

    def _get_default_timeframe(self):
        return (
            self.exchange_settings.get("last_timeframe")
            or list(self.data.exchange_list[self.exchange].timeframes.keys())[1]
        )

    def _get_default_symbol(self):
        return (
            self.exchange_settings.get("last_symbol")
            or self._get_default_bitcoin_market()
        )

    def _get_default_bitcoin_market(self):
        symbols = self.data.exchange_list[self.exchange].symbols
        return next(
            (symbol for symbol in symbols if symbol in ["BTC/USD", "BTC/USDT"]), None
        )

    def _on_orderbook_visibility_changed(self, tab, exchange, symbol, visible):
        """Handle orderbook visibility changes and manage the corresponding data stream."""
        if tab != self.tab_id:
            return
            
        stream_id = f"orderbook_{exchange}_{symbol}_{tab}"
        
        if visible:
            # Start or restart the orderbook stream when orderbook is shown
            if not self.task_manager.is_task_running(stream_id):
                logging.info(f"Starting orderbook stream for {symbol} on {tab}")
                self.task_manager.start_task(
                    stream_id,
                    self.data.watch_orderbook(tab, exchange, symbol)
                )
        else:
            # Stop the orderbook stream when orderbook is hidden to save resources
            if self.task_manager.is_task_running(stream_id):
                logging.info(f"Stopping orderbook stream for {symbol} on {tab}")
                self.task_manager.stop_task(stream_id)
