import pandas as pd
from trade_suite.data.data_source import Data

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import timeframe_to_seconds


class CandleFactory:
    def __init__(self, exchange, emitter: SignalEmitter, task_manager: TaskManager, data: Data, exchange_settings, ohlcv) -> None:
        self.exchange = exchange
        self.emitter = emitter
        self.task_manager = task_manager
        self.data = data
        self.exchange_settings = exchange_settings
        self.timeframe_str = self.exchange_settings['last_timeframe'] if self.exchange_settings else '15m'
        self.timeframe_seconds = timeframe_to_seconds(self.timeframe_str)  # Timeframe for the candles in seconds
        self.last_candle_timestamp = None
        
        self.ohlcv = ohlcv
        
        self.register_event_listeners()
        
    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.build_candle_from_stream,
            Signals.NEW_CANDLES: self.on_new_candles
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)
        
    def on_new_candles(self, exchange, candles):
        if isinstance(candles, pd.DataFrame) and exchange == self.exchange:
            self.ohlcv = candles
        
    def build_candle_from_stream(self, exchange, trade_data):
        if exchange != self.exchange:
            return 
        
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
        
        self.emitter.emit(Signals.UPDATED_CANDLES, exchange=exchange, candles=self.ohlcv)
        
    def resample_candle(self, new_timeframe: str, active_exchange):
        timeframe_in_seconds = timeframe_to_seconds(new_timeframe)
        # if new timeframe > old timeframe
        if timeframe_in_seconds > self.timeframe_seconds:
            ohlcv = self.data.agg.resample_data(self.ohlcv, new_timeframe)
            self.emitter.emit(Signals.UPDATED_CANDLES, exchange=active_exchange, candles=ohlcv)
            self.ohlcv = ohlcv
        else:
            return None
        self.timeframe_seconds = timeframe_in_seconds