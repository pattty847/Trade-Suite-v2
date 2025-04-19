import logging
import dearpygui.dearpygui as dpg
import numpy as np
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget
from trade_suite.analysis.orderbook_processor import OrderBookProcessor

# Forward declaration for type hinting
if TYPE_CHECKING:
    from trade_suite.gui.task_manager import TaskManager


class OrderbookWidget(DockableWidget):
    """
    Widget for displaying and interacting with order book data.
    """
    
    def __init__(
        self,
        emitter: SignalEmitter,
        task_manager: 'TaskManager',
        exchange: str,
        symbol: str,
        instance_id: Optional[str] = None,
        width: int = 400,
        height: int = 500,
    ):
        """
        Initialize an order book widget.
        
        Args:
            emitter: Signal emitter
            task_manager: Task manager instance
            exchange: Exchange name (e.g., 'coinbase')
            symbol: Trading pair (e.g., 'BTC/USD')
            instance_id: Optional unique instance identifier
            width: Initial widget width
            height: Initial widget height
        """
        # Create a unique ID if not provided
        if instance_id is None:
            instance_id = f"{exchange}_{symbol}".lower().replace("/", "")
            
        super().__init__(
            title=f"Orderbook - {exchange.upper()} {symbol}",
            widget_type="orderbook",
            emitter=emitter,
            task_manager=task_manager,
            instance_id=instance_id,
            width=width,
            height=height,
        )
        
        # Configuration
        self.exchange = exchange
        self.symbol = symbol
        
        # Get market info for price precision
        self.price_precision = 0.01  # Default
        
        # Initialize the orderbook processor
        self.processor = OrderBookProcessor(self.price_precision)
        
        # UI components
        self.orderbook_plot_tag = f"{self.window_tag}_plot"
        self.ob_xaxis_tag = f"{self.window_tag}_xaxis"
        self.ob_yaxis_tag = f"{self.window_tag}_yaxis"
        self.bids_stair_tag = f"{self.window_tag}_bids_stair"
        self.asks_stair_tag = f"{self.window_tag}_asks_stair"
        self.bids_bar_tag = f"{self.window_tag}_bids_bar"
        self.asks_bar_tag = f"{self.window_tag}_asks_bar"
        
        # Track visibility state to avoid unnecessary configure_item calls
        self.bids_stair_tag_visible = True
        self.asks_stair_tag_visible = True
        self.bids_bar_tag_visible = False
        self.asks_bar_tag_visible = False
        
        # Last data
        self.last_orderbook = None
        self.last_x_limits = (0, 0)
    
    def get_requirements(self) -> Dict[str, Any]:
        """Define the data requirements for the OrderbookWidget."""
        return {
            "type": "orderbook",
            "exchange": self.exchange,
            "symbol": self.symbol,
            # No timeframe needed for orderbook
        }
    
    def build_menu(self) -> None:
        """Build the order book widget's menu bar."""
        with dpg.menu(label="Aggregate"):
            dpg.add_checkbox(
                label="Enable",
                default_value=self.processor.aggregation_enabled,
                callback=self._toggle_aggregated_order_book,
            )
            
        with dpg.menu(label="Levels"):
            self.spread_slider_id = dpg.add_slider_float(
                label="Spread %",
                default_value=self.processor.spread_percentage,
                min_value=0.001,  # 0.1% minimum
                max_value=0.2,    # 20% maximum
                format="%.3f",
                callback=self._set_ob_levels,
            )
    
    def build_content(self) -> None:
        """Build the order book widget's content."""
        # Top info section
        with dpg.group(horizontal=True):
            dpg.add_text("Bid/Ask Ratio: ")
            self.bid_ask_ratio = dpg.add_text("1.00")
        
        # Tick size controls
        with dpg.group(horizontal=True):
            dpg.add_text("Tick Size:")
            self.tick_display = dpg.add_text(f"{self.processor.tick_size:.8g}")
            dpg.add_button(label="-", callback=self._decrease_tick_size)
            dpg.add_button(label="+", callback=self._increase_tick_size)
        
        # Main orderbook plot
        with dpg.plot(
            label="Orderbook", 
            tag=self.orderbook_plot_tag,
            height=-1,
            width=-1
        ):
            dpg.add_plot_legend()
            
            self.ob_xaxis_tag = dpg.add_plot_axis(dpg.mvXAxis)
            
            with dpg.plot_axis(dpg.mvYAxis, label="Volume", tag=self.ob_yaxis_tag):
                # Create series for both display modes
                # Stair series for aggregated view
                self.bids_stair_tag = dpg.add_stair_series(
                    [], [], label="Bids", show=True
                )
                self.asks_stair_tag = dpg.add_stair_series(
                    [], [], label="Asks", show=True
                )
                
                # Set colors after creation
                dpg.bind_item_theme(self.bids_stair_tag, self._create_bids_theme())
                dpg.bind_item_theme(self.asks_stair_tag, self._create_asks_theme())
                
                # Bar series for non-aggregated view (individual orders)
                self.bids_bar_tag = dpg.add_bar_series(
                    [], [], label="Bids", show=False, weight=0.5
                )
                self.asks_bar_tag = dpg.add_bar_series(
                    [], [], label="Asks", show=False, weight=0.5
                )
                
                # Set colors for bar series
                dpg.bind_item_theme(self.bids_bar_tag, self._create_bids_theme())
                dpg.bind_item_theme(self.asks_bar_tag, self._create_asks_theme())
    
    def _create_bids_theme(self):
        """Create a theme for bid items (green)"""
        bid_theme = dpg.add_theme()
        with dpg.theme_component(dpg.mvStairSeries, parent=bid_theme):
            dpg.add_theme_color(dpg.mvPlotCol_Line, [0, 255, 0, 255])
            dpg.add_theme_color(dpg.mvPlotCol_Fill, [0, 255, 0, 100])
        with dpg.theme_component(dpg.mvBarSeries, parent=bid_theme):
            dpg.add_theme_color(dpg.mvPlotCol_Line, [0, 255, 0, 255])
            dpg.add_theme_color(dpg.mvPlotCol_Fill, [0, 255, 0, 100])
        return bid_theme
    
    def _create_asks_theme(self):
        """Create a theme for ask items (red)"""
        ask_theme = dpg.add_theme()
        with dpg.theme_component(dpg.mvStairSeries, parent=ask_theme):
            dpg.add_theme_color(dpg.mvPlotCol_Line, [255, 0, 0, 255])
            dpg.add_theme_color(dpg.mvPlotCol_Fill, [255, 0, 0, 100])
        with dpg.theme_component(dpg.mvBarSeries, parent=ask_theme):
            dpg.add_theme_color(dpg.mvPlotCol_Line, [255, 0, 0, 255])
            dpg.add_theme_color(dpg.mvPlotCol_Fill, [255, 0, 0, 100])
        return ask_theme
    
    def build_status_bar(self) -> None:
        """Build the order book widget's status bar."""
        dpg.add_text("Best Bid: ")
        self.best_bid_tag = dpg.add_text("0.00")
        dpg.add_spacer(width=20)
        dpg.add_text("Best Ask: ")
        self.best_ask_tag = dpg.add_text("0.00")
        dpg.add_spacer(width=20)
        dpg.add_text("Spread: ")
        self.spread_tag = dpg.add_text("0.00")
    
    def register_handlers(self) -> None:
        """Register event handlers for order book related signals."""
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
    
    def _on_order_book_update(self, exchange: str, orderbook: dict):
        """Handler for ORDER_BOOK_UPDATE signal."""
        # Check if this update is for the correct market
        orderbook_symbol = orderbook.get('symbol')
        if exchange != self.exchange or orderbook_symbol != self.symbol:
            # Log for debugging, might remove later
            # logging.debug(f"OBWidget {self.window_tag} ignoring update for {exchange}/{orderbook_symbol}")
            return
        
        # Log for debugging, might remove later
        # logging.debug(f"OBWidget {self.window_tag} processing update for {self.exchange}/{self.symbol}")
        
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
        """Update the orderbook visualization with processed data."""
        # Extract data from processor result
        bids_processed = processed_data["bids_processed"]
        asks_processed = processed_data["asks_processed"]
        x_limits = processed_data["x_axis_limits"]
        y_limits = processed_data["y_axis_limits"]
        bid_ask_ratio = processed_data["bid_ask_ratio"]
        best_bid = processed_data["best_bid"]
        best_ask = processed_data["best_ask"]
        
        # Update the appropriate series based on aggregation mode
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
        midpoint = processed_data.get("midpoint", (x_min + x_max) / 2)
        if not hasattr(self, 'last_x_limits') or \
           abs(self.last_x_limits[0] - x_min) > 0.0005 * midpoint or \
           abs(self.last_x_limits[1] - x_max) > 0.0005 * midpoint:
            dpg.set_axis_limits(axis=self.ob_xaxis_tag, ymin=x_min, ymax=x_max)
            self.last_x_limits = (x_min, x_max)
            
        # Update y-axis limits
        y_min, y_max = y_limits
        dpg.set_axis_limits(axis=self.ob_yaxis_tag, ymin=y_min, ymax=y_max)

        # Update the stats
        dpg.set_value(self.bid_ask_ratio, f"{bid_ask_ratio:.2f}")
        dpg.set_value(self.best_bid_tag, f"{best_bid:.2f}")
        dpg.set_value(self.best_ask_tag, f"{best_ask:.2f}")
        dpg.set_value(self.spread_tag, f"{best_ask - best_bid:.2f}")
    
    def _toggle_aggregated_order_book(self, sender, app_data, user_data=None):
        """Toggle order book aggregation mode."""
        # Use processor to toggle aggregation
        self.processor.toggle_aggregation()
        
        # Refresh using the last raw data
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            self._on_order_book_update(self.exchange, self.last_orderbook)
    
    def _set_ob_levels(self, sender, app_data, user_data=None):
        """Set order book spread percentage."""
        # Update the spread percentage via processor
        self.processor.set_spread_percentage(app_data)
        
        # If we have order book data, refresh the display
        if hasattr(self, 'last_orderbook') and self.last_orderbook:
            self._on_order_book_update(self.exchange, self.last_orderbook)
    
    def _decrease_tick_size(self):
        """Decrease order book tick size."""
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
            self._on_order_book_update(self.exchange, self.last_orderbook)
    
    def _increase_tick_size(self):
        """Increase order book tick size."""
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
            self._on_order_book_update(self.exchange, self.last_orderbook)
    
    def close(self) -> None:
        """Clean up orderbook-specific resources before closing."""
        logging.info(f"Closing OrderbookWidget: {self.window_tag}")
        # Add any specific cleanup here before calling base class close
        super().close() # Call base class close to handle unsubscription and DPG item deletion 