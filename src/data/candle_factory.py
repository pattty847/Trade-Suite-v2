import pandas as pd
from src.data.data_source import Data

from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager
from src.gui.utils import str_timeframe_to_minutes


class CandleFactory:
    def __init__(self, emitter: SignalEmitter, task_manager: TaskManager, data: Data, exchange_settings) -> None:
        self.emitter = emitter
        self.task_manager = task_manager
        self.data = data
        self.exchange_settings = exchange_settings
        self.timeframe_str = self.exchange_settings['last_timeframe'] if self.exchange_settings else '15m'
        self.timeframe_seconds = str_timeframe_to_minutes(self.timeframe_str)  # Timeframe for the candles in seconds
        print(self.timeframe_seconds, self.timeframe_str)
        self.last_candle_timestamp = None
        
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        
        self.register_event_listeners()
        
    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.build_candle_from_stream,
            Signals.NEW_CANDLES: self.on_new_candles
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)
        
    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
        
    def build_candle_from_stream(self, exchange, trade_data):
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
        
        self.emitter.emit(Signals.UPDATED_CANDLES, candles=self.ohlcv)
        
    def resample_candle(self, new_timeframe: str, active_exchange, active_symbol):
        timeframe_in_minutes = str_timeframe_to_minutes(new_timeframe)
        
        # if new timeframe > old timeframe
        if timeframe_in_minutes > self.timeframe_seconds:
            ohlcv = self.data.agg.resample_data(self.ohlcv, new_timeframe)
            self.emitter.emit(Signals.UPDATED_CANDLES, candles=ohlcv)
            self.ohlcv = ohlcv
        else:
            self.task_manager.start_stream(active_exchange, active_symbol, new_timeframe, cant_resample=True)