import dearpygui.dearpygui as dpg

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals


class OrderBook:
    def __init__(
        self, tab, exchange, emitter: SignalEmitter, data: Data, config: ConfigManager
    ):
        self.tab = tab
        self.exchange = exchange
        self.emitter = emitter
        self.data = data
        self.config = config

        self.show_orderbook = True
        self.aggregated_order_book = False
        self.order_book_levels = 100
        self.tick_size = (
            1  # TODO: This needs to be dynamic based on the symbols precision
        )

        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)

    def setup_orderbook_menu(self):
        with dpg.menu(label="Orderbook"):
            dpg.add_checkbox(
                label="Show",
                default_value=self.show_orderbook,
                callback=self.toggle_orderbook,
            )

    def toggle_orderbook(self):
        self.show_orderbook = not self.show_orderbook
        if self.show_orderbook:
            dpg.configure_item(
                f"{self.tab}_order_book_group", show=self.show_orderbook
            )
            dpg.configure_item(
                f"{self.tab}_charts_group", width=dpg.get_viewport_width() * 0.7
            )
        else:
            dpg.configure_item(f"{self.tab}_charts_group", width=-1)

    # Rest of the methods related to order book (update_order_book, set_ob_levels, etc.)

    def on_order_book_update(self, tab, exchange, orderbook):
        if exchange == self.exchange and tab == self.tab:
            bids_df, ask_df, price_column = self.data.agg.on_order_book_update(
                exchange,
                orderbook,
                self.tick_size,
                self.aggregated_order_book,
                self.order_book_levels,
            )
            self.update_order_book(bids_df, ask_df, price_column)

    def update_order_book(self, bids_df, asks_df, price_column):
        dpg.configure_item(
            self.bids_tag,
            x=bids_df[price_column].tolist(),
            y=bids_df["cumulative_quantity"].tolist(),
        )
        dpg.configure_item(
            self.asks_tag,
            x=asks_df[price_column].tolist(),
            y=asks_df["cumulative_quantity"].tolist(),
        )

        # Find the range for price and quantity
        min_price = min(bids_df[price_column].min(), asks_df[price_column].min())
        max_price = max(bids_df[price_column].max(), asks_df[price_column].max())
        max_quantity = max(
            bids_df["cumulative_quantity"].max(), asks_df["cumulative_quantity"].max()
        )

        # Update the x-axis limits for price
        dpg.set_axis_limits(axis=self.ob_xaxis, ymin=min_price, ymax=max_price)

        # Update the y-axis limits for quantity
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=0, ymax=max_quantity)

    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book

    def set_ob_levels(self, sender, app_data, user_data):
        self.order_book_levels = app_data
