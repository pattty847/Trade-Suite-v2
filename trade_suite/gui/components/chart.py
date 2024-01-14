import logging

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
from trade_suite.gui.utils import timeframe_to_seconds


class Chart:
    def __init__(self, parent, exchange, emitter: SignalEmitter, data: Data, task_manager: TaskManager, config_manager: ConfigManager) -> None:
        self.tag = dpg.generate_uuid()
        self.parent = parent # Primary Window's tag
        self.emitter = emitter # Signal Emitter object used to register and emit information
        self.data = data # CCXTWrapper used to fetch data for your account
        self.task_manager = task_manager # Asyncio task wrapper running in thread
        self.config_manager = config_manager 
        self.active_exchange = exchange
        self.exchange_settings = self.config_manager.get_setting(self.active_exchange) # else make settings
        
        self.candle_factory = CandleFactory(self.emitter, self.task_manager, self.data, self.exchange_settings)
        self.indicators = Indicators(self.emitter, self.exchange_settings)
        self.trading = Trading(self.emitter, self.data, self.config_manager, self.task_manager)
        self.orderbook = OrderBook(self.emitter, self.data, self.config_manager)

        # OHLCV data structure
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        self.timeframe_str = self.exchange_settings['last_timeframe'] if self.exchange_settings else '15m'
        self.timeframe_seconds = timeframe_to_seconds(self.timeframe_str)  # Timeframe for the candles in seconds
        self.last_candle_timestamp = None
        self.active_symbol = self.exchange_settings['last_symbol'] if self.exchange_settings else None
        
        
        self.setup_ui_elements()
        self.register_event_listeners()

    def setup_ui_elements(self):
        with dpg.tab(label=self.active_exchange.upper(), parent=self.parent):
            with dpg.child_window(menubar=True, tag=self.tag):
                self.setup_menus()
                self.setup_candlestick_chart()

    def setup_menus(self):
        with dpg.menu_bar():
            self.setup_exchange_menu()
            self.setup_settings_menu()
            self.trading.setup_trading_menu()
            self.indicators.create_indicators_menu()
            self.orderbook.setup_orderbook_menu()

    def setup_exchange_menu(self):
        with dpg.menu(label="Markets"):
            dpg.add_text('Symbols')
            dpg.add_listbox(
                items=self.data.exchange_list[self.active_exchange]['symbols'], 
                callback=lambda sender, symbol, user_data: self.emitter.emit(Signals.SYMBOL_CHANGED, new_symbol=symbol),
                num_items=8
            )
            
            dpg.add_text('Timeframe')
            dpg.add_listbox(
                items=self.data.exchange_list[self.active_exchange]['timeframes'],
                callback=lambda sender, timeframe, user_data: self.emitter.emit(Signals.TIMEFRAME_CHANGED, new_timeframe=timeframe),
                num_items=5
            )

    def setup_settings_menu(self):
        with dpg.menu(label="Settings"):
            dpg.add_text("Candle Width")
            dpg.add_slider_float(min_value=0.1, max_value=1, callback=lambda s, a, u: dpg.configure_item(self.candle_series, weight=a))
            dpg.add_menu_item(label="Stop All Streaming", callback=self.task_manager.stop_all_tasks)
                
    def setup_candlestick_chart(self):
        with dpg.group(horizontal=True):  # Use horizontal grouping to align elements side by side
            
            with dpg.group(width=dpg.get_viewport_width() * 0.7, height=-1, tag='charts_group'):  # This group will contain the charts, filling the available space
                                    
                with dpg.subplots(rows=2, columns=1, row_ratios=[0.7, 0.3], link_all_x=True):
                    # Candlestick Chart
                    with dpg.plot(label="Candlestick Chart", height=-1) as self.candlestick_plot:
                        dpg.add_plot_legend()
                        
                        # Belongs to: self.candlestick_plot
                        self.trading.trade_mode_drag_line_tag = dpg.add_drag_line(label='Order', show=False, color=[255, 0, 0, 255], vertical=False)
                        
                        self.candle_series_xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                        with dpg.plot_axis(dpg.mvYAxis, label="USD") as self.candle_series_yaxis:
                            # Ensure data is populated before adding series
                            self.candle_series = dpg.add_candle_series(
                                list(self.ohlcv['dates']),
                                list(self.ohlcv['opens']),
                                list(self.ohlcv['closes']),
                                list(self.ohlcv['lows']),
                                list(self.ohlcv['highs']),
                                time_unit=dpg.mvTimeUnit_Min,
                                label=f"{self.active_symbol}"
                            )
                            self.trading.candlestick_plot = self.candlestick_plot
                            self.indicators.candle_series_yaxis = self.candle_series_yaxis
                            
                        
                    # Volume Chart
                    with dpg.plot(label="Volume Chart", no_title=True, height=-1):
                        dpg.add_plot_legend()
                        self.volume_series_xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                        with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.volume_series_yaxis:
                            # Ensure data is populated before adding series
                            self.volume_series = dpg.add_line_series(
                                list(self.ohlcv['dates']),
                                list(self.ohlcv['volumes']),
                            )
            
            
            with dpg.group(width=300, tag='order_book_group'):
                self.orderbook.create_order_book_ui()
                

    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles, # first callback emitted when application starts (requests last chart user had)
            Signals.UPDATED_CANDLES: self.on_updated_candles,
            Signals.VIEWPORT_RESIZED: self.on_viewport_resize,
            Signals.TRADE_STAT_UPDATE: self.on_trade_stat_update,
            Signals.SYMBOL_CHANGED: self.on_symbol_change,
            Signals.TIMEFRAME_CHANGED: self.on_timeframe_change,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    
    def on_symbol_change(self, new_symbol: str):
        new_settings = {"last_symbol": new_symbol, "last_timeframe": self.timeframe_str}
        self.config_manager.update_setting(self.active_exchange, new_settings)
        
        self.active_symbol = new_symbol
        self.task_manager.start_stream(self.active_exchange, new_symbol, self.timeframe_str, cant_resample=False)
        
    def on_timeframe_change(self, new_timeframe: str):
        new_settings = {"last_symbol": self.active_symbol, "last_timeframe": new_timeframe}
        self.config_manager.update_setting(self.active_exchange, new_settings)
        
        self.candle_factory.resample_candle(new_timeframe, self.active_exchange, self.active_symbol)
        self.timeframe_str = new_timeframe
        

    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
            self.update_candle_chart()
            dpg.fit_axis_data(self.candle_series_xaxis)
            dpg.fit_axis_data(self.candle_series_yaxis)
            dpg.fit_axis_data(self.volume_series_xaxis)
            dpg.fit_axis_data(self.volume_series_yaxis)
            
            
    def on_new_trade(self, exchange, trade_data):
        pass
        
    def on_updated_candles(self, candles):
        self.ohlcv = candles
        self.update_candle_chart()


    def update_candle_chart(self):
        # Redraw the candle stick series (assuming the dataframe has changed)
        dpg.configure_item(self.candlestick_plot, label=f"{self.active_symbol} | {self.timeframe_str}")
        dpg.configure_item(
            self.candle_series,
            dates=self.ohlcv['dates'].tolist(),
            opens=self.ohlcv['opens'].tolist(),
            highs=self.ohlcv['highs'].tolist(),
            lows=self.ohlcv['lows'].tolist(),
            closes=self.ohlcv['closes'].tolist(),
        )
        dpg.configure_item(
            self.volume_series,
            x=self.ohlcv['dates'].tolist(),
            y=self.ohlcv['volumes'].tolist()
        )

        
    def on_trade_stat_update(self, symbol, stats):
        pass

    def on_viewport_resize(self, width, height):
        # Calculate new width for the charts and order book based on viewport size
        charts_width = width * 0.7
        order_book_width = width - charts_width  # Subtract the chart width from the total to get the order book width
        
        # Update the width of the groups
        dpg.configure_item("charts_group", width=charts_width)
        dpg.configure_item("order_book_group", width=order_book_width)