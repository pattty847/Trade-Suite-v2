import dearpygui.dearpygui as dpg
from config import ConfigManager
from data.data_source import Data

from gui.signals import SignalEmitter, Signals
from gui.task_manager import TaskManager
from gui.utils import searcher


class Tab:
    def __init__(self, parent, exchange, emitter, data, task_manager, config_manager):
        self.tab_id = dpg.generate_uuid()
        self.parent: str = parent
        
        self.emitter: SignalEmitter = emitter
        self.data: Data = data
        self.task_manager: TaskManager = task_manager
        self.config_manager: ConfigManager = config_manager
        
        
        self.exchange: str = exchange
        self.exchange_settings = self.config_manager.get_setting(exchange) or {}
        
        self.setup_ui_elements()
        self.setup_menus()

    def initialize_components(self):
        raise NotImplementedError("Subclasses must implement this method.")
    
    def setup_content(self):
        raise NotImplementedError("Subclasses must implement this method.")

    def start_data_stream(self):
        """
        def start_data_stream(self):
            if self.exchange and self.active_symbol and self.timeframe_str:
                self.task_manager.start_stream_for_chart(
                    self.parent,
                    exchange=self.exchange,
                    symbol=self.active_symbol,
                    timeframe=self.timeframe_str,
                )
        """
        raise NotImplementedError("Subclass must implement this method.")

    def setup_ui_elements(self):
        with dpg.tab(label=self.exchange.upper(), parent=self.parent, tag=self.tab_id):
            with dpg.child_window(menubar=True):
                self.setup_menus()
                self.setup_content()

    def setup_menus(self):
        with dpg.menu_bar():
            self.setup_exchange_menu()
            self.setup_settings_menu()
            self.trading.setup_trading_menu()
            self.indicators.create_indicators_menu()
            self.orderbook.setup_orderbook_menu()

    def setup_exchange_menu(self):
        with dpg.menu(label="Markets"):
            dpg.add_text("Symbols")
            # TODO: Add search box for symbols
            input_tag = dpg.add_input_text(label="Search")
            symbols_list = dpg.add_listbox(
                items=self.data.exchange_list[self.exchange].symbols,
                default_value=self.active_symbol,
                callback=lambda sender, symbol, user_data: self.emitter.emit(
                    Signals.SYMBOL_CHANGED,
                    exchange=self.exchange,
                    tab=self.parent,
                    new_symbol=symbol,
                ),
                num_items=8,
            )
            dpg.set_item_callback(
                input_tag,
                callback=lambda: searcher(
                    input_tag,
                    symbols_list,
                    self.data.exchange_list[self.exchange].symbols,
                ),
            )

            dpg.add_text("Timeframe")
            dpg.add_listbox(
                items=list(self.data.exchange_list[self.exchange].timeframes.keys()),
                default_value=self.timeframe_str,
                callback=lambda sender, timeframe, user_data: self.emitter.emit(
                    Signals.TIMEFRAME_CHANGED,
                    exchange=self.exchange,
                    tab=self.parent,
                    new_timeframe=timeframe,
                ),
                num_items=5,
            )

    def setup_settings_menu(self):
        with dpg.menu(label="Settings"):
            dpg.add_text("Candle Width")
            dpg.add_slider_float(
                min_value=0.1,
                max_value=1,
                callback=lambda s, a, u: dpg.configure_item(
                    self.candle_series, weight=a
                ),
            )
            dpg.add_menu_item(
                label="Stop All Streaming", callback=self.task_manager.stop_all_tasks
            )