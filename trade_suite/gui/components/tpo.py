import logging
import dearpygui.dearpygui as dpg
import pandas as pd
from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.components.component_testing.base_tab import BaseTab
from trade_suite.gui.components.orderbook import OrderBook

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager

class TPO(BaseTab):
    def __init__(self, parent, exchange, emitter, data, task_manager, config_manager):
        super().__init__(parent, exchange, emitter, data, task_manager, config_manager)
        
        self.initialize_components()
        self.setup_ui_elements()
        self.register_event_listeners()
        self.start_data_stream()
        
    def initialize_components(self):
        self.orderbook = OrderBook(
            self.tab_id,
            self.exchange,
            self.active_symbol,
            self.emitter,
            self.data,
            self.config_manager,
        )
        
    def start_data_stream(self):
        pass
        
    def setup_ui_elements(self):
        with dpg.tab(label=f"TPO: {self.exchange.upper()}", tag=self.tab_id, parent=self.parent):
            with dpg.child_window(menubar=True):
                super().setup_menus()
                self.setup_display()
                
    def setup_display(self):
        dpg.add_text("The TPO Chart will go here")
    
        
    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles,  # first callback emitted when application starts (requests last chart user had)
            Signals.VIEWPORT_RESIZED: self.on_viewport_resize,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)
            
    def on_new_trade(self, tab, exchange, trade_data):
        if tab == self.tab_id:
            timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
            price = trade_data["price"]
            volume = trade_data["amount"] * 2
            
            logging.info(timestamp, price, volume)
        
        
    def on_new_candles(self, tab, exchange, candles):
        if tab == self.tab_id:
            if isinstance(candles, pd.DataFrame) and tab == self.tab_id:
                self.ohlcv = candles
                
    def on_viewport_resize(self, width, height):
        pass