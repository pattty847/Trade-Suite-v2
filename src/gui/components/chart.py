import dearpygui.dearpygui as dpg
import pandas as pd

from collections import deque

from src.data.data_source import Data
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager

"""

We need to incorporate pandas for the candle sticks here and in Data(). 

Maintain a consistant Chart object and modularity wherever possible.

"""

class Chart:
    def __init__(self, emitter: SignalEmitter, data: Data, task_manager: TaskManager) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        
        # Figure out base values for these
        self.active_stream = None
        self.active_timeframe = None

        # UI elements will need to register for emitted signals
        
        # When we receive a trade after streaming symbol(s) on an exchange(s) we can subscribe to the events.
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        self.emitter.register(Signals.NEW_CANDLES, self.on_new_candles)

        
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
                    
                    
                    dpg.add_text('Test Candle Fetch')
                    symbol = 'ETH/USD'
                    dpg.add_button(
                        label=symbol,
                        callback=lambda sender, app_data, user_data: self.task_manager.start_task(
                            'fetch_candles',
                            self.data.fetch_candles(
                                exchanges=['coinbasepro'], 
                                symbols=[symbol], 
                                timeframes=['1m'], 
                                write_to_db=False
                            )
                        )
                    )
                
                
                with dpg.menu(label="Settings"):
                    dpg.add_slider_float(min_value=0.1, max_value=5, callback=lambda s, a, u: dpg.configure_item(self.candle_series, weight=a))
                
                
                    with dpg.menu(label="Testing"):
                        dpg.add_button(label="Stop Async Tasks", callback=self.task_manager.stop_all_tasks)
            

            with dpg.group(width=-1, height=-1):
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
                self.timeframe = 60  # Timeframe for the candles in seconds
                self.last_candle_timestamp = None
                
                with dpg.subplots(rows=2, columns=1, row_ratios=[.7, .3], link_all_x=True):
                    with dpg.plot(label="Candlestick Chart", no_title=True):
                        dpg.add_plot_legend()
                        xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                        with dpg.plot_axis(dpg.mvYAxis, label="USD"):
                            self.candle_series = dpg.add_candle_series(
                                list(self.ohlcv['dates']),
                                list(self.ohlcv['opens']),
                                list(self.ohlcv['closes']),
                                list(self.ohlcv['lows']),
                                list(self.ohlcv['highs']),
                                time_unit=dpg.mvTimeUnit_Min
                            )
                            dpg.fit_axis_data(dpg.top_container_stack())
                        dpg.fit_axis_data(xaxis)
                    
                    with dpg.plot(no_title=True):
                        dpg.add_plot_legend()
                        xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                        with dpg.plot_axis(dpg.mvYAxis, label="USD"):
                            self.volume_series = dpg.add_line_series(
                                list(self.ohlcv['dates']),
                                list(self.ohlcv['volumes']),
                            )
                            dpg.fit_axis_data(dpg.top_container_stack())
                        dpg.fit_axis_data(xaxis)

                        
    def start_stream(self, symbol):
        for task in list(self.task_manager.tasks):
            self.task_manager.stop_task(task)
        
        # We need to fetch the candles (wait for them), this emits 'Signals.NEW_CANDLES', func 'on_new_candles' should set them    
        self.task_manager.run_task_until_complete(self.data.fetch_candles(['coinbasepro'], [symbol], ['1m'], write_to_db=False))
        
        # We start the stream (ticks), this emits 'Signals.NEW_TRADE', func 'on_new_trade' handles building of candles
        self.task_manager.start_task(
            f'stream_{symbol}_{self.timeframe}', 
            # TODO: Add 'exchange' parameter to 'stream_trades'
            coro=self.data.stream_trades(
                symbols=[symbol], 
                chart_tag=self.candle_series
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
        print(orderbook)