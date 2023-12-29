import logging
import dearpygui.dearpygui as dpg
import pandas as pd
from src.config import ConfigManager

from src.data.data_source import Data
from src.gui import tags
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager


class Chart:
    def __init__(self, exchange, emitter: SignalEmitter, data: Data, task_manager: TaskManager, config_manager: ConfigManager) -> None:
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        self.config_manager = config_manager
        self.exchange = exchange
        
        self.exchange_settings = self.config_manager.get_setting(self.exchange)
        
        # Order book variables
        self.order_book_levels = 100
        self.tick_size = 10
        self.aggregated_order_book = True
        
        # UI elements will need to register for emitted signals
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        self.emitter.register(Signals.NEW_CANDLES, self.on_new_candles)
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)
        self.emitter.register(Signals.VIEWPORT_RESIZED, self.on_viewport_resize)
        self.emitter.register(Signals.TRADE_STAT_UPDATE, self.on_trade_stat_update)
        self.emitter.register(Signals.SYMBOL_CHANGED, self.on_symbol_change)
        self.emitter.register(Signals.TIMEFRAME_CHANGED, self.on_timeframe_change)


        # OHLCV data structure
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        self.timeframe_str = self.exchange_settings['last_timeframe'] if self.exchange_settings else '15m'
        self.timeframe_seconds = self.str_timeframe_to_minutes(self.timeframe_str)  # Timeframe for the candles in seconds
        self.last_candle_timestamp = None
        self.active_symbol = self.exchange_settings['last_symbol'] if self.exchange_settings else None
        
        # UI setup
        with dpg.child_window(menubar=True, tag=self.exchange, parent=tags.PRIMARY_WINDOW):
            with dpg.menu_bar():
                with dpg.menu(label=self.exchange.upper()):

                    dpg.add_text('Symbols')
                    dpg.add_listbox(
                        items=self.data.exchange_list[self.exchange]['symbols'], 
                        callback=lambda sender, symbol, user_data: self.emitter.emit(Signals.SYMBOL_CHANGED, new_symbol=symbol),
                        num_items=8
                    )
                    
                    dpg.add_text('Timeframe')
                    dpg.add_listbox(
                        items=self.data.exchange_list[self.exchange]['timeframes'],
                        callback=lambda sender, timeframe, user_data: self.emitter.emit(Signals.TIMEFRAME_CHANGED, new_timeframe=timeframe),
                        num_items=5
                    )
                    
                
                    with dpg.menu(label="Testing"):
                        dpg.add_slider_float(min_value=0.1, max_value=5, callback=lambda s, a, u: dpg.configure_item(self.candle_series, weight=a))
                        dpg.add_menu_item(label="Stop Async Tasks", callback=self.task_manager.stop_all_tasks)
            
                
            with dpg.group(horizontal=True):  # Use horizontal grouping to align elements side by side
                with dpg.group(tag='charts_group', width=dpg.get_viewport_width() * 0.7, height=-1):  # This group will contain the charts, filling the available space
                    with dpg.subplots(rows=2, columns=1, row_ratios=[0.7, 0.3], link_all_x=True):
                        
                        # Candlestick Chart
                        with dpg.plot(label="Candlestick Chart", no_title=True, height=-1):
                            dpg.add_plot_legend()
                            xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                            with dpg.plot_axis(dpg.mvYAxis, label="USD"):
                                # Ensure data is populated before adding series
                                self.candle_series = dpg.add_candle_series(
                                    list(self.ohlcv['dates']),
                                    list(self.ohlcv['opens']),
                                    list(self.ohlcv['closes']),
                                    list(self.ohlcv['lows']),
                                    list(self.ohlcv['highs']),
                                    time_unit=dpg.mvTimeUnit_Min
                                )
                            dpg.fit_axis_data(xaxis)
                            
                        # Volume Chart
                        with dpg.plot(label="Volume Chart", no_title=True, height=-1):
                            dpg.add_plot_legend()
                            xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                            with dpg.plot_axis(dpg.mvYAxis, label="Volume") as vol_yaxis:
                                # Ensure data is populated before adding series
                                self.volume_series = dpg.add_line_series(
                                    list(self.ohlcv['dates']),
                                    list(self.ohlcv['volumes']),
                                )
                            dpg.set_axis_limits_auto(axis=vol_yaxis)
                            dpg.fit_axis_data(xaxis)
                            
                with dpg.group(width=300, tag='order_book_group'):  # This group will contain the order book plot
                    dpg.add_checkbox(label="Aggregate", default_value=self.aggregated_order_book, callback=self.toggle_aggregated_order_book)
                    # Tick slider needs to be tailored to symbol precision
                    dpg.add_slider_int(label="Levels", default_value=100, min_value=5, max_value=1000, callback=lambda s, a, u: self.set_ob_levels(a))
                    with dpg.plot(label="Orderbook", no_title=True, height=-1):
                            dpg.add_plot_legend()
                            self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
                            with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                                # Ensure data is populated before adding series
                                self.bids_tag = dpg.add_line_series(
                                    [], []
                                )
                                self.asks_tag = dpg.add_line_series(
                                    [], []
                                )
                            dpg.fit_axis_data(xaxis)
                            
    
    # This needs to be abstracted more
    # The TaskManager is async loop running in thread as daemon, needed for non-blocking UI
    def start_stream(self, symbol, timeframe, cant_resample: bool):

        if cant_resample:
            if f"trades_{symbol}" in self.task_manager.tasks:
                self.task_manager.stop_task(f"trades_{symbol}")

        # We need to fetch the candles (wait for them), this emits 'Signals.NEW_CANDLES', func 'on_new_candles' should set them    
        self.task_manager.run_task_until_complete(self.data.fetch_candles([self.exchange], [symbol], [timeframe], write_to_db=False))
        
        if f"trades_{symbol}" not in self.task_manager.tasks:
            # We start the stream (ticks), this emits 'Signals.NEW_TRADE', func 'on_new_trade' handles building of candles
            self.task_manager.start_task(
                f'trades_{symbol}', 
                # TODO: Add 'exchange' parameter to 'stream_trades'
                coro=self.data.stream_trades(
                    symbols=[symbol], 
                    track_stats=True
                )
            )
        
        if f"orderbook_{symbol}" not in self.task_manager.tasks:
            self.task_manager.start_task(
                f'orderbook_{symbol}', 
                # TODO: Add 'exchange' parameter to 'stream_trades'
                coro=self.data.stream_order_book(
                    symbols=[symbol], 
                )
            )
     
    def on_symbol_change(self, new_symbol: str):
        new_settings = {"last_symbol": new_symbol, "last_timeframe": self.timeframe_str}
        self.config_manager.update_setting(self.exchange, new_settings)
        
        self.active_symbol = new_symbol
        self.start_stream(new_symbol, self.timeframe_str, cant_resample=False)
        
    def on_timeframe_change(self, new_timeframe: str):
        new_settings = {"last_symbol": self.active_symbol, "last_timeframe": new_timeframe}
        self.config_manager.update_setting(self.exchange, new_settings)
        
        timeframe_in_minutes = self.str_timeframe_to_minutes(new_timeframe)

        # if new timeframe > old timeframe
        if timeframe_in_minutes > self.timeframe_seconds:
            self.resample_data(new_timeframe)
        else:
            self.start_stream(self.active_symbol, new_timeframe, cant_resample=True)

        self.timeframe_str = new_timeframe
        self.timeframe_seconds = timeframe_in_minutes

    def str_timeframe_to_minutes(self, timeframe_str):
        # Extracts the numerical value and unit from the timeframe string
        numeric_part = int(timeframe_str[:-1])
        unit = timeframe_str[-1]

        if unit == 'm':
            return numeric_part * 60
        elif unit == 'h':
            return numeric_part * 60 * 60
        elif unit == 'd':
            return numeric_part * 60 * 60 * 24
        else:
            raise ValueError("Invalid timeframe format")

    def resample_data(self, timeframe_str):
        temp_ohlcv = self.ohlcv.copy()
        temp_ohlcv['dates'] = pd.to_datetime(temp_ohlcv['dates'], unit='s')
        temp_ohlcv.set_index('dates', inplace=True)

        if timeframe_str.endswith('m'):
            timeframe_str = timeframe_str.replace('m', 'T')
        resampled_ohlcv = self.perform_resampling(temp_ohlcv, timeframe_str)

        self.ohlcv = resampled_ohlcv
        self.update_candle_chart()

    def perform_resampling(self, data, timeframe):
        # Perform the actual resampling
        resampled_ohlcv = data.resample(timeframe).agg({
            'opens': 'first',
            'highs': 'max',
            'lows': 'min',
            'closes': 'last',
            'volumes': 'sum'
        }).dropna().reset_index()

        resampled_ohlcv['dates'] = resampled_ohlcv['dates'].view('int64') // 1e9
        return resampled_ohlcv.reset_index(drop=True)

    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
            self.update_candle_chart()
            
            
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

        self.update_candle_chart()


    def update_candle_chart(self):
        # Redraw the candle stick series (assuming the dataframe has changed)
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

    def on_order_book_update(self, exchange, orderbook):
        bids_df, ask_df, price_column = self.data.agg.on_order_book_update(exchange, orderbook, self.tick_size, self.aggregated_order_book, self.order_book_levels)
        self.update_order_book(bids_df, ask_df, price_column)
    
    def update_order_book(self, bids_df, asks_df, price_column):
        dpg.configure_item(self.bids_tag, x=bids_df[price_column].tolist(), y=bids_df['cumulative_quantity'].tolist())
        dpg.configure_item(self.asks_tag, x=asks_df[price_column].tolist(), y=asks_df['cumulative_quantity'].tolist())
        
        # Find the midpoint
        worst_bid_price = bids_df[price_column].min()
        worst_ask_price = asks_df[price_column].max()
        worst_bid_size = bids_df['cumulative_quantity'].min()
        worst_ask_size = asks_df['cumulative_quantity'].max()

        # Update the x-axis limits
        dpg.set_axis_limits(axis=self.ob_xaxis, ymin=worst_bid_price, ymax=worst_ask_price)
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=worst_bid_size, ymax=worst_ask_size)
        
    def on_trade_stat_update(self, symbol, stats):
        pass

    def on_viewport_resize(self, width, height):
        # Calculate new width for the charts and order book based on viewport size
        charts_width = width * 0.7
        order_book_width = width - charts_width  # Subtract the chart width from the total to get the order book width
        
        # Update the width of the groups
        dpg.configure_item("charts_group", width=charts_width)
        dpg.configure_item("order_book_group", width=order_book_width)
        
    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book
                            
    def set_ob_levels(self, levels):
        self.order_book_levels = levels