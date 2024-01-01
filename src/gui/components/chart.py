import logging

import dearpygui.dearpygui as dpg
import pandas as pd

from src.config import ConfigManager
from src.data.data_source import Data
from src.gui import tags
from src.gui.components.orderbook import OrderBook
from src.gui.components.trading import Orders
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager
from src.gui.utils import str_timeframe_to_minutes


class Chart:
    def __init__(self, exchange, emitter: SignalEmitter, data: Data, task_manager: TaskManager, config_manager: ConfigManager) -> None:
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        self.config_manager = config_manager
        self.active_exchange = exchange
        self.exchange_settings = self.config_manager.get_setting(self.active_exchange) # else make settings
        
        
        # UI elements will need to register for emitted signals
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        self.emitter.register(Signals.NEW_CANDLES, self.on_new_candles)
        self.emitter.register(Signals.VIEWPORT_RESIZED, self.on_viewport_resize)
        self.emitter.register(Signals.TRADE_STAT_UPDATE, self.on_trade_stat_update)
        self.emitter.register(Signals.SYMBOL_CHANGED, self.on_symbol_change)
        self.emitter.register(Signals.TIMEFRAME_CHANGED, self.on_timeframe_change)


        # OHLCV data structure
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        self.timeframe_str = self.exchange_settings['last_timeframe'] if self.exchange_settings else '15m'
        self.timeframe_seconds = str_timeframe_to_minutes(self.timeframe_str)  # Timeframe for the candles in seconds
        self.last_candle_timestamp = None
        self.active_symbol = self.exchange_settings['last_symbol'] if self.exchange_settings else None
        
        self.in_trade_mode = False

        # UI setup
        with dpg.child_window(menubar=True, tag=self.active_exchange, parent=tags.PRIMARY_WINDOW):
            with dpg.menu_bar():
                with dpg.menu(label=self.active_exchange.upper()):

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
                    
                
                    with dpg.menu(label="Settings"):
                        dpg.add_text("Candle Width")
                        dpg.add_slider_float(min_value=0.1, max_value=1, callback=lambda s, a, u: dpg.configure_item(self.candle_series, weight=a))
                        dpg.add_menu_item(label="Stop All Streaming", callback=self.task_manager.stop_all_tasks)
            
                with dpg.menu(label="Trading Actions"):
                    dpg.add_menu_item(label="Toggle Trade Line Visibility", callback=self.place_trade_callback)
                    dpg.add_menu_item(label="Execute Trade at Line Position", callback=self.open_order_window)

                    # Adding a tooltip to the menu to give users more information
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Use these options to manage trading on the chart.\n"
                                    "'Toggle Trade Line Visibility' will show or hide the line where you can place your trade.\n"
                                    "'Execute Trade at Line Position' will open the trade window at the line's current position.")

                
            with dpg.group(horizontal=True):  # Use horizontal grouping to align elements side by side
                
                with dpg.group(tag='charts_group', width=dpg.get_viewport_width() * 0.7, height=-1):  # This group will contain the charts, filling the available space
                                        
                    with dpg.subplots(rows=2, columns=1, row_ratios=[0.7, 0.3], link_all_x=True):
                        # Candlestick Chart
                        with dpg.plot(label="Candlestick Chart", height=-1) as self.candlestick_plot:
                            dpg.add_plot_legend()
                            
                            dpg.add_drag_line(label='Order', tag="trade_drag_line", show=False, color=[255, 0, 0, 255], vertical=False)
                            
                            self.candle_series_xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                            with dpg.plot_axis(dpg.mvYAxis, label="USD") as self.candle_series_yaxis:
                                # Ensure data is populated before adding series
                                self.candle_series = dpg.add_candle_series(
                                    list(self.ohlcv['dates']),
                                    list(self.ohlcv['opens']),
                                    list(self.ohlcv['closes']),
                                    list(self.ohlcv['lows']),
                                    list(self.ohlcv['highs']),
                                    time_unit=dpg.mvTimeUnit_Min
                                )
                                
                            
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
                    self.orderbook = OrderBook(self.emitter, self.data, self.config_manager)
                    # self.orders = Orders(self.emitter, self.data, self.config_manager, self.task_manager)

    def place_trade_callback(self):
        self.in_trade_mode = not self.in_trade_mode
        if self.in_trade_mode: 
            dpg.configure_item('trade_drag_line', show=True, default_value=self.ohlcv['closes'].tolist()[-1])
        else: 
            dpg.configure_item('trade_drag_line', show=False)
    
    def open_order_window(self):
        price = dpg.get_value('trade_drag_line')
        
        def on_close():
            dpg.delete_item('order_window', children_only=True)
            dpg.delete_item('order_window')

        def apply_percentage(sender, app_data, user_data):
            percentage = user_data / 100
            take_profit_price = price * (1 + percentage)
            dpg.set_value("profit_percentage_input", take_profit_price)

        if not dpg.does_item_exist("order_window"):
            width, height = 400, 300
            with dpg.window(
                label="Place Order", 
                modal=True, 
                on_close=on_close,
                width=width, height=height,
                pos=(dpg.get_viewport_width() / 2 - width/2, dpg.get_viewport_height() / 2 - height/2)):
                dpg.add_input_float(label="Price", default_value=price, tag="Price")
                dpg.add_input_float(label="Stop Loss", tag="Stop Loss")
                dpg.add_input_float(label="Take Profit", tag="profit_percentage_input")
                dpg.add_input_int(label="Size", tag="Size")

                # Quick buttons for setting take profit percentage
                with dpg.group(horizontal=True):
                    for percent in [2, 3, 5]:
                        dpg.add_button(label=f"{percent}%", callback=apply_percentage, user_data=percent)

                dpg.add_button(label="Place Order")
    
    def on_symbol_change(self, new_symbol: str):
        new_settings = {"last_symbol": new_symbol, "last_timeframe": self.timeframe_str}
        self.config_manager.update_setting(self.active_exchange, new_settings)
        
        self.active_symbol = new_symbol
        self.task_manager.start_stream(self.active_exchange, new_symbol, self.timeframe_str, cant_resample=False)
        
    def on_timeframe_change(self, new_timeframe: str):
        new_settings = {"last_symbol": self.active_symbol, "last_timeframe": new_timeframe}
        self.config_manager.update_setting(self.active_exchange, new_settings)
        
        timeframe_in_minutes = str_timeframe_to_minutes(new_timeframe)

        # if new timeframe > old timeframe
        if timeframe_in_minutes > self.timeframe_seconds:
            self.ohlcv = self.data.agg.resample_data(self.ohlcv, new_timeframe)
            self.update_candle_chart()
        else:
            self.task_manager.start_stream(self.active_exchange, self.active_symbol, new_timeframe, cant_resample=True)

        self.timeframe_str = new_timeframe
        self.timeframe_seconds = timeframe_in_minutes
        

    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
            self.update_candle_chart()
            dpg.fit_axis_data(self.candle_series_xaxis)
            dpg.fit_axis_data(self.candle_series_yaxis)
            dpg.fit_axis_data(self.volume_series_xaxis)
            dpg.fit_axis_data(self.volume_series_yaxis)
            
            
    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']

        if self.last_candle_timestamp is None:
            self.last_candle_timestamp = timestamp - (timestamp % self.timeframe_seconds)

        if timestamp >= self.last_candle_timestamp + self.timeframe_seconds:
            # Start a new candle
            new_candle = {
                'dates': self.last_candle_timestamp + self.timeframe_seconds,
                'opens': price,
                'highs': price,
                'lows': price,
                'closes': price,
                'volumes': volume
            }
            # Convert the new candle dictionary to a DataFrame before concatenating
            new_candle_df = pd.DataFrame([new_candle])
            self.ohlcv = pd.concat([self.ohlcv, new_candle_df], ignore_index=True)
            self.last_candle_timestamp += self.timeframe_seconds
        else:
            # Update the current candle
            self.ohlcv.at[self.ohlcv.index[-1], 'highs'] = max(self.ohlcv.at[self.ohlcv.index[-1], 'highs'], price)
            self.ohlcv.at[self.ohlcv.index[-1], 'lows'] = min(self.ohlcv.at[self.ohlcv.index[-1], 'lows'], price)
            self.ohlcv.at[self.ohlcv.index[-1], 'closes'] = price
            self.ohlcv.at[self.ohlcv.index[-1], 'volumes'] += volume
        
        if volume >= 0.2:
            dpg.draw_circle([timestamp, price], volume, parent=self.candlestick_plot)

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