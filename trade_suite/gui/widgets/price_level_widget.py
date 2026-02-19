import dearpygui.dearpygui as dpg
import logging
import time
from typing import Dict, List, Optional, Any, TYPE_CHECKING

import numpy as np  # Local import to avoid global dependency issues if NumPy is unavailable at import time

from .base_widget import DockableWidget
from ...core.facade import CoreServicesFacade
from ...analysis.orderbook_processor import OrderBookProcessor
from ...core.signals import Signals

# Forward declaration for type hinting
if TYPE_CHECKING:
    from trade_suite.core.task_manager import TaskManager


class PriceLevelWidget(DockableWidget):
    """
    Widget for displaying aggregated order book depth in a table format (Price Levels / DOM).
    """
    WIDGET_TYPE = "price_level"
    WIDGET_TITLE = "Price Levels"

    def __init__(
        self,
        core: CoreServicesFacade,
        instance_id: str,
        exchange: str,
        symbol: str,
        max_depth: int = 15,
        default_tick_size: float = 1.0,
        width: int = 250,
        height: int = 600,
        **kwargs,
    ):
        """
        Initialize a Price Level widget.

        Args:
            core: The core services facade.
            instance_id: Unique identifier for this widget instance.
            exchange: Exchange name (e.g., 'coinbase')
            symbol: Trading pair (e.g., 'BTC/USD')
            max_depth: Number of price levels to show on each side
            default_tick_size: Initial aggregation level
            width: Initial widget width
            height: Initial widget height
        """
        self.WIDGET_TITLE = f"Levels - {exchange.upper()} {symbol}"
        
        super().__init__(
            core=core,
            instance_id=instance_id,
            width=width,
            height=height,
            **kwargs,
        )

        # Configuration
        self.exchange = exchange
        self.symbol = symbol
        self.max_depth = max_depth
        self.tick_size = default_tick_size

        # Price precision (could be fetched from exchange later); use tick_size as baseline
        self.price_precision = default_tick_size if default_tick_size > 0 else 0.01

        # Use shared OrderBookProcessor for fast NumPy aggregation & cumulative calcs
        self.processor = OrderBookProcessor(price_precision=self.price_precision, initial_tick_size=self.tick_size)

        # UI Tags
        self.table_tag = f"{self.window_tag}_table"
        self.tick_slider_tag = f"{self.window_tag}_tick_slider"

        # Cell storage: Each entry will be (price_cell_tag, quantity_cell_tag)
        self.ask_cells: List[tuple[int, int]] = []
        self.bid_cells: List[tuple[int, int]] = []
        self.spread_cell: Optional[int] = None # Only need one text item for spread row

        # Last seen orderbook data - store for refreshing on tick size change
        self.last_orderbook = None

        # Performance optimization - track last update time for rate limiting
        self.last_update_time = 0
        self.update_interval = 0.05  # Minimum time between updates (seconds)

        # Dictionary to store the last color/value for each cell for optimization
        self.last_colors = {}
        self.last_values = {} # Store last text value set for optimization

    def get_requirements(self) -> Dict[str, Any]:
        """Define the data requirements for the PriceLevelWidget."""
        # Needs order book data
        return {
            "type": "orderbook",
            "exchange": self.exchange,
            "symbol": self.symbol,
        }

    def get_config(self) -> Dict[str, Any]:
        """Returns the configuration needed to recreate this PriceLevelWidget."""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "max_depth": self.max_depth,
            "default_tick_size": self.tick_size, # Use current tick_size with correct init param name
        }

    def build_content(self) -> None:
        """Build the price level widget's content."""
        # Add tick size control
        dpg.add_slider_float(
            label="Tick Size",
            tag=self.tick_slider_tag,
            default_value=self.tick_size,
            min_value=0.0001, # Allow finer ticks
            max_value=10000.0, # Allow larger ticks
            format="%.4f", # Show more precision
            callback=self._on_tick_size_change,
            width=-1 # Take full width
        )

        # Create the table with clipper=True for better performance
        with dpg.table(
            header_row=True,
            resizable=True,
            borders_innerH=True,
            borders_innerV=True,
            borders_outerH=True,
            borders_outerV=True,
            clipper=True,
            delay_search=True,
            tag=self.table_tag,
            # Set height=-1 to fill available space below slider
            height=-1,
            width=-1
        ) as self.table_id: # Keep table_id for potential direct reference if needed
            # Add columns for price and quantity
            dpg.add_table_column(label="Price")
            dpg.add_table_column(label="Quantity")

            # Pre-allocate cell storage
            self.ask_cells = []
            self.bid_cells = []

            # Create ask rows (top-to-bottom, highest ask at bottom of asks section)
            for i in range(self.max_depth):
                with dpg.table_row():
                    price_cell = dpg.add_text("", color=[200, 100, 100])
                    qty_cell = dpg.add_text("", color=[200, 100, 100])
                    self.ask_cells.append((price_cell, qty_cell))

            # Create spread row
            with dpg.table_row():
                self.spread_cell = dpg.add_text("Spread: --")
                # Empty cell for alignment in the quantity column
                dpg.add_text("")

            # Create bid rows (top-to-bottom, highest bid at top of bids section)
            for i in range(self.max_depth):
                with dpg.table_row():
                    price_cell = dpg.add_text("", color=[100, 200, 100])
                    qty_cell = dpg.add_text("", color=[100, 200, 100])
                    self.bid_cells.append((price_cell, qty_cell))

    def register_handlers(self) -> None:
        """Register event handlers for signals."""
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)

    def _on_order_book_update(self, exchange: str, orderbook: dict):
        """Process an order book update signal."""
        # Check if this update is for the correct market and widget is ready
        orderbook_symbol = orderbook.get('symbol')
        if not self.is_created or exchange != self.exchange or orderbook_symbol != self.symbol:
            # Log for debugging, might remove later
            # if self.is_created:
            #     logging.debug(f"PLWidget {self.window_tag} ignoring update for {exchange}/{orderbook_symbol}")
            return
        
        # Log for debugging, might remove later
        # logging.debug(f"PLWidget {self.window_tag} processing update for {self.exchange}/{self.symbol}")

        # Always store the latest orderbook data (even if we skip rendering)
        self.last_orderbook = orderbook

        # Apply rate limiting
        current_time = time.time()
        if (current_time - self.last_update_time) < self.update_interval:
            return # Too soon since last update

        # Update the timestamp for rate limiting
        self.last_update_time = current_time

        # Process and display the order book
        self._process_and_display_orderbook(orderbook)

    def _process_and_display_orderbook(self, orderbook):
        """Aggregate and display the order book data in the table."""
        if not orderbook or not self.is_created:
            return

        raw_bids = orderbook.get("bids", [])
        raw_asks = orderbook.get("asks", [])

        # Estimate midpoint for processor helper (optional but helps spread logic)
        current_price = None
        if raw_bids and raw_asks:
            current_price = (raw_bids[0][0] + raw_asks[0][0]) / 2

        processed = self.processor.process_orderbook(raw_bids, raw_asks, current_price)
        if not processed:
            return

        import numpy as _np  # local alias to avoid global import cost each call

        # -----------------------------
        # Fast-path: work directly with NumPy views that are already sorted by
        # OrderBookProcessor (_vector_aggregate guarantees bids DESC, asks ASC).
        # -----------------------------
        bids_arr = _np.asarray(processed["bids_processed"], dtype=_np.float64)
        asks_arr = _np.asarray(processed["asks_processed"], dtype=_np.float64)

        # Slice out only price & *individual* qty columns (col 0,1).  No Python
        # object creation, just a view.
        bids_agg = bids_arr[:, :2]
        asks_agg = asks_arr[:, :2]

        # We want highest-priced ask at top, so take last N rows and reverse.
        asks_display = asks_agg[-self.max_depth:][::-1]

        # Calculate spread
        best_bid_price = bids_agg[0, 0] if bids_agg.size else 0
        best_ask_price = asks_agg[0, 0] if asks_agg.size else 0
        spread = best_ask_price - best_bid_price if best_ask_price and best_bid_price else 0

        # Update ask cells (display highest asks first, going down)
        for i in range(self.max_depth):
            # Ensure the table and cells still exist
            if not dpg.does_item_exist(self.table_tag) or i >= len(self.ask_cells):
                logging.warning(f"Ask cell {i} or table no longer exists for {self.window_tag}")
                break
            price_cell, qty_cell = self.ask_cells[i]
            if not dpg.does_item_exist(price_cell): continue # Cell might be deleted

            if i < asks_display.shape[0]:
                price, quantity = asks_display[i, 0], asks_display[i, 1]
                # Highlight best ask (which is the last element in asks_display)
                is_best_ask = (i == len(asks_display) - 1)
                color = [255, 80, 80] if is_best_ask else [200, 100, 100]

                # Pre-format outside DPG calls to avoid duplicate work
                new_price_str = f"{price:,.8g}"
                new_qty_str = f"{quantity:,.8g}"

                if self.last_values.get(price_cell) != new_price_str:
                    dpg.set_value(price_cell, new_price_str)
                    self.last_values[price_cell] = new_price_str
                if self.last_values.get(qty_cell) != new_qty_str:
                    dpg.set_value(qty_cell, new_qty_str)
                    self.last_values[qty_cell] = new_qty_str

                # Update color only if changed
                if self.last_colors.get(price_cell) != color:
                    dpg.configure_item(price_cell, color=color)
                    dpg.configure_item(qty_cell, color=color)
                    self.last_colors[price_cell] = color
            else:
                # Clear unused cells only if they aren't already cleared
                if self.last_values.get(price_cell) != "":
                    dpg.set_value(price_cell, "")
                    self.last_values[price_cell] = ""
                if self.last_values.get(qty_cell) != "":
                    dpg.set_value(qty_cell, "")
                    self.last_values[qty_cell] = ""
                # Also ensure color cache reflects cleared state
                if self.last_colors.get(price_cell) is not None:
                    self.last_colors[price_cell] = None

        # Update spread cell only if changed
        if self.spread_cell and dpg.does_item_exist(self.spread_cell):
            new_spread_str = f"Spread: {spread:,.8g}"
            if self.last_values.get(self.spread_cell) != new_spread_str:
                dpg.set_value(self.spread_cell, new_spread_str)
                self.last_values[self.spread_cell] = new_spread_str

        # Update bid cells (display highest bids first, going down)
        for i in range(self.max_depth):
             # Ensure the table and cells still exist
            if not dpg.does_item_exist(self.table_tag) or i >= len(self.bid_cells):
                logging.warning(f"Bid cell {i} or table no longer exists for {self.window_tag}")
                break
            price_cell, qty_cell = self.bid_cells[i]
            if not dpg.does_item_exist(price_cell): continue

            if i < bids_agg.shape[0]:
                price, quantity = bids_agg[i, 0], bids_agg[i, 1]
                # Highlight best bid (first element in bids_agg)
                is_best_bid = (i == 0)
                color = [80, 255, 80] if is_best_bid else [100, 200, 100]

                # Pre-format outside DPG calls to avoid duplicate work
                new_price_str = f"{price:,.8g}"
                new_qty_str = f"{quantity:,.8g}"

                if self.last_values.get(price_cell) != new_price_str:
                    dpg.set_value(price_cell, new_price_str)
                    self.last_values[price_cell] = new_price_str
                if self.last_values.get(qty_cell) != new_qty_str:
                    dpg.set_value(qty_cell, new_qty_str)
                    self.last_values[qty_cell] = new_qty_str

                # Update color only if changed
                if self.last_colors.get(price_cell) != color:
                    dpg.configure_item(price_cell, color=color)
                    dpg.configure_item(qty_cell, color=color)
                    self.last_colors[price_cell] = color
            else:
                # Clear unused cells only if they aren't already cleared
                if self.last_values.get(price_cell) != "":
                    dpg.set_value(price_cell, "")
                    self.last_values[price_cell] = ""
                if self.last_values.get(qty_cell) != "":
                    dpg.set_value(qty_cell, "")
                    self.last_values[qty_cell] = ""
                # Also ensure color cache reflects cleared state
                if self.last_colors.get(price_cell) is not None:
                    self.last_colors[price_cell] = None

    def _on_tick_size_change(self, sender, app_data, user_data):
        """Handle tick size slider changes."""
        self.tick_size = app_data
        # Keep processor in sync
        self.processor.set_tick_size(self.tick_size)
        # Reprocess the last known orderbook with the new tick size immediately
        if self.last_orderbook:
            self._process_and_display_orderbook(self.last_orderbook)

    def close(self) -> None:
        """Clean up price level specific resources before closing."""
        logging.info(f"Closing PriceLevelWidget: {self.window_tag}")
        # Add any specific cleanup here before calling base class close
        super().close() # Call base class close to handle unsubscription and DPG item deletion 