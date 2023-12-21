import asyncio
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
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        
        with dpg.child_window(menubar=True):
            with dpg.menu_bar():
                with dpg.menu(label="Symbols"):
                    # TODO: Need a function to check if symbol is already streaming if so, stop, start new one, handle errors, etc.
                    dpg.add_listbox(
                        self.data.exchange_list['coinbasepro']['symbols'], 
                        callback= lambda s, a, u: self.task_manager.start_task(
                            'stream_symbol', 
                            self.data.stream_trades([a])
                        )
                    )
                with dpg.menu(label="Testing"):
                    dpg.add_button(label="Run Async Task", callback=self.trigger_async_task)
                    dpg.add_button(label="Stop Async Task", callback=self.stop_async_task)
            
            
            dpg.add_text(tag='price')
            dpg.add_text(tag='cost')
        
            
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

            with dpg.plot(use_local_time=True, width=-1, height=-1):
                dpg.add_plot_legend()
                xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
                with dpg.plot_axis(dpg.mvYAxis, label="USD"):
                    # dpg.add_candle_series(
                    #     list(self.ohlcv['timestamps']),
                    #     list(self.ohlcv['opens']),
                    #     list(self.ohlcv['closes']),
                    #     list(self.ohlcv['lows']),
                    #     list(self.ohlcv['highs']),
                    #     weight=0.1,
                    #     tag='candle_series_tag',
                    #     time_unit=dpg.mvTimeUnit_Min
                    # )
                    dpg.add_line_series(self.x, self.y, tag='line_series')
                    dpg.fit_axis_data(dpg.top_container_stack())
                dpg.fit_axis_data(xaxis)
            

    async def async_task(self):
        await self.data.stream_trades(['BTC/USD'], tag='results')

    def trigger_async_task(self, sender, app_data, user_data):
        self.task_manager.start_task("async_task", self.async_task())

    def stop_async_task(self, sender, app_data, user_data):
        self.task_manager.stop_task("stream_symbol")

    def stop_all_async_tasks(self):
        self.task_manager.stop_all_tasks()

    def on_new_trade(self, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']
        
        self.x.append(timestamp)
        self.y.append(price)
        
        dpg.configure_item('line_series', x=self.x, y=self.y)

    def on_new_trade_(self, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']

        # Determine if this trade starts a new candle
        if self.last_candle_timestamp is None or timestamp >= self.last_candle_timestamp + self.timeframe:
            self.ohlcv['timestamps'].append(timestamp)
            self.ohlcv['opens'].append(price)
            self.ohlcv['highs'].append(price)
            self.ohlcv['lows'].append(price)
            self.ohlcv['closes'].append(price)
            self.ohlcv['volumes'].append(volume)
            self.last_candle_timestamp = timestamp
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