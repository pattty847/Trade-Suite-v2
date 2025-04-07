import json
import logging
import dearpygui.dearpygui as dpg
import pandas as pd
import time

from config import ConfigManager
from data.data_source import Data
from gui.signals import SignalEmitter, Signals
from gui.components.test_ob import TestOB


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
        self.aggregated_order_book = True
        self.spread_percentage = 0.005
        self.tick_size = 0.01
        self.market_info = self.data.exchange_list[self.exchange].market(self.symbol)
        
        # Track visibility state to avoid unnecessary configure_item calls
        self.bids_stair_tag_visible = True
        self.asks_stair_tag_visible = True
        self.bids_bar_tag_visible = False
        self.asks_bar_tag_visible = False
        self.last_x_limits = (0, 0)
        
        # Track last update time to limit update frequency if needed
        self.last_update_time = 0

        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
        self.emitter.register(Signals.SYMBOL_CHANGED, self._on_symbol_change)
        # self.emitter.register(Signals.NEW_TRADE, self._on_trade)

        self._update_tick_size(None, None, self.symbol)

    def setup_orderbook_menu(self):
        with dpg.menu(label="Orderbook"):
            dpg.add_checkbox(
                label="Show",
                default_value=self.show_orderbook,
                callback=self._toggle_show_hide_orderbook,
            )

    def draw_orderbook_plot(self):
        with dpg.child_window(menubar=True, width=-1):
            with dpg.menu_bar():

                with dpg.menu(label="Aggregate"):
                    dpg.add_checkbox(
                        label="Toggle",
                        default_value=self.aggregated_order_book,
                        callback=self._toggle_aggregated_order_book,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Aggregates orderbook levels by the tick size.")

                    # TICK SIZE SLIDER - improved with better range and format
                    self.tick_size_slider_id = dpg.add_slider_float(
                        label="Tick Size",
                        default_value=self.market_info["precision"]["price"],
                        callback=self._set_tick_size,
                        min_value=self.market_info["precision"]["price"],
                        max_value=max(100, self.market_info["precision"]["price"] * 1000),
                        format="%.5f",
                        show=self.aggregated_order_book,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text(
                            "Set the aggregation tick size (CTRL+CLICK to enter size)"
                        )

                with dpg.menu(label="Levels"):
                    dpg.add_slider_float(
                        label="Spread %",
                        default_value=self.spread_percentage,
                        min_value=0,
                        max_value=1,
                        callback=self._set_ob_levels,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Change the midpoint spread %.")

            with dpg.group(horizontal=True):
                dpg.add_text(f"Bid/Ask Ratio: ")
                self.bid_ask_ratio = dpg.add_text("")

            with dpg.plot(
                label="Orderbook", no_title=True, height=-1, width=-1
            ) as self.orderbook_tag:
                dpg.add_plot_legend()

                self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
                with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                    # Create series for both display modes
                    # Stair series for aggregated view
                    self.bids_stair_tag = dpg.add_stair_series(
                        [], [], label="Bids", show=self.aggregated_order_book
                    )
                    self.asks_stair_tag = dpg.add_stair_series(
                        [], [], label="Asks", show=self.aggregated_order_book
                    )
                    
                    # Bar series for non-aggregated view (individual orders)
                    self.bids_bar_tag = dpg.add_bar_series(
                        [], [], label="Bids", show=(not self.aggregated_order_book), weight=0.5
                    )
                    self.asks_bar_tag = dpg.add_bar_series(
                        [], [], label="Asks", show=(not self.aggregated_order_book), weight=0.5
                    )

    # Listens for order book emissions
    def _on_order_book_update(self, tab, exchange, orderbook):
        logging.debug(f"[_on_order_book_update] Entered for tab {tab}")
        if tab == self.tab:
            # Apply rate limiting - only process updates at most once every 0.05 seconds (20 fps)
            current_time = time.time()
            time_since_last_update = current_time - self.last_update_time
            
            if time_since_last_update < 0.05:  # 50ms between updates (20fps)
                # Too soon since last update, skip this one
                return
                
            # Update the timestamp for rate limiting
            self.last_update_time = current_time
        
            # Store a copy of the latest orderbook for refreshing when settings change
            self.last_orderbook = {
                "bids": [list(bid) for bid in orderbook["bids"]],
                "asks": [list(ask) for ask in orderbook["asks"]],
            }
            
            # Only process limited number of levels for better performance
            # For large orderbooks, limiting to 100 levels per side is usually sufficient
            max_levels = 100
            limited_orderbook = {
                "bids": orderbook["bids"][:max_levels] if len(orderbook["bids"]) > max_levels else orderbook["bids"],
                "asks": orderbook["asks"][:max_levels] if len(orderbook["asks"]) > max_levels else orderbook["asks"]
            }
            
            # Pass the 'self.aggregated_order_book' to determine if aggregation is needed
            bids_df, asks_df, price_column = self._aggregate_and_group_order_book(
                limited_orderbook,
                self.tick_size,
                self.aggregated_order_book,
            )

            # Whether aggregated or not, update the order book display
            self._update_order_book(bids_df, asks_df, price_column)

    def _aggregate_and_group_order_book(
        self, orderbook, tick_size, aggregate
    ):
        # Extract bids and asks
        bids = orderbook["bids"]
        asks = orderbook["asks"]

        if aggregate:
            # Process for aggregated view
            bids_df = self._group_and_aggregate(bids, tick_size)
            asks_df = self._group_and_aggregate(asks, tick_size)
            price_column = "price_group"
        else:
            # Process for non-aggregated view
            bids_df = pd.DataFrame(bids, columns=["price", "quantity"])
            asks_df = pd.DataFrame(asks, columns=["price", "quantity"])
            price_column = "price"

        # Sorting
        bids_df = bids_df.sort_values(by=price_column, ascending=False)
        asks_df = asks_df.sort_values(by=price_column, ascending=True)

        # Calculate cumulative quantities only if aggregated
        if aggregate:
            bids_df["cumulative_quantity"] = bids_df["quantity"].cumsum()
            asks_df["cumulative_quantity"] = asks_df["quantity"].cumsum()

        # Update the series data
        return bids_df, asks_df, price_column


    def _group_and_aggregate(self, orders, tick_size):
        # Make a defensive copy of the orders to prevent race conditions
        try:
            # Check if there are any orders
            if not orders:
                return pd.DataFrame(columns=["price_group", "quantity"])
                
            # Make a copy of the orders list to avoid race conditions
            orders_copy = list(orders)
            
            # Verify that each order has exactly 2 elements [price, quantity]
            valid_orders = [order for order in orders_copy if len(order) == 2]
            
            # Create DataFrame from the valid orders
            df = pd.DataFrame(valid_orders, columns=["price", "quantity"])
            
            # Calculate the price group
            df["price_group"] = (df["price"] // tick_size) * tick_size
            
            # Group and aggregate
            return df.groupby("price_group").agg({"quantity": "sum"}).reset_index()
        except Exception as e:
            logging.error(f"Error in _group_and_aggregate: {e}")
            # Return empty DataFrame with correct structure if there's an error
            return pd.DataFrame(columns=["price_group", "quantity"])


    def _update_order_book(self, bids_df, asks_df, price_column):
        # Get price and quantity data based on the chosen view
        bid_prices = bids_df[price_column].tolist()
        ask_prices = asks_df[price_column].tolist()
        
        # Get quantities based on view mode
        if self.aggregated_order_book and "cumulative_quantity" in bids_df:
            bid_quantities = bids_df["cumulative_quantity"].tolist()
            ask_quantities = asks_df["cumulative_quantity"].tolist()
        else:
            bid_quantities = bids_df["quantity"].tolist()
            ask_quantities = asks_df["quantity"].tolist()

        # Use container stack to batch all updates
        dpg.push_container_stack(self.orderbook_tag)

        # Update the appropriate series based on aggregation mode
        if self.aggregated_order_book:
            # Only update visibility if needed - minimize configuration changes
            if self.bids_stair_tag_visible != True or self.asks_stair_tag_visible != True:
                # Configure visibility once
                dpg.configure_item(self.bids_stair_tag, show=True)
                dpg.configure_item(self.asks_stair_tag, show=True)
                dpg.configure_item(self.bids_bar_tag, show=False)
                dpg.configure_item(self.asks_bar_tag, show=False)
                self.bids_stair_tag_visible = True
                self.asks_stair_tag_visible = True
                self.bids_bar_tag_visible = False
                self.asks_bar_tag_visible = False
            
            # Use set_value for faster updates
            dpg.set_value(self.bids_stair_tag, [bid_prices, bid_quantities])
            dpg.set_value(self.asks_stair_tag, [ask_prices, ask_quantities])
        else:
            # Only update visibility if needed
            if self.bids_bar_tag_visible != True or self.asks_bar_tag_visible != True:
                dpg.configure_item(self.bids_stair_tag, show=False)
                dpg.configure_item(self.asks_stair_tag, show=False)
                dpg.configure_item(self.bids_bar_tag, show=True)
                dpg.configure_item(self.asks_bar_tag, show=True)
                self.bids_stair_tag_visible = False
                self.asks_stair_tag_visible = False
                self.bids_bar_tag_visible = True
                self.asks_bar_tag_visible = True
            
            # Use set_value for faster updates
            dpg.set_value(self.bids_bar_tag, [bid_prices, bid_quantities])
            dpg.set_value(self.asks_bar_tag, [ask_prices, ask_quantities])

        # Calculate the midpoint between the best bid and best ask
        best_bid = bids_df[price_column].max() if not bids_df.empty else 0
        best_ask = asks_df[price_column].min() if not asks_df.empty else 0
        
        # Safety check to prevent division issues when orderbook is empty
        if best_bid == 0 or best_ask == 0:
            dpg.pop_container_stack()
            return
            
        midpoint = (best_bid + best_ask) / 2
        price_range = midpoint * self.spread_percentage

        # Update the x-axis limits based on the midpoint and calculated range
        # Only update x-axis if values changed significantly
        new_xmin = midpoint - price_range
        new_xmax = midpoint + price_range
        
        if not hasattr(self, 'last_x_limits') or \
           abs(self.last_x_limits[0] - new_xmin) > 0.001 * midpoint or \
           abs(self.last_x_limits[1] - new_xmax) > 0.001 * midpoint:
            dpg.set_axis_limits(axis=self.ob_xaxis, ymin=new_xmin, ymax=new_xmax)
            self.last_x_limits = (new_xmin, new_xmax)

        # Calculate the y-axis limits
        visible_bids = bids_df[bids_df[price_column] >= midpoint - price_range]
        visible_asks = asks_df[asks_df[price_column] <= midpoint + price_range]

        # Calculate max height based on view mode and available data
        if self.aggregated_order_book and "cumulative_quantity" in bids_df and "cumulative_quantity" in asks_df and \
           not visible_bids.empty and not visible_asks.empty:
            max_bid_quantity = visible_bids["cumulative_quantity"].max()
            max_ask_quantity = visible_asks["cumulative_quantity"].max()
        elif not visible_bids.empty and not visible_asks.empty:
            max_bid_quantity = visible_bids["quantity"].max()
            max_ask_quantity = visible_asks["quantity"].max()
        else:
            # Default if no data available
            max_bid_quantity = max_ask_quantity = 0

        max_y_value = max(max_bid_quantity, max_ask_quantity, 0.1)  # Ensure positive value

        # Use a small buffer above the max_y_value for better visual spacing
        buffer = max_y_value * 0.1  # 10% buffer
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=0, ymax=max_y_value + buffer)

        # Calculate the visible bid and ask quantities
        if not visible_bids.empty and not visible_asks.empty:
            visible_bid_quantities = visible_bids[
                "cumulative_quantity" if self.aggregated_order_book and "cumulative_quantity" in visible_bids else "quantity"
            ].sum()
            visible_ask_quantities = visible_asks[
                "cumulative_quantity" if self.aggregated_order_book and "cumulative_quantity" in visible_asks else "quantity"
            ].sum()

            # Calculate bid-ask ratio for visible quantities
            if visible_ask_quantities > 0:  # Prevent division by zero
                bid_ask_ratio = visible_bid_quantities / visible_ask_quantities
            else:
                bid_ask_ratio = float("inf")
        else:
            bid_ask_ratio = 1.0  # Default value when no data

        # Set the bid-ask ratio value in the UI
        dpg.set_value(self.bid_ask_ratio, f"{bid_ask_ratio:.2f}")
        
        # Finish batched updates
        dpg.pop_container_stack()

    def _toggle_show_hide_orderbook(self):
        self.show_orderbook = not self.show_orderbook
        if self.show_orderbook:
            dpg.configure_item(self.order_book_group, show=self.show_orderbook)
            dpg.configure_item(self.charts_group, width=dpg.get_viewport_width() * 0.7)
            
            # Inform the parent Chart class that the orderbook was shown
            # This will be handled through a signal
            self.emitter.emit(
                Signals.ORDERBOOK_VISIBILITY_CHANGED,
                tab=self.tab,
                exchange=self.exchange,
                symbol=self.symbol,
                visible=True
            )
        else:
            dpg.configure_item(self.order_book_group, width=-1)
            dpg.configure_item(self.charts_group, width=-1)
            
            # Inform the parent Chart class that the orderbook was hidden
            self.emitter.emit(
                Signals.ORDERBOOK_VISIBILITY_CHANGED,
                tab=self.tab,
                exchange=self.exchange,
                symbol=self.symbol,
                visible=False
            )

    # Rest of the methods related to order book (update_order_book, set_ob_levels, etc.)

    def _toggle_aggregated_order_book(self):
        # Toggle the aggregation flag
        self.aggregated_order_book = not self.aggregated_order_book
        
        # Show/hide the tick size slider based on aggregation mode
        dpg.configure_item(self.tick_size_slider_id, show=self.aggregated_order_book)
        
        # Request a refresh of the order book with the current data
        # This will apply the new aggregation setting to the current data
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            bids_df, asks_df, price_column = self._aggregate_and_group_order_book(
                self.last_orderbook,
                self.tick_size,
                self.aggregated_order_book,
            )
            self._update_order_book(bids_df, asks_df, price_column)
            
    def _set_ob_levels(self, sender, app_data, user_data):
        self.spread_percentage = app_data

    def _on_symbol_change(self, exchange, tab, new_symbol):
        self.symbol = new_symbol

        self.market_info = self.data.exchange_list[self.exchange].market(self.symbol)

        self._update_tick_size(exchange, tab, self.symbol)

    def _update_tick_size(self, exchange, tab, new_symbol):
        price_precision = self.market_info["precision"]["price"]
        self._set_tick_size(None, price_precision, None)

    def _set_tick_size(self, sender, app_data: float, user_data):
        # Update the tick size
        self.tick_size = app_data
        
        # Refresh the order book with the new tick size
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            bids_df, asks_df, price_column = self._aggregate_and_group_order_book(
                self.last_orderbook, 
                self.tick_size,
                self.aggregated_order_book
            )
            self._update_order_book(bids_df, asks_df, price_column)
