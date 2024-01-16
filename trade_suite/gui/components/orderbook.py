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

        self.show_orderbook = True
        self.aggregated_order_book = False
        self.order_book_levels = 100
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
                        default_value=self.market_info['precision']['price'],
                        callback=self.set_tick_size,
                        min_value=self.market_info['precision']['price'],
                        max_value=10,
                        show=self.aggregated_order_book
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Set the aggregation tick size.")
                        
                with dpg.menu(label="Levels"):
                    dpg.add_slider_int(
                        label="Levels",
                        default_value=self.order_book_levels,
                        min_value=5,
                        max_value=1000,
                        callback=self.set_ob_levels,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Change how many levels of the orderbook to show!")

            with dpg.plot(
                label="Orderbook", no_title=True, height=-1, width=-1
            ) as self.orderbook_tag:
                dpg.add_plot_legend()
                self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
                with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                    self.bids_tag = dpg.add_line_series([], [])
                    self.asks_tag = dpg.add_line_series([], [])

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
        self.order_book_levels = app_data
        
    def set_tick_size(self, sender, app_data, user_data):
        self.tick_size = app_data

    def on_order_book_update(self, tab, exchange, orderbook):
        if exchange == self.exchange and tab == self.tab:
            bids_df, ask_df, price_column = self.data.agg.on_order_book_update(
                exchange,
                orderbook,
                self.tick_size,
                self.aggregated_order_book,
            )
            self._update_order_book(bids_df, ask_df, price_column)

    def _update_order_book(self, bids_df, asks_df, price_column):
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

        # Calculate the midpoint between the best bid and best ask
        best_bid = bids_df[price_column].max()
        best_ask = asks_df[price_column].min()
        midpoint = (best_bid + best_ask) / 2

        # Determine the price range based on the number of levels
        if len(bids_df) >= self.order_book_levels and len(asks_df) >= self.order_book_levels:
            lower_bound_price = bids_df[price_column].nlargest(self.order_book_levels).min()
            upper_bound_price = asks_df[price_column].nsmallest(self.order_book_levels).max()
            price_range = max(midpoint - lower_bound_price, upper_bound_price - midpoint)
        else:
            # Fallback in case there are fewer levels than requested
            price_range = self.order_book_levels  # Set a default value

        # Update the x-axis limits based on the midpoint and calculated range
        dpg.set_axis_limits(axis=self.ob_xaxis, ymin=midpoint - price_range, ymax=midpoint + price_range)

        # The y-axis update remains the same
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=0, ymax=self.order_book_levels)



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
