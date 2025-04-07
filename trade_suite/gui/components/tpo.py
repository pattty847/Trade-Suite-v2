import logging
import dearpygui.dearpygui as dpg
import pandas as pd
from config import ConfigManager
from data.data_source import Data

from gui.signals import SignalEmitter, Signals
from gui.task_manager import TaskManager
from gui.utils import searcher


class TAB:
    def __init__(self, parent, exchange, emitter, data, task_manager, config_manager):
        self.initialize_attributes(
            parent, exchange, emitter, data, task_manager, config_manager
        )
        self.initialize_components()
        self.setup_ui_elements()
        self.register_event_listeners()
        self.start_data_stream()

    def initialize_attributes(
        self, parent, exchange, emitter, data, task_manager, config_manager
    ):
        self.tab_id = dpg.generate_uuid()
        self.parent: str = parent
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

    def initialize_components(self):
        pass

    def start_data_stream(self):
        pass

    def setup_ui_elements(self):
        with dpg.tab(
            label=f"TPO: {self.exchange.upper()}", tag=self.tab_id, parent=self.parent
        ):
            with dpg.child_window(menubar=True):
                self.setup_menus()
                self.setup_display()

    def setup_menus(self):
        with dpg.menu_bar():
            self.setup_exchange_menu()

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
                    tab=self.tab_id,
                    new_timeframe=timeframe,
                ),
                num_items=5,
            )

    def setup_display(self):
        with dpg.plot(label="", no_title=True, height=-1):
            dpg.add_plot_legend()
            self.series_xaxis = dpg.add_plot_axis(dpg.mvXAxis, time=True)
            with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.series_yaxis:
                # Ensure data is populated before adding series
                self.series = dpg.add_line_series([], [])

    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles,  # first callback emitted when application starts (requests last chart user had)
            Signals.UPDATED_CANDLES: self.on_updated_candles,
            Signals.VIEWPORT_RESIZED: self.on_viewport_resize,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def on_new_trade(self, tab, exchange, trade_data):
        if tab == self.tab_id:
            timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
            price = trade_data["price"]
            volume = trade_data["amount"] * 2

    def on_new_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab_id:
            self.ohlcv = candles

            self.series_ = {
                "dates": self.ohlcv["dates"].tolist(),
                "closes": self.ohlcv["closes"].tolist(),
            }
            dpg.configure_item(
                self.series, self.series_["dates"], self.series_["closes"]
            )

    def on_updated_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab_id:
            self.ohlcv = candles

    def on_viewport_resize(self, width, height):
        pass

    def get_default_timeframe(self):
        return (
            self.exchange_settings.get("last_timeframe")
            or list(self.data.exchange_list[self.exchange].timeframes.keys())[1]
        )

    def get_default_symbol(self):
        return (
            self.exchange_settings.get("last_symbol")
            or self.get_default_bitcoin_market()
        )

    def get_default_bitcoin_market(self):
        symbols = self.data.exchange_list[self.exchange].symbols
        return next(
            (symbol for symbol in symbols if symbol in ["BTC/USD", "BTC/USDT"]), None
        )
