from abc import abstractmethod
import dearpygui.dearpygui as dpg
import pandas as pd

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import searcher

class BaseTab:
    def __init__(self, parent, exchange, emitter, data, task_manager, config_manager):
        self.tab_id = dpg.generate_uuid()
        self.exchange: str = exchange
        self.parent: str = parent # tab_bar
        self.emitter: SignalEmitter = emitter
        self.data: Data = data
        self.task_manager: TaskManager = task_manager
        self.config_manager: ConfigManager = config_manager  
        
        self.exchange: str = exchange
        self.exchange_settings = self.config_manager.get_setting(exchange) or {}
        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        
        self.timeframe_str = self.get_default_timeframe()
        self.active_symbol = self.get_default_symbol()      
    
        
    @abstractmethod
    def start_data_stream(self):
        # This method will be implemented in the derived class
        raise NotImplementedError("Must be implemented by the subclass.")

    @abstractmethod
    def initialize_components(self):
        # This method will be implemented in the derived class
        raise NotImplementedError("Must be implemented by the subclass.")

    def setup_ui_elements(self):
        with dpg.tab(label=f"Candle: {self.exchange.upper()}", tag=self.tab_id, parent=self.parent):
            with dpg.child_window(menubar=True):
                self.setup_menus()
                self.setup_display()

    def setup_menus(self):
        with dpg.menu_bar():
            self.setup_exchange_menu()
            self.setup_settings_menu()

    def setup_exchange_menu(self):
        with dpg.menu(label="Markets"):
            dpg.add_text("Symbols")
            # TODO: Add search box for symbols
            input_tag = dpg.add_input_text(label="Search")
            symbols_list = dpg.add_listbox(
                items=self.data.exchange_list[self.exchange]["symbols"],
                default_value=self.active_symbol,
                callback=lambda sender, symbol, user_data: self.emitter.emit(
                    Signals.SYMBOL_CHANGED,
                    exchange=self.exchange,
                    tab=self.tab_id,
                    new_symbol=symbol,
                ),
                num_items=8,
            )
            dpg.set_item_callback(
                input_tag,
                callback=lambda: searcher(
                    input_tag,
                    symbols_list,
                    self.data.exchange_list[self.exchange]["symbols"],
                ),
            )

            dpg.add_text("Timeframe")
            dpg.add_listbox(
                items=self.data.exchange_list[self.exchange]["timeframes"],
                default_value=self.timeframe_str,
                callback=lambda sender, timeframe, user_data: self.emitter.emit(
                    Signals.TIMEFRAME_CHANGED,
                    exchange=self.exchange,
                    tab=self.tab_id,
                    new_timeframe=timeframe,
                ),
                num_items=5,
            )

    def setup_settings_menu(self):
        with dpg.menu(label="Settings"):
            pass
    
    @abstractmethod
    def register_event_listeners(self):
        raise NotImplementedError("Must be implemented by the subclass.")
    
    @abstractmethod
    def setup_display(self):
        # This method will be implemented in the derived class
        raise NotImplementedError("Must be implemented by the subclass.")
    
    @abstractmethod
    def on_viewport_resize(self, width, height):
        # This method will be implemented in the derived class
        raise NotImplementedError("Must be implemented by the subclass.")

    def get_default_timeframe(self):
        return (
            self.exchange_settings.get("last_timeframe")
            or self.data.exchange_list[self.exchange]["timeframes"][1]
        )

    def get_default_symbol(self):
        return (
            self.exchange_settings.get("last_symbol")
            or self.get_default_bitcoin_market()
        )

    def get_default_bitcoin_market(self):
        symbols = self.data.exchange_list[self.exchange]["symbols"]
        return next(
            (symbol for symbol in symbols if symbol in ["BTC/USD", "BTC/USDT"]), None
        )