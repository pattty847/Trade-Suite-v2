import json
import dearpygui.dearpygui as dpg

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals


class OrderBook:
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
        self.charts_group = f"{self.tab}_charts_group"  # tag id for chart's grouping
        self.order_book_group = (
            f"{self.tab}_order_book_group"  # tag id for order book group
        )

        self.show_orderbook = True
        self.aggregated_order_book = False
        self.spread_percentage = 0.05
        self.tick_size = 0
        self.market_info = self.data.exchange_list[self.exchange]["ccxt"].market(
            self.symbol
        )

        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)
        self.emitter.register(Signals.SYMBOL_CHANGED, self._on_symbol_change)

        self._update_tick_size(None, None, self.symbol)

    def setup_orderbook_menu(self):
        with dpg.menu(label="Orderbook"):
            dpg.add_checkbox(
                label="Show",
                default_value=self.show_orderbook,
                callback=self._toggle_orderbook,
            )

    def draw_orderbook_plot(self):
        with dpg.child_window(menubar=True, width=-1):
            with dpg.menu_bar():
                with dpg.menu(label="Series Type"):
                    self.line_bar_series_checkbox = dpg.add_checkbox(
                        label="Line Series",
                        default_value=True,
                        callback=self.toggle_series_type,
                    )

                with dpg.menu(label="Aggregate"):
                    dpg.add_checkbox(
                        label="Toggle",
                        default_value=self.aggregated_order_book,
                        callback=self.toggle_aggregated_order_book,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Aggregates orderbook levels by the tick size.")

                    self.tick_size_slider_id = dpg.add_slider_float(
                        label="Tick",
                        default_value=self.market_info["precision"]["price"],
                        callback=self.set_tick_size,
                        min_value=self.market_info["precision"]["price"],
                        max_value=10,
                        show=self.aggregated_order_book,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Set the aggregation tick size.")

                with dpg.menu(label="Levels"):
                    dpg.add_slider_float(
                        label="Spread %",
                        default_value=self.spread_percentage,
                        min_value=0,
                        max_value=1,
                        callback=self.set_ob_levels,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Change the midpoint spreadD %.")

            with dpg.group(horizontal=True):
                dpg.add_text(f"Bid/Ask Ratio: ")
                self.bid_ask_ratio = dpg.add_text("")

            with dpg.plot(
                label="Orderbook", no_title=True, height=-1, width=-1
            ) as self.orderbook_tag:
                dpg.add_plot_legend()

                self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
                with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                    self.line_series = True  # or False, depending on your default

                    # Inside plot axis context:
                    self.bids_bar_tag = dpg.add_bar_series([], [], label="Bids")
                    self.asks_bar_tag = dpg.add_bar_series([], [], label="Asks")
                    self.bids_line_tag = dpg.add_line_series([], [], label="Bids")
                    self.asks_line_tag = dpg.add_line_series([], [], label="Asks")

                    # Show/hide based on default
                    dpg.hide_item(
                        self.bids_line_tag if self.line_series else self.bids_bar_tag
                    )
                    dpg.hide_item(
                        self.asks_line_tag if self.line_series else self.asks_bar_tag
                    )

    # Listens for order book emissions
    def on_order_book_update(self, tab, exchange, orderbook):
        if exchange == self.exchange and tab == self.tab:
            # Pass the 'self.aggregated_order_book' to determine if aggregation is needed
            bids_df, asks_df, price_column = self.data.agg.on_order_book_update(
                exchange,
                orderbook,
                self.tick_size,
                self.aggregated_order_book,
            )

            if self.aggregated_order_book:
                # If aggregated, use cumulative quantities
                bids_df["cumulative_quantity"] = bids_df["quantity"].cumsum()
                asks_df["cumulative_quantity"] = asks_df["quantity"].cumsum()

            # Whether aggregated or not, update the order book display
            self._update_order_book(bids_df, asks_df, price_column)

    def _update_order_book(self, bids_df, asks_df, price_column):
        bid_prices = bids_df[price_column].tolist()
        ask_prices = asks_df[price_column].tolist()
        bid_quantities = bids_df[
            "cumulative_quantity" if self.aggregated_order_book else "quantity"
        ].tolist()
        ask_quantities = asks_df[
            "cumulative_quantity" if self.aggregated_order_book else "quantity"
        ].tolist()

        dpg.configure_item(self.bids_bar_tag, x=bid_prices, y=bid_quantities)
        dpg.configure_item(self.asks_bar_tag, x=ask_prices, y=ask_quantities)
        dpg.configure_item(self.bids_line_tag, x=bid_prices, y=bid_quantities)
        dpg.configure_item(self.asks_line_tag, x=ask_prices, y=ask_quantities)

        # Calculate the midpoint between the best bid and best ask
        best_bid = bids_df[price_column].max()
        best_ask = asks_df[price_column].min()
        midpoint = (best_bid + best_ask) / 2
        price_range = midpoint * self.spread_percentage

        # Update the x-axis limits based on the midpoint and calculated range
        dpg.set_axis_limits(
            axis=self.ob_xaxis, ymin=midpoint - price_range, ymax=midpoint + price_range
        )

        # Calculate the y-axis limits
        visible_bids = bids_df[bids_df[price_column] >= midpoint - price_range]
        visible_asks = asks_df[asks_df[price_column] <= midpoint + price_range]

        if (
            self.aggregated_order_book
            and "cumulative_quantity" in bids_df
            and "cumulative_quantity" in asks_df
        ):
            max_bid_quantity = visible_bids["cumulative_quantity"].max()
            max_ask_quantity = visible_asks["cumulative_quantity"].max()
        else:
            max_bid_quantity = visible_bids["quantity"].max()
            max_ask_quantity = visible_asks["quantity"].max()

        max_y_value = max(max_bid_quantity, max_ask_quantity)

        # Use a small buffer above the max_y_value for better visual spacing
        buffer = max_y_value * 0.1  # 10% buffer
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=0, ymax=max_y_value + buffer)

        # Calculate the visible bid and ask quantities
        visible_bid_quantities = visible_bids[
            "cumulative_quantity" if self.aggregated_order_book else "quantity"
        ].sum()
        visible_ask_quantities = visible_asks[
            "cumulative_quantity" if self.aggregated_order_book else "quantity"
        ].sum()

        # Calculate bid-ask ratio for visible quantities
        if visible_ask_quantities > 0:  # Prevent division by zero
            bid_ask_ratio = visible_bid_quantities / visible_ask_quantities
        else:
            bid_ask_ratio = float("inf")

        # Set the bid-ask ratio value in the UI (assuming self.bid_ask_ratio is a UI element)
        dpg.set_value(
            self.bid_ask_ratio, f"{bid_ask_ratio:.2f}"
        )  # Replace with actual UI element ID

    def toggle_series_type(self, sender, app_data, user_data):
        logging.info(app_data)
        self.line_series = app_data
        # self.toggle_aggregated_order_book()
        # Logic to show/hide series
        if self.line_series:
            dpg.hide_item(self.bids_bar_tag)
            dpg.hide_item(self.asks_bar_tag)
            dpg.show_item(self.bids_line_tag)
            dpg.show_item(self.asks_line_tag)
        else:
            dpg.hide_item(self.bids_line_tag)
            dpg.hide_item(self.asks_line_tag)
            dpg.show_item(self.bids_bar_tag)
            dpg.show_item(self.asks_bar_tag)

    def _toggle_orderbook(self):
        self.show_orderbook = not self.show_orderbook
        if self.show_orderbook:
            dpg.configure_item(self.order_book_group, show=self.show_orderbook)
            dpg.configure_item(self.charts_group, width=dpg.get_viewport_width() * 0.7)
        else:
            dpg.configure_item(self.charts_group, width=-1)

    # Rest of the methods related to order book (update_order_book, set_ob_levels, etc.)

    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book
        dpg.configure_item(self.tick_size_slider_id, show=self.aggregated_order_book)

    def set_ob_levels(self, sender, app_data, user_data):
        self.spread_percentage = app_data

    def set_tick_size(self, sender, app_data, user_data):
        self.tick_size = app_data

    def _on_symbol_change(self, exchange, tab, new_symbol):
        self.symbol = new_symbol

        self.market_info = self.data.exchange_list[self.exchange]["ccxt"].market(
            self.symbol
        )

        self._update_tick_size(exchange, tab, self.symbol)

    def _update_tick_size(self, exchange, tab, new_symbol):
        price_precision = self.market_info["precision"]["price"]
        self._set_tick_size(price_precision)

    def _set_tick_size(self, tick_size: float):
        # Check if its within the precision limits
        self.tick_size = tick_size
