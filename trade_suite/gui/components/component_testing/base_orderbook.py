from abc import ABC, abstractmethod

import dearpygui.dearpygui as dpg
from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.components.component_testing.base_tab import BaseTab
from trade_suite.gui.signals import SignalEmitter, Signals


class BaseOrderbook(ABC, BaseTab):
    def __init__(self, parent, exchange, emitter, data, task_manager, config_manager):
        super().__init__(parent, exchange, emitter, data, task_manager, config_manager)
        
        # tag id for chart's grouping
        self.charts_group = f"{self.tab}_charts_group"
        self.order_book_group = (
            f"{self.tab}_order_book_group"  # tag id for order book group
        )
        self.setup_listeners()

    def setup_listeners(self):
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)
        self.emitter.register(Signals.SYMBOL_CHANGED, self.on_symbol_change)
        # self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)

    @abstractmethod
    def draw(self, label):
        with dpg.child_window(label=f'Test OrderBook: {self.exchange}'):
            pass
        
    @abstractmethod
    def is_active_tab_and_exchange(self, tab, exchange):
        return True if exchange == self.exchange and tab == self.tab else False


    # Optional: Define on_new_trade if needed for your visualizations
    # @abstractmethod
    # def on_new_trade(self, trade):
    #     pass


class TestOB(BaseOrderbook):
    def draw(self, label):
        # First, call the base class draw to setup the plot
        super().draw(label=label)
        
        with dpg.plot(
            label=label, height=-1, width=-1
        ) as self.plot:
            
            dpg.add_plot_legend()

            self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
            
            with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.yaxis:
                # Assuming self.plot is already created by the base class
                self.bids_bar_series = dpg.add_bar_series([], [], label="Bids", parent=self.yaxis)
                self.asks_bar_series = dpg.add_bar_series([], [], label="Asks", parent=self.yaxis)

    def on_order_book_update(self, tab, exchange, orderbook):
        # Here, handle updating the data for the bar series based on the orderbook update.
        # This will involve setting the x and y data for the bar series.
        pass

    def on_symbol_change(self, tab, exchange, symbol):
        # Handle any necessary updates when the symbol changes
        pass

    def on_new_trade(self, trade):
        # Handle any necessary updates when a new trade occurs
        pass
