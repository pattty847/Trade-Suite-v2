import logging
import dearpygui.dearpygui as dpg
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget

# Forward declaration for type hinting
if TYPE_CHECKING:
    from trade_suite.gui.task_manager import TaskManager


class TradingWidget(DockableWidget):
    """
    Widget for trading functionality, including order entry and position management.
    """
    
    def __init__(
        self,
        emitter: SignalEmitter,
        task_manager: 'TaskManager',
        exchange: str,
        symbol: str,
        instance_id: Optional[str] = None,
        width: int = 1200,
        height: int = 250,
    ):
        """
        Initialize a trading widget.
        
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
            title=f"Trading - {exchange.upper()} {symbol}",
            widget_type="trading",
            emitter=emitter,
            task_manager=task_manager,
            instance_id=instance_id,
            width=width,
            height=height,
        )
        
        # Configuration
        self.exchange = exchange
        self.symbol = symbol
        
        # Internal state
        self.current_price = 0.0
        self.position_size = 0.0
        self.position_entry = 0.0
        self.unrealized_pnl = 0.0
        self.order_quantity = 0.01  # Default quantity
        
        # UI component tags
        self.position_table_tag = f"{self.window_tag}_positions"
        self.order_table_tag = f"{self.window_tag}_orders"
        self.price_display = f"{self.window_tag}_price_display"
        self.price_input = f"{self.window_tag}_price_input"
        self.quantity_input = f"{self.window_tag}_quantity_input"
        self.position_size_display = f"{self.window_tag}_pos_size"
        self.position_entry_display = f"{self.window_tag}_pos_entry"
        self.position_pnl_display = f"{self.window_tag}_pos_pnl"
        self.exchange_status = f"{self.window_tag}_exch_status"
        self.last_order_status = f"{self.window_tag}_last_order"
    
    def get_requirements(self) -> Dict[str, Any]:
        """Define the data requirements for the TradingWidget."""
        # Trading widget primarily needs real-time trades for price updates
        return {
            "type": "trades",
            "exchange": self.exchange,
            "symbol": self.symbol,
            # No timeframe needed
        }
    
    def build_menu(self) -> None:
        """Build the trading widget's menu bar."""
        with dpg.menu(label="Order Types"):
            dpg.add_menu_item(label="Market", callback=self._set_order_type_market)
            dpg.add_menu_item(label="Limit", callback=self._set_order_type_limit)
            dpg.add_menu_item(label="Stop", callback=self._set_order_type_stop)
        
        with dpg.menu(label="Trading Tools"):
            dpg.add_menu_item(label="Risk Calculator", callback=self._show_risk_calculator)
            dpg.add_menu_item(label="Order History", callback=self._show_order_history)
    
    def build_content(self) -> None:
        """Build the trading widget's content."""
        # Main trading layout with two columns
        with dpg.group(horizontal=True):
            # Left side - Order entry
            with dpg.child_window(width=400, height=-1):
                with dpg.collapsing_header(label="Order Entry", default_open=True):
                    # Price display
                    with dpg.group(horizontal=True):
                        dpg.add_text("Current Price:")
                        dpg.add_text("0.00", tag=self.price_display)
                    
                    # Order type selector
                    dpg.add_combo(
                        items=["Market", "Limit", "Stop"],
                        default_value="Market",
                        callback=lambda s, a: self._on_order_type_change(a),
                        label="Order Type",
                        width=150
                    )
                    
                    # Order price (for limit/stop orders)
                    dpg.add_input_float(
                        label="Price",
                        default_value=0.0,
                        format="%.2f",
                        width=150,
                        enabled=False,  # Disabled for market orders
                        tag=self.price_input
                    )
                    
                    # Quantity
                    dpg.add_input_float(
                        label="Quantity",
                        default_value=self.order_quantity,
                        format="%.4f",
                        width=150,
                        callback=self._on_quantity_change,
                        tag=self.quantity_input
                    )
                    
                    # Buttons for common quantities
                    with dpg.group(horizontal=True):
                        for qty in [0.001, 0.01, 0.1, 1.0]:
                            dpg.add_button(
                                label=str(qty),
                                callback=lambda s, a, q=qty: self._set_quantity(q),
                                width=50
                            )
                    
                    # Order buttons
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="BUY",
                            callback=self._on_buy,
                            width=100,
                            height=30
                        )
                        
                        dpg.add_button(
                            label="SELL",
                            callback=self._on_sell,
                            width=100,
                            height=30
                        )
                
                # Position info
                with dpg.collapsing_header(label="Position", default_open=True):
                    with dpg.group():
                        with dpg.group(horizontal=True):
                            dpg.add_text("Size:")
                            dpg.add_text("0.0", tag=self.position_size_display)
                        
                        with dpg.group(horizontal=True):
                            dpg.add_text("Entry:")
                            dpg.add_text("0.00", tag=self.position_entry_display)
                        
                        with dpg.group(horizontal=True):
                            dpg.add_text("P&L:")
                            dpg.add_text("$0.00", tag=self.position_pnl_display)
                        
                        # Close position button
                        dpg.add_button(
                            label="Close Position",
                            callback=self._on_close_position,
                            width=150
                        )
            
            # Right side - Orders and history
            with dpg.child_window(width=-1, height=-1):
                with dpg.tab_bar():
                    # Open orders tab
                    with dpg.tab(label="Open Orders"):
                        with dpg.table(
                            header_row=True,
                            borders_innerH=True,
                            borders_outerH=True,
                            borders_innerV=True,
                            borders_outerV=True,
                            tag=self.order_table_tag,
                            height=-1
                        ):
                            dpg.add_table_column(label="ID")
                            dpg.add_table_column(label="Type")
                            dpg.add_table_column(label="Side")
                            dpg.add_table_column(label="Price")
                            dpg.add_table_column(label="Quantity")
                            dpg.add_table_column(label="Time")
                            dpg.add_table_column(label="Actions")
                    
                    # Filled orders tab
                    with dpg.tab(label="Order History"):
                        # Similar table for filled orders
                        pass
    
    def build_status_bar(self) -> None:
        """Build the trading widget's status bar."""
        dpg.add_text("Exchange Status:")
        dpg.add_text("Connected", tag=self.exchange_status)
        dpg.add_spacer(width=20)
        dpg.add_text("Last Order:")
        dpg.add_text("None", tag=self.last_order_status)
    
    def register_handlers(self) -> None:
        """Register event handlers for trading related signals."""
        self.emitter.register(Signals.NEW_TRADE, self._on_new_trade)
        # More handlers would be registered for actual trading functionality
    
    def _on_new_trade(self, exchange: str, trade_data: dict):
        """Handler for new trade data."""
        # Filter trades based on the widget's configured exchange and symbol
        trade_symbol = trade_data.get('symbol')
        if exchange != self.exchange or trade_symbol != self.symbol:
            return
            
        # Update current price
        self.current_price = trade_data.get("price", 0)
        dpg.set_value(self.price_display, f"${self.current_price:.2f}")
        
        # Update position P&L if we have a position
        if self.position_size != 0:
            self._update_position_pnl()
    
    def _on_order_type_change(self, order_type):
        """Handler for order type change."""
        # Enable/disable price input based on order type
        is_market = order_type == "Market"
        dpg.configure_item(self.price_input, enabled=not is_market)
        
        # If switching to market, use current price
        if is_market:
            dpg.set_value(self.price_input, self.current_price)
    
    def _on_quantity_change(self, sender, app_data):
        """Handler for quantity change."""
        self.order_quantity = app_data
    
    def _set_quantity(self, quantity):
        """Set the order quantity."""
        self.order_quantity = quantity
        dpg.set_value(self.quantity_input, quantity)
    
    def _on_buy(self):
        """Handler for buy button."""
        # Get order details
        order_type = dpg.get_value(dpg.get_item_parent(self.price_input))
        price = dpg.get_value(self.price_input) if order_type != "Market" else self.current_price
        quantity = dpg.get_value(self.quantity_input)
        
        # Validate
        if quantity <= 0:
            logging.warning("Order quantity must be greater than 0")
            return
            
        if order_type != "Market" and price <= 0:
            logging.warning("Order price must be greater than 0")
            return
        
        # Add to position (simplified, in reality would place an order)
        self._add_to_position(quantity, price)
        
        # Add to orders table
        self._add_order_to_table("Buy", order_type, price, quantity)
        
        # Update status
        dpg.set_value(self.last_order_status, f"Buy {quantity} @ {price:.2f}")
        
        # In a real implementation, would emit an order placement signal
    
    def _on_sell(self):
        """Handler for sell button."""
        # Get order details
        order_type = dpg.get_value(dpg.get_item_parent(self.price_input))
        price = dpg.get_value(self.price_input) if order_type != "Market" else self.current_price
        quantity = dpg.get_value(self.quantity_input)
        
        # Validate
        if quantity <= 0:
            logging.warning("Order quantity must be greater than 0")
            return
            
        if order_type != "Market" and price <= 0:
            logging.warning("Order price must be greater than 0")
            return
        
        # Add to position (simplified, in reality would place an order)
        self._add_to_position(-quantity, price)
        
        # Add to orders table
        self._add_order_to_table("Sell", order_type, price, quantity)
        
        # Update status
        dpg.set_value(self.last_order_status, f"Sell {quantity} @ {price:.2f}")
        
        # In a real implementation, would emit an order placement signal
    
    def _on_close_position(self):
        """Handler for close position button."""
        if self.position_size == 0:
            return
            
        # Create an order to close the position
        side = "Sell" if self.position_size > 0 else "Buy"
        quantity = abs(self.position_size)
        
        # Add order to table
        self._add_order_to_table(side, "Market", self.current_price, quantity)
        
        # Update status
        dpg.set_value(self.last_order_status, f"Close {side} {quantity} @ {self.current_price:.2f}")
        
        # Reset position
        self._reset_position()
    
    def _reset_position(self):
        """Reset position data."""
        self.position_size = 0.0
        self.position_entry = 0.0
        self.unrealized_pnl = 0.0
        
        # Update UI
        dpg.set_value(self.position_size_display, f"{self.position_size:.4f}")
        dpg.set_value(self.position_entry_display, f"${self.position_entry:.2f}")
        dpg.set_value(self.position_pnl_display, f"${self.unrealized_pnl:.2f}")
    
    def _add_to_position(self, quantity, price):
        """Add to existing position (handles both buy and sell)."""
        if self.position_size == 0:
            # New position
            self.position_size = quantity
            self.position_entry = price
        else:
            # Adjust existing position - simplified calculation
            # In reality would use proper avg price calculation
            old_value = self.position_size * self.position_entry
            new_value = quantity * price
            self.position_size += quantity
            
            # If position crosses zero, reset
            if (self.position_size > 0 and self.position_size - quantity <= 0) or \
               (self.position_size < 0 and self.position_size - quantity >= 0):
                self.position_entry = price
            else:
                # Calculate new average entry
                self.position_entry = (old_value + new_value) / self.position_size if self.position_size != 0 else 0
        
        # Update UI
        dpg.set_value(self.position_size_display, f"{self.position_size:.4f}")
        dpg.set_value(self.position_entry_display, f"${self.position_entry:.2f}")
        
        # Update P&L
        self._update_position_pnl()
    
    def _update_position_pnl(self):
        """Update unrealized P&L based on current price and position."""
        if self.position_size == 0:
            self.unrealized_pnl = 0.0
        else:
            # Calculate P&L - long positions gain when price rises, short positions gain when price falls
            price_diff = self.current_price - self.position_entry
            self.unrealized_pnl = price_diff * self.position_size
        
        # Update UI with color based on profit/loss
        if self.unrealized_pnl > 0:
            dpg.configure_item(self.position_pnl_display, color=[0, 255, 0])
        elif self.unrealized_pnl < 0:
            dpg.configure_item(self.position_pnl_display, color=[255, 0, 0])
        else:
            dpg.configure_item(self.position_pnl_display, color=[255, 255, 255])
            
        dpg.set_value(self.position_pnl_display, f"${self.unrealized_pnl:.2f}")
    
    def _add_order_to_table(self, side, order_type, price, quantity):
        """Add an order to the orders table."""
        import time
        from datetime import datetime
        
        # Generate a simple order ID
        order_id = f"ORD-{int(time.time() * 1000) % 10000}"
        
        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Add a row to the orders table
        with dpg.table_row(parent=self.order_table_tag):
            dpg.add_text(order_id)
            dpg.add_text(order_type)
            dpg.add_text(side)
            dpg.add_text(f"{price:.2f}")
            dpg.add_text(f"{quantity:.4f}")
            dpg.add_text(timestamp)
            
            # Add cancel button
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Cancel",
                    callback=lambda s, a, row=dpg.last_item(): self._cancel_order(row)
                )
    
    def _cancel_order(self, row):
        """Cancel an order and remove from the table."""
        # In a real implementation, would send a cancel request to the exchange
        # For now, just remove the row
        parent = dpg.get_item_parent(row)
        dpg.delete_item(parent)
        
        # Update status
        dpg.set_value(self.last_order_status, "Order Cancelled")
    
    def _clear_orders(self):
        """Clear all orders from the table."""
        # Get all rows in the table and delete them
        for child in dpg.get_item_children(self.order_table_tag, slot=1):
            dpg.delete_item(child)
    
    def _set_order_type_market(self):
        """Set order type to Market."""
        dpg.set_value(dpg.get_item_parent(self.price_input), "Market")
        self._on_order_type_change("Market")
    
    def _set_order_type_limit(self):
        """Set order type to Limit."""
        dpg.set_value(dpg.get_item_parent(self.price_input), "Limit")
        self._on_order_type_change("Limit")
    
    def _set_order_type_stop(self):
        """Set order type to Stop."""
        dpg.set_value(dpg.get_item_parent(self.price_input), "Stop")
        self._on_order_type_change("Stop")
    
    def _show_risk_calculator(self):
        """Show the risk calculator dialog."""
        # In a real implementation, would create a risk calculator popup
        logging.info("Risk calculator not implemented yet")
    
    def _show_order_history(self):
        """Show the order history dialog."""
        # In a real implementation, would create an order history popup
        logging.info("Order history not implemented yet")

    def close(self) -> None:
        """Clean up trading-specific resources before closing."""
        logging.info(f"Closing TradingWidget: {self.window_tag}")
        # Add any specific cleanup here before calling base class close
        super().close() # Call base class close to handle unsubscription and DPG item deletion 