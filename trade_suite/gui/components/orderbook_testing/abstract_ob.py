from abc import ABC, abstractmethod

import dearpygui.dearpygui as dpg
from config import ConfigManager
from data.data_source import Data
from gui.signals import SignalEmitter, Signals


class BaseOrderbook(ABC):
    def __init__(
        self,
        tab,
        exchange,
        symbol: str,
        emitter: SignalEmitter,
        data: Data,
        config: ConfigManager,
    ):
        self.tab = tab
        self.exchange = exchange
        self.symbol = symbol
        self.emitter = emitter
        self.data = data
        self.config = config
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
        with dpg.plot(
            label=label, height=-1, width=-1
        ) as self.plot:
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
