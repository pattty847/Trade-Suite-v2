import asyncio
import logging
from typing import Dict, List
import math
from collections import defaultdict

import dearpygui.dearpygui as dpg
import time

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.components.test_ob import TestOB


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
        self.spread_percentage = 0.05 # 5%
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
        # logging.debug(f"[_on_order_book_update] Entered for tab {tab}") # Can be noisy
        if tab == self.tab:
            # No manual rate limiting needed here - CCXT/WebSocket handles update frequency
            # current_time = time.time()
            # time_since_last_update = current_time - self.last_update_time
            # if time_since_last_update < 0.05:
            #     return
            # self.last_update_time = current_time

            # Store a copy of the latest raw orderbook lists
            # Ensure bids/asks exist and are lists
            raw_bids = orderbook.get('bids', [])
            raw_asks = orderbook.get('asks', [])

            # Validate data format (optional but recommended)
            if not isinstance(raw_bids, list) or not isinstance(raw_asks, list):
                 logging.warning(f"Invalid orderbook data received for {self.symbol}: bids or asks not lists.")
                 return
                 
            # Store raw lists (avoid deep copy if not strictly needed elsewhere)
            self.last_orderbook = {
                "bids": raw_bids, #[list(bid) for bid in raw_bids],
                "asks": raw_asks, #[list(ask) for ask in raw_asks],
            }

            # Limit number of levels for performance
            max_levels = 100 # Consider making this configurable
            limited_bids = raw_bids[:max_levels]
            limited_asks = raw_asks[:max_levels]

            # Process the raw lists directly
            bids_processed, asks_processed = self._aggregate_and_group_order_book(
                limited_bids,
                limited_asks,
                self.tick_size,
                self.aggregated_order_book,
            )

            # Update the plot with processed lists
            self._update_order_book(bids_processed, asks_processed)

    def _aggregate_and_group_order_book(
        self, bids_raw: list, asks_raw: list, tick_size: float, aggregate: bool
    ):
        """Processes raw bid/ask lists, aggregates if requested, and calculates cumulative sums."""
        
        if aggregate:
            # Aggregate bids
            bids_grouped = defaultdict(float)
            for price, quantity in bids_raw:
                if tick_size > 0:
                    group = math.floor(price / tick_size) * tick_size
                    bids_grouped[group] += quantity
                else: # Avoid division by zero if tick_size is invalid
                    bids_grouped[price] += quantity
            # Sort descending by price, calculate cumulative
            bids_sorted = sorted(bids_grouped.items(), key=lambda item: item[0], reverse=True)
            bids_processed = []
            cumulative_qty = 0
            for price, quantity in bids_sorted:
                cumulative_qty += quantity
                bids_processed.append([price, quantity, cumulative_qty]) # [price, individual_qty, cumulative_qty]

            # Aggregate asks
            asks_grouped = defaultdict(float)
            for price, quantity in asks_raw:
                 if tick_size > 0:
                     group = math.floor(price / tick_size) * tick_size
                     asks_grouped[group] += quantity
                 else:
                     asks_grouped[price] += quantity
            # Sort ascending by price, calculate cumulative
            asks_sorted = sorted(asks_grouped.items(), key=lambda item: item[0])
            asks_processed = []
            cumulative_qty = 0
            for price, quantity in asks_sorted:
                cumulative_qty += quantity
                asks_processed.append([price, quantity, cumulative_qty]) # [price, individual_qty, cumulative_qty]

        else:
            # Non-aggregated: just sort
            # Sort bids descending by price
            bids_processed = sorted(bids_raw, key=lambda item: item[0], reverse=True)
             # Ensure format consistency: [price, quantity] (no cumulative here)
            bids_processed = [[p, q] for p, q in bids_processed]

            # Sort asks ascending by price
            asks_processed = sorted(asks_raw, key=lambda item: item[0])
             # Ensure format consistency: [price, quantity]
            asks_processed = [[p, q] for p, q in asks_processed]

        return bids_processed, asks_processed


    def _update_order_book(self, bids_processed: list, asks_processed: list):
        # Check if processed lists are empty
        if not bids_processed or not asks_processed:
            logging.debug(f"Order book empty or processing failed for {self.symbol}. Skipping update.")
            # Optionally clear the series if they are empty
            # dpg.set_value(self.bids_stair_tag, [[], []])
            # dpg.set_value(self.asks_stair_tag, [[], []])
            # dpg.set_value(self.bids_bar_tag, [[], []])
            # dpg.set_value(self.asks_bar_tag, [[], []])
            return

        # Extract data for plotting based on aggregation mode
        if self.aggregated_order_book:
            bid_prices = [item[0] for item in bids_processed]
            bid_quantities = [item[2] for item in bids_processed] # Use cumulative quantity (index 2)
            ask_prices = [item[0] for item in asks_processed]
            ask_quantities = [item[2] for item in asks_processed] # Use cumulative quantity (index 2)
        else:
            bid_prices = [item[0] for item in bids_processed]
            bid_quantities = [item[1] for item in bids_processed] # Use individual quantity (index 1)
            ask_prices = [item[0] for item in asks_processed]
            ask_quantities = [item[1] for item in asks_processed] # Use individual quantity (index 1)

        # Check for empty lists after extraction (can happen if processing results in empty lists)
        if not bid_prices or not ask_prices:
             logging.debug(f"Empty price/quantity lists after processing for {self.symbol}. Skipping DPG update.")
             return

        # Use container stack to batch all updates
        dpg.push_container_stack(self.orderbook_tag)

        # Update the appropriate series based on aggregation mode
        if self.aggregated_order_book:
            # Configure visibility if needed
            if not self.bids_stair_tag_visible or not self.asks_stair_tag_visible:
                dpg.configure_item(self.bids_stair_tag, show=True)
                dpg.configure_item(self.asks_stair_tag, show=True)
                dpg.configure_item(self.bids_bar_tag, show=False)
                dpg.configure_item(self.asks_bar_tag, show=False)
                self.bids_stair_tag_visible = True
                self.asks_stair_tag_visible = True
                self.bids_bar_tag_visible = False
                self.asks_bar_tag_visible = False
            
            # Update plot data
            dpg.set_value(self.bids_stair_tag, [bid_prices, bid_quantities])
            dpg.set_value(self.asks_stair_tag, [ask_prices, ask_quantities])
        else:
            # Configure visibility if needed
            if not self.bids_bar_tag_visible or not self.asks_bar_tag_visible:
                dpg.configure_item(self.bids_stair_tag, show=False)
                dpg.configure_item(self.asks_stair_tag, show=False)
                dpg.configure_item(self.bids_bar_tag, show=True)
                dpg.configure_item(self.asks_bar_tag, show=True)
                self.bids_stair_tag_visible = False
                self.asks_stair_tag_visible = False
                self.bids_bar_tag_visible = True
                self.asks_bar_tag_visible = True

            # Update plot data
            dpg.set_value(self.bids_bar_tag, [bid_prices, bid_quantities])
            dpg.set_value(self.asks_bar_tag, [ask_prices, ask_quantities])

        # Calculate midpoint, axis limits, and bid/ask ratio

        # Best bid is the highest price in bids_processed (first item after sorting desc)
        # Best ask is the lowest price in asks_processed (first item after sorting asc)
        best_bid = bids_processed[0][0] if bids_processed else 0
        best_ask = asks_processed[0][0] if asks_processed else 0

        if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid: # Added check for crossed book
            logging.warning(f"Invalid best bid/ask ({best_bid}/{best_ask}) for {self.symbol}. Skipping axis update.")
            dpg.pop_container_stack()
            return

        midpoint = (best_bid + best_ask) / 2
        price_range = midpoint * self.spread_percentage

        # Update x-axis limits
        new_xmin = midpoint - price_range
        new_xmax = midpoint + price_range

        # Optimize axis updates slightly - check for significant change
        if not hasattr(self, 'last_x_limits') or \
           abs(self.last_x_limits[0] - new_xmin) > 0.0005 * midpoint or \
           abs(self.last_x_limits[1] - new_xmax) > 0.0005 * midpoint: # Tighter threshold
            dpg.set_axis_limits(axis=self.ob_xaxis, ymin=new_xmin, ymax=new_xmax)
            self.last_x_limits = (new_xmin, new_xmax)

        # Calculate y-axis limits based on *visible* data within the price range
        if self.aggregated_order_book:
            # Use cumulative quantities for y-limit in aggregated view
            visible_bids_qty = [item[2] for item in bids_processed if item[0] >= new_xmin]
            visible_asks_qty = [item[2] for item in asks_processed if item[0] <= new_xmax]
            # Sum of individual quantities for bid/ask ratio
            visible_bids_indiv_qty_sum = sum(item[1] for item in bids_processed if item[0] >= new_xmin)
            visible_asks_indiv_qty_sum = sum(item[1] for item in asks_processed if item[0] <= new_xmax)
        else:
            # Use individual quantities for y-limit in non-aggregated view
            visible_bids_qty = [item[1] for item in bids_processed if item[0] >= new_xmin]
            visible_asks_qty = [item[1] for item in asks_processed if item[0] <= new_xmax]
            visible_bids_indiv_qty_sum = sum(visible_bids_qty) # Sum is the same here
            visible_asks_indiv_qty_sum = sum(visible_asks_qty) # Sum is the same here

        max_bid_y = max(visible_bids_qty) if visible_bids_qty else 0
        max_ask_y = max(visible_asks_qty) if visible_asks_qty else 0
        max_y_value = max(max_bid_y, max_ask_y, 0.1) # Ensure positive value, use 0.1 as minimum floor

        # Use a small buffer above the max_y_value
        buffer = max_y_value * 0.1 # 10% buffer
        # Optimize axis update - check if limits changed significantly
        current_y_limits = dpg.get_axis_limits(self.ob_yaxis)
        new_ymax = max_y_value + buffer
        # Check relative change to avoid jitter
        if abs(current_y_limits[1] - new_ymax) / new_ymax > 0.05: # Only update if > 5% change
             dpg.set_axis_limits(axis=self.ob_yaxis, ymin=0, ymax=new_ymax)


        # Calculate bid-ask ratio based on *sum* of individual quantities in the visible range
        if visible_asks_indiv_qty_sum > 0:
            bid_ask_ratio = visible_bids_indiv_qty_sum / visible_asks_indiv_qty_sum
        elif visible_bids_indiv_qty_sum > 0:
             bid_ask_ratio = float('inf') # Lots of bids, no asks visible
        else:
            bid_ask_ratio = 1.0 # Default or indicates no volume visible

        # Set the bid-ask ratio value
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
        self.aggregated_order_book = not self.aggregated_order_book
        dpg.configure_item(self.tick_size_slider_id, show=self.aggregated_order_book)

        # Refresh using the last raw data
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            bids_processed, asks_processed = self._aggregate_and_group_order_book(
                self.last_orderbook.get('bids', []), # Use .get for safety
                self.last_orderbook.get('asks', []),
                self.tick_size,
                self.aggregated_order_book,
            )
            self._update_order_book(bids_processed, asks_processed)

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
        # Ensure tick_size is positive
        if app_data <= 0:
             logging.warning(f"Attempted to set invalid tick size: {app_data}. Using previous value: {self.tick_size}")
             # Optionally reset slider value if possible or just don't update
             # dpg.set_value(self.tick_size_slider_id, self.tick_size) # Reset slider if needed
             return

        self.tick_size = app_data

        # Refresh the order book with the new tick size using last raw data
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            bids_processed, asks_processed = self._aggregate_and_group_order_book(
                self.last_orderbook.get('bids', []), # Use .get for safety
                self.last_orderbook.get('asks', []),
                self.tick_size,
                self.aggregated_order_book
            )
            self._update_order_book(bids_processed, asks_processed)
