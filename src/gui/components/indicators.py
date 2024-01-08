import dearpygui.dearpygui as dpg
import pandas as pd

from src.gui.signals import SignalEmitter, Signals
from src.gui.utils import str_timeframe_to_minutes

class Indicators:
    
    def __init__(self, emitter: SignalEmitter, exchange_settings) -> None:
        self.emitter = emitter
        self.exchange_settings = exchange_settings

        
        self.timeframe_str = self.exchange_settings['last_timeframe'] if self.exchange_settings else '15m'
        self.timeframe_seconds = str_timeframe_to_minutes(self.timeframe_str)  # Timeframe for the candles in seconds
        
        self.candle_series_yaxis = None
        
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        
        self.show_ema = False
        self.line_series_ids = {}
        
        self.register_event_listeners()
        
        
    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles,
            Signals.TIMEFRAME_CHANGED: self.on_timeframe_change,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)
           
            
    def on_timeframe_change(self, new_timeframe: str):
        timeframe_in_minutes = str_timeframe_to_minutes(new_timeframe)
        self.timeframe_str = new_timeframe
        self.timeframe_seconds = timeframe_in_minutes
            
            
    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
        
        
    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']
        
                
                
    def setup_line_series_menu(self):
        with dpg.menu(label="Indicators"):
            with dpg.menu(label="Moving Averages"):
                dpg.add_checkbox(label="EMAs", default_value=self.show_ema, callback=self.toggle_ema)
    
    
    def toggle_ema(self):
        self.show_ema = not self.show_ema
        if not self.line_series_ids:
            print("test")
            self.add_line_series()
            
        for line_series_id in self.line_series_ids.values():
            dpg.configure_item(line_series_id, show=self.show_ema)

    def add_line_series(self):
        span = [10, 25, 50, 100, 200]
        ema_values = [self.ohlcv['closes'].ewm(span=x, adjust=False).mean().tolist() for x in span]

        for ema, span_value in zip(ema_values, span):
            label = f"EMA {span_value}"
            line_series_id = dpg.add_line_series(list(self.ohlcv['dates']), list(ema), label=label, parent=self.candle_series_yaxis)
            self.line_series_ids[span_value] = line_series_id  # Store the line series ID