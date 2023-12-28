import dearpygui.dearpygui as dpg
import pandas as pd

from src.data.data_source import Data
from src.gui import tags
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager

class Chart:
    def __init__(self, exchange, emitter: SignalEmitter, data: Data, task_manager: TaskManager) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        self.exchange = exchange
        
        # Order book variables
        self.ob_levels = 100
        self.tick_size = 10
        self.aggregated_order_book = True
        
        # UI elements will need to register for emitted signals
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        self.emitter.register(Signals.NEW_CANDLES, self.on_new_candles)
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)
        self.emitter.register(Signals.VIEWPORT_RESIZED, self.on_viewport_resize)
        self.emitter.register(Signals.TRADE_STAT_UPDATE, self.on_trade_stat_update)

        # OHLCV data structure
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        self.timeframe = 300  # Timeframe for the candles in seconds
        self.last_candle_timestamp = None
        self.active_symbol = None
        
        
        # UI setup
        with dpg.child_window(menubar=True, parent=tags.PRIMARY_WINDOW):
            with dpg.menu_bar():
                with dpg.menu(label=self.exchange.upper()):

                    dpg.add_text('Symbols')
                    dpg.add_listbox(
                        items=self.data.exchange_list[self.exchange]['symbols'], 
                        callback=lambda sender, symbol, user_data: self.start_stream(symbol),
                        num_items=8
                    )
                    
                    dpg.add_text('Timeframe')
                    dpg.add_listbox(
                        items=self.data.exchange_list[self.exchange]['timeframes'],
                        callback=lambda sender, timeframe, user_data: self.resample_chart(timeframe),
                        num_items=5
                    )
                    resample_tf = dpg.add_slider_int(label="Minutes", min_value=1, max_value=10080)
                    dpg.add_button(label="Resample", callback=lambda: self.resample_chart(dpg.get_value(resample_tf)))
                    
                
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
                            
    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book
                            
    def set_ob_levels(self, levels):
        self.ob_levels = levels
    
    # This needs to be abstracted more
    # The TaskManager is async loop running in thread as daemon, needed for non-blocking UI
    def start_stream(self, symbol):
        self.active_symbol = symbol
        
        self.task_manager.stop_all_tasks()
        
        # We need to fetch the candles (wait for them), this emits 'Signals.NEW_CANDLES', func 'on_new_candles' should set them    
        self.task_manager.run_task_until_complete(self.data.fetch_candles([self.exchange], [symbol], ['1m'], write_to_db=False))
        
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
    
    
    # Need to work on this function/finish, perhaps move to utils file or something
    def resample_chart(self, resampled_timeframe: str):
        
        # this shit could be done better but shit
        tf = int(resampled_timeframe[:-1])
        old_tf = self.timeframe # holds timeframe in minutes
        if resampled_timeframe.endswith('m'):
            self.timeframe = tf * 60
            resampled_timeframe = resampled_timeframe.replace('m', 'T')
        elif resampled_timeframe.endswith('h'):
            self.timeframe = tf * 60 * 60
        elif resampled_timeframe.endswith('d'):
            self.timeframe = tf * 60 * 60 * 24
        
        if tf < old_tf:
            # self.data.fetch_candles([self.exchange], [self.active_symbol], [resampled_timeframe], write_to_db=False)
            return
            
        # Convert 'dates' from Unix timestamp (in seconds) to datetime for resampling
        temp_ohlcv = self.ohlcv.copy()
        temp_ohlcv['dates'] = pd.to_datetime(temp_ohlcv['dates'], unit='s')

        # Set 'dates' as the index
        temp_ohlcv.set_index('dates', inplace=True)

        # Perform the resampling
        resampled_ohlcv = temp_ohlcv.resample(resampled_timeframe).agg({
            'opens': 'first',
            'highs': 'max',
            'lows': 'min',
            'closes': 'last',
            'volumes': 'sum'
        }).dropna().reset_index()

        # Convert 'dates' back to Unix timestamp in seconds for dearpygui
        resampled_ohlcv['dates'] = resampled_ohlcv['dates'].view('int64') // 1e9

        # Replace the existing DataFrame with the resampled one
        self.ohlcv = resampled_ohlcv

        # Update the chart with the new data
        self.update_candle_chart()

        # Reset the index back to a range index
        self.ohlcv.reset_index(drop=True, inplace=True)



    # This is good, single responsibility
    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
            self.update_candle_chart()

    # This is somewhat good, could be moved? Not sure
    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']

        if self.last_candle_timestamp is None:
            self.last_candle_timestamp = timestamp - (timestamp % self.timeframe)

        if timestamp >= self.last_candle_timestamp + self.timeframe:
            # Start a new candle
            new_candle = {
                'dates': self.last_candle_timestamp + self.timeframe,
                'opens': price,
                'highs': price,
                'lows': price,
                'closes': price,
                'volumes': volume
            }
            self.ohlcv = pd.concat([self.ohlcv, new_candle], ignore_index=True)
            self.last_candle_timestamp += self.timeframe
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
        bids_df, ask_df, price_column = self.data.agg.on_order_book_update(exchange, orderbook, self.tick_size, self.aggregated_order_book, self.ob_levels)
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