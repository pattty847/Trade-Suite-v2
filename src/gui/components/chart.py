import dearpygui.dearpygui as dpg
import numpy as np
import pandas as pd

from collections import deque

from src.data.data_source import Data
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager

class Chart:
    def __init__(self, emitter: SignalEmitter, data: Data, task_manager: TaskManager) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        
        # Figure out base values for these
        self.active_stream = None
        self.active_timeframe = None
        self.ob_levels = 100
        self.tick_size = 10
        self.aggregated_order_book = True
        # UI elements will need to register for emitted signals
        
        # When we receive a trade after streaming symbol(s) on an exchange(s) we can subscribe to the events.
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        self.emitter.register(Signals.NEW_CANDLES, self.on_new_candles)
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)
        self.emitter.register(Signals.VIEWPORT_RESIZED, self.on_viewport_resize)
        self.emitter.register(Signals.TRADE_STAT_UPDATE, self.on_trade_stat_update)

        
        with dpg.child_window(menubar=True):
            with dpg.menu_bar():
                with dpg.menu(label="CoinbasePro"):

                    dpg.add_text('Symbols')
                    dpg.add_listbox(
                        items=self.data.exchange_list['coinbasepro']['symbols'], 
                        callback=lambda sender, symbol, user_data: self.start_stream(symbol),
                        num_items=8
                    )
                    
                    
                    dpg.add_text('Timeframe')
                    dpg.add_listbox(
                        items=self.data.exchange_list['coinbasepro']['timeframes'],
                        callback=lambda sender, timeframe, user_data: self.resample_chart(timeframe),
                        num_items=5
                    )
                    
                
                    with dpg.menu(label="Testing"):
                        dpg.add_slider_float(min_value=0.1, max_value=5, callback=lambda s, a, u: dpg.configure_item(self.candle_series, weight=a))
                        dpg.add_menu_item(label="Stop Async Tasks", callback=self.task_manager.stop_all_tasks)
            

            max_len = 10000
            # OHLCV data structure
            self.ohlcv = {
                'dates': deque(maxlen=max_len),
                'opens': deque(maxlen=max_len),
                'highs': deque(maxlen=max_len),
                'lows': deque(maxlen=max_len),
                'closes': deque(maxlen=max_len),
                'volumes': deque(maxlen=max_len)
            }
            self.timeframe = 300  # Timeframe for the candles in seconds
            self.last_candle_timestamp = None
                
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
                    dpg.add_checkbox(label="Aggregate", callback=self.toggle_aggregated_order_book)
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
                            
    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book
                            
    def set_ob_levels(self, levels):
        self.ob_levels = levels
                        
    def start_stream(self, symbol):
        self.task_manager.stop_all_tasks()
        
        # We need to fetch the candles (wait for them), this emits 'Signals.NEW_CANDLES', func 'on_new_candles' should set them    
        self.task_manager.run_task_until_complete(self.data.fetch_candles(['coinbasepro'], [symbol], ['5m'], write_to_db=False))
        
        # We start the stream (ticks), this emits 'Signals.NEW_TRADE', func 'on_new_trade' handles building of candles
        self.task_manager.start_task(
            f'stream_{symbol}_{self.timeframe}', 
            # TODO: Add 'exchange' parameter to 'stream_trades'
            coro=self.data.stream_trades(
                symbols=[symbol], 
                track_stats=True
            )
        )
        
        self.task_manager.start_task(
            f'stream_ob_{symbol}', 
            # TODO: Add 'exchange' parameter to 'stream_trades'
            coro=self.data.stream_order_book(
                symbols=[symbol], 
            )
        )
        
    def resample_chart(self, resampled_timeframe: str):
        # Check if there exists candles (self.ohlcv) to resample
        # Can we already resample the current timeframe into the new timeframe?
        # If not, out of the timeframes the exchange offers (self.data.exchange_list[exchange_id]['timeframes']), 
        # what's the best timeframe fetch so we can resample to the new timeframe?
        # Fetch the new candles need to resample
        # Resample candles self.ohlcv
        # Update the chart, and the on_new_trade function
        # update the chart's time_unit
        pass

    def on_new_candles(self, candles):
        # Directly check if candles is a DataFrame
        if isinstance(candles, pd.DataFrame):
            self.update_chart_from_dataframe(candles)
        else:
            # Assuming candles is a dict with the required structure
            for exchange_name, values in candles.items():
                for key, ohlcv_df in values.items():
                    symbol, timeframe = key.split("-")
                    print(f"{exchange_name} {symbol} {timeframe}:\n{ohlcv_df.head()}")
                    self.update_chart_from_dataframe(ohlcv_df)
                    
    def update_chart_from_dataframe(self, ohlcv_df):
        """Converts a DataFrame to OHLCV dict and updates the chart."""
        self.ohlcv = ohlcv_df.to_dict('list')
        dpg.configure_item(
            self.candle_series,
            dates=self.ohlcv['dates'],
            opens=self.ohlcv['opens'],
            highs=self.ohlcv['highs'],
            lows=self.ohlcv['lows'],
            closes=self.ohlcv['closes']
        )
        dpg.configure_item(
            self.volume_series,
            x=self.ohlcv['dates'],
            y=self.ohlcv['volumes']
        )

    def on_new_trade(self, exchange, trade_data):
        
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']

        if self.last_candle_timestamp is None:
            self.last_candle_timestamp = timestamp - (timestamp % self.timeframe)

        if timestamp >= self.last_candle_timestamp + self.timeframe:
            # Start a new candle
            new_candle_timestamp = self.last_candle_timestamp + self.timeframe
            self.ohlcv['dates'].append(new_candle_timestamp)
            self.ohlcv['opens'].append(price)
            self.ohlcv['highs'].append(price)
            self.ohlcv['lows'].append(price)
            self.ohlcv['closes'].append(price)
            self.ohlcv['volumes'].append(volume)
            self.last_candle_timestamp = new_candle_timestamp
        else:
            # Update the current candle
            if len(self.ohlcv['highs']) > 0 and len(self.ohlcv['lows']) > 0 and len(self.ohlcv['closes']) > 0 and len(self.ohlcv['volumes']) > 0:
                self.ohlcv['highs'][-1] = max(self.ohlcv['highs'][-1], price)
                self.ohlcv['lows'][-1] = min(self.ohlcv['lows'][-1], price)
                self.ohlcv['closes'][-1] = price
                self.ohlcv['volumes'][-1] += volume

        # Update the chart
        self.update_candle_chart()

    def update_candle_chart(self):
        # Assuming you've created a candle series with a tag
        dpg.configure_item(
            self.candle_series,
            dates=self.ohlcv['dates'],
            opens=self.ohlcv['opens'],
            highs=self.ohlcv['highs'],
            lows=self.ohlcv['lows'],
            closes=self.ohlcv['closes'],
        )
        dpg.configure_item(
            self.volume_series,
            x=self.ohlcv['dates'],
            y=self.ohlcv['volumes']
        )

    def on_order_book_update(self, exchange, orderbook):
        bids_df, ask_df, price_column = self.data.agg.on_order_book_update(exchange, orderbook, self.tick_size, self.aggregated_order_book)
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