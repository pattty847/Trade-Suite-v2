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
from trade_suite.analysis.orderbook_processor import OrderBookProcessor


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
        self.market_info = self.data.exchange_list[self.exchange].market(self.symbol)
        
        # Create the order book processor
        price_precision = self.market_info["precision"]["price"]
        self.processor = OrderBookProcessor(price_precision)
        
        # Track visibility state to avoid unnecessary configure_item calls
        self.bids_stair_tag_visible = True
        self.asks_stair_tag_visible = True
        self.bids_bar_tag_visible = False
        self.asks_bar_tag_visible = False
        self.last_x_limits = (0, 0)

        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
        self.emitter.register(Signals.SYMBOL_CHANGED, self._on_symbol_change)

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
                        default_value=self.processor.aggregation_enabled,
                        callback=self._toggle_aggregated_order_book,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Aggregates orderbook levels by the tick size.")

                with dpg.menu(label="Levels"):
                    self.spread_slider_id = dpg.add_slider_float(
                        label="Spread %",
                        default_value=self.processor.spread_percentage,
                        min_value=0.001,  # 0.1% minimum
                        max_value=0.2,    # 20% maximum - more reasonable range for most assets
                        format="%.3f",    # Show 3 decimal places for finer control
                        callback=self._set_ob_levels,
                    )
                    with dpg.tooltip(dpg.last_item()):
                        dpg.add_text("Change the midpoint spread %.")

            with dpg.group(horizontal=True):
                dpg.add_text(f"Bid/Ask Ratio: ")
                self.bid_ask_ratio = dpg.add_text("")

            with dpg.group(horizontal=True):
                dpg.add_text("Tick Size:")
                self.tick_display = dpg.add_text(f"{self.processor.tick_size:.8g}")  # Show current tick size
                dpg.add_button(label="-", callback=self._decrease_tick_size)
                dpg.add_button(label="+", callback=self._increase_tick_size)

            with dpg.plot(
                label="Orderbook", no_title=True, height=-1, width=-1
            ) as self.orderbook_tag:
                dpg.add_plot_legend()

                self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
                with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                    # Create series for both display modes
                    # Stair series for aggregated view
                    self.bids_stair_tag = dpg.add_stair_series(
                        [], [], label="Bids", show=self.processor.aggregation_enabled
                    )
                    self.asks_stair_tag = dpg.add_stair_series(
                        [], [], label="Asks", show=self.processor.aggregation_enabled
                    )
                    
                    # Bar series for non-aggregated view (individual orders)
                    self.bids_bar_tag = dpg.add_bar_series(
                        [], [], label="Bids", show=(not self.processor.aggregation_enabled), weight=0.5
                    )
                    self.asks_bar_tag = dpg.add_bar_series(
                        [], [], label="Asks", show=(not self.processor.aggregation_enabled), weight=0.5
                    )

    # Listens for order book emissions
    def _on_order_book_update(self, tab, exchange, orderbook):
        if tab == self.tab:
            # Extract raw data
            raw_bids = orderbook.get('bids', [])
            raw_asks = orderbook.get('asks', [])

            # Store raw data for reference
            self.last_orderbook = {
                "bids": raw_bids,
                "asks": raw_asks,
            }
            
            # Calculate current price for tick size operations
            current_price = None
            if raw_bids and raw_asks:
                best_bid = raw_bids[0][0]
                best_ask = raw_asks[0][0]
                current_price = (best_bid + best_ask) / 2
            
            # Process the orderbook using the processor
            processed_data = self.processor.process_orderbook(
                raw_bids, raw_asks, current_price
            )
            
            # Update the visualization if we have valid processed data
            if processed_data:
                self._update_visualization(processed_data)

    def _update_visualization(self, processed_data):
        """Update the orderbook visualization with processed data"""
        # Extract data from processor result
        bids_processed = processed_data["bids_processed"]
        asks_processed = processed_data["asks_processed"]
        x_limits = processed_data["x_axis_limits"]
        y_limits = processed_data["y_axis_limits"]
        bid_ask_ratio = processed_data["bid_ask_ratio"]
        
        # Update the appropriate series based on aggregation mode
        dpg.push_container_stack(self.orderbook_tag)
        
        if self.processor.aggregation_enabled:
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
            
            # Extract data for plotting
            bid_prices = [item[0] for item in bids_processed]
            bid_quantities = [item[2] for item in bids_processed]  # Use cumulative
            ask_prices = [item[0] for item in asks_processed]
            ask_quantities = [item[2] for item in asks_processed]  # Use cumulative
            
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

            # Extract data for plotting
            bid_prices = [item[0] for item in bids_processed]
            bid_quantities = [item[1] for item in bids_processed]  # Use individual
            ask_prices = [item[0] for item in asks_processed]
            ask_quantities = [item[1] for item in asks_processed]  # Use individual
            
            # Update plot data
            dpg.set_value(self.bids_bar_tag, [bid_prices, bid_quantities])
            dpg.set_value(self.asks_bar_tag, [ask_prices, ask_quantities])

        # Update axis limits
        x_min, x_max = x_limits
        
        # Only update x-axis if there's a significant change to avoid jitter
        if not hasattr(self, 'last_x_limits') or \
           abs(self.last_x_limits[0] - x_min) > 0.0005 * processed_data["midpoint"] or \
           abs(self.last_x_limits[1] - x_max) > 0.0005 * processed_data["midpoint"]:
            dpg.set_axis_limits(axis=self.ob_xaxis, ymin=x_min, ymax=x_max)
            self.last_x_limits = (x_min, x_max)
            
        # Update y-axis limits
        y_min, y_max = y_limits
        current_y_limits = dpg.get_axis_limits(self.ob_yaxis)
        
        # Only update if substantial change
        if abs(current_y_limits[1] - y_max) / y_max > 0.05:
            dpg.set_axis_limits(axis=self.ob_yaxis, ymin=y_min, ymax=y_max)

        # Update the bid-ask ratio text
        dpg.set_value(self.bid_ask_ratio, f"{bid_ask_ratio:.2f}")
        
        # Finish batched updates
        dpg.pop_container_stack()

    def _toggle_show_hide_orderbook(self):
        self.show_orderbook = not self.show_orderbook
        if self.show_orderbook:
            dpg.configure_item(self.order_book_group, show=self.show_orderbook)
            dpg.configure_item(self.charts_group, width=dpg.get_viewport_width() * 0.7)
            
            # Inform the parent Chart class that the orderbook was shown
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

    def _toggle_aggregated_order_book(self):
        # Use processor to toggle aggregation
        self.processor.toggle_aggregation()
        
        # Refresh using the last raw data
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            self._on_order_book_update(self.tab, self.exchange, self.last_orderbook)

    def _set_ob_levels(self, sender, app_data, user_data):
        # Update the spread percentage via processor
        self.processor.set_spread_percentage(app_data)
        
        # If we have order book data, refresh the display
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            self._on_order_book_update(self.tab, self.exchange, self.last_orderbook)

    def _on_symbol_change(self, exchange, tab, new_symbol):
        if tab != self.tab or exchange != self.exchange:
            return
            
        self.symbol = new_symbol
        self.market_info = self.data.exchange_list[self.exchange].market(self.symbol)
        
        # Update processor with new price precision
        price_precision = self.market_info["precision"]["price"]
        self.processor.price_precision = price_precision
        self.processor.set_tick_size(price_precision)
        
        # Update tick display
        dpg.set_value(self.tick_display, f"{self.processor.tick_size:.8g}")

    def _decrease_tick_size(self):
        # Get current price if available
        current_price = None
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            bids = self.last_orderbook.get('bids', [])
            asks = self.last_orderbook.get('asks', [])
            if bids and asks:
                current_price = (bids[0][0] + asks[0][0]) / 2
        
        # Use processor to decrease tick size
        new_tick_size = self.processor.decrease_tick_size(current_price)
        dpg.set_value(self.tick_display, f"{new_tick_size:.8g}")
        
        # Refresh orderbook display
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            self._on_order_book_update(self.tab, self.exchange, self.last_orderbook)

    def _increase_tick_size(self):
        # Get current price if available
        current_price = None
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            bids = self.last_orderbook.get('bids', [])
            asks = self.last_orderbook.get('asks', [])
            if bids and asks:
                current_price = (bids[0][0] + asks[0][0]) / 2
        
        # Use processor to increase tick size
        new_tick_size = self.processor.increase_tick_size(current_price)
        dpg.set_value(self.tick_display, f"{new_tick_size:.8g}")
        
        # Refresh orderbook display
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            self._on_order_book_update(self.tab, self.exchange, self.last_orderbook)
