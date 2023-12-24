from collections import deque
import dearpygui.dearpygui as dpg
import pandas as pd

from src.data.data_source import Data
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager

class Chart:
    def __init__(self, emitter: SignalEmitter, data: Data, task_manager: TaskManager) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager

        # UI elements will need to register for emitted signals
        
        # When we receive a trade after streaming symbol(s) on an exchange(s) we can subscribe to the events.
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        self.emitter.register(Signals.FETCHED_CANDLES, self.on_new_candles)
        
        with dpg.child_window(menubar=True):
            with dpg.menu_bar():
                with dpg.menu(label="CoinbasePro"):
                    # TODO: Need a function to check if symbol is already streaming if so, stop, start new one, handle errors, etc.
                    dpg.add_text('Symbols')
                    dpg.add_listbox(
                        items=self.data.exchange_list['coinbasepro']['symbols'], 
                        callback= lambda sender, app_data, user_data: self.task_manager.start_task(
                            'stream_symbol', 
                            self.data.stream_trades([app_data])
                        ),
                        num_items=8
                    )
                    dpg.add_text('Timeframe')
                    dpg.add_listbox(
                        items=self.data.exchange_list['coinbasepro']['timeframes'],
                        callback=lambda sender, app_data, user_data: self.task_manager.start_task(
                            'fetch_candles',
                            # Set timeframe, resample candle series (if possible, or request new data?)
                        ),
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
                                timeframes=['1h'], 
                                write_to_db=True
                            )
                        )
                    )
                
                
                with dpg.menu(label="Settings"):
                    dpg.add_slider_float(min_value=0.1, max_value=2, callback=lambda s, a, u: dpg.configure_item('candle_series_tag', weight=a))
                
                
                with dpg.menu(label="Testing"):
                    dpg.add_button(label="Stop Async Tasks", callback=self.task_manager.stop_all_tasks)
            
       
            # OHLCV data structure
            self.ohlcv = {
                'timestamps': deque(maxlen=1000),
                'opens': deque(maxlen=1000),
                'highs': deque(maxlen=1000),
                'lows': deque(maxlen=1000),
                'closes': deque(maxlen=1000),
                'volumes': deque(maxlen=1000)
            }
            self.timeframe = 60  # Timeframe for the candles in seconds
            self.last_candle_timestamp = None

            self.x = []
            self.y = []

            with dpg.plot(use_local_time=True, width=-1, height=-1, crosshairs=True):
                dpg.add_plot_legend()
                xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                with dpg.plot_axis(dpg.mvYAxis, label="USD"):
                    dpg.add_candle_series(
                        list(self.ohlcv['timestamps']),
                        list(self.ohlcv['opens']),
                        list(self.ohlcv['closes']),
                        list(self.ohlcv['lows']),
                        list(self.ohlcv['highs']),
                        weight=0.1,
                        tag='candle_series_tag',
                        time_unit=dpg.mvTimeUnit_Hr
                    )
                    # dpg.add_line_series(self.x, self.y, tag='line_series')
                    dpg.fit_axis_data(dpg.top_container_stack())
                dpg.fit_axis_data(xaxis)

        
    def on_new_candles(self, all_candles):
        for exchange_name, candles in all_candles.items():
            for key, ohlcv_df in candles.items():
                symbol, timeframe = key.split("-")
                print(symbol, timeframe, ohlcv_df)

                # Ensure the index is timezone-aware in UTC before conversion
                if not ohlcv_df.index.tzinfo:
                    ohlcv_df = ohlcv_df.tz_localize('UTC')

                # Convert the index to UNIX time (seconds since the epoch)
                timestamps = ohlcv_df.index.view('int64') // 10**9

                # Set the OHLCV data from the DataFrame
                self.ohlcv = {
                    'timestamps': list(timestamps),
                    'opens': list(ohlcv_df['open']),
                    'highs': list(ohlcv_df['high']),
                    'lows': list(ohlcv_df['low']),
                    'closes': list(ohlcv_df['close']),
                    'volumes': list(ohlcv_df['volume'])
                }

                # Update the chart with new candle data
                dpg.configure_item(
                    'candle_series_tag',
                    dates=self.ohlcv['timestamps'],
                    opens=self.ohlcv['opens'],
                    highs=self.ohlcv['highs'],
                    lows=self.ohlcv['lows'],
                    closes=self.ohlcv['closes']
                )

    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']

        # Normalize first timestamp to the nearest lower interval
        if self.last_candle_timestamp is None:
            # This aligns the first timestamp to the beginning of the timeframe interval
            self.last_candle_timestamp = timestamp - (timestamp % self.timeframe)

        # Determine if this trade starts a new candle
        if timestamp >= self.last_candle_timestamp + self.timeframe:
            # Start a new candle at the beginning of the new interval
            new_candle_timestamp = self.last_candle_timestamp + self.timeframe
            self.ohlcv['timestamps'].append(new_candle_timestamp)
            self.ohlcv['opens'].append(price)
            self.ohlcv['highs'].append(price)
            self.ohlcv['lows'].append(price)
            self.ohlcv['closes'].append(price)
            self.ohlcv['volumes'].append(volume)
            self.last_candle_timestamp = new_candle_timestamp
        else:
            # Update current candle
            self.ohlcv['highs'][-1] = max(self.ohlcv['highs'][-1], price)
            self.ohlcv['lows'][-1] = min(self.ohlcv['lows'][-1], price)
            self.ohlcv['closes'][-1] = price
            self.ohlcv['volumes'][-1] += volume

        # Update the chart with new candle data
        self.update_candle_chart()
        
    def update_candle_chart(self):
        # Assuming you've created a candle series with a tag
        dpg.configure_item(
            'candle_series_tag',
            dates=list(self.ohlcv['timestamps']),
            opens=list(self.ohlcv['opens']),
            highs=list(self.ohlcv['highs']),
            lows=list(self.ohlcv['lows']),
            closes=list(self.ohlcv['closes']),
        )
        
    def on_new_trade_(self, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']
        
        self.x.append(timestamp)
        self.y.append(price)
        
        dpg.configure_item('line_series', x=self.x, y=self.y)