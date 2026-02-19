"""
Demo application for the dockable widgets system.

This demonstrates how to use the widgets framework to create a customizable trading interface.
Run this file directly to test the widgets.
"""

import os
import sys
import logging
import dearpygui.dearpygui as dpg
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets import (
    DashboardManager,
    ChartWidget,
    OrderbookWidget,
    TradingWidget,
)


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class WidgetsDemoApp:
    """Demo application for testing the dockable widgets system."""
    
    def __init__(self):
        """Initialize the demo application."""
        # Initialize DearPyGUI
        dpg.create_context()
        
        # Create signal emitter
        self.emitter = SignalEmitter()
        
        # Create dashboard manager
        self.dashboard = DashboardManager(
            emitter=self.emitter,
            default_layout_file="config/factory_layout.ini",
            user_layout_file="config/user_layout.ini",
        )
        
        # Parse command line arguments
        self.parse_args()
    
    def parse_args(self):
        """Parse command line arguments."""
        # Check for reset flag
        self.reset_layout = "--reset" in sys.argv
    
    def setup(self):
        """Set up the application."""
        # Initialize layout
        self.dashboard.initialize_layout(reset=self.reset_layout)
        
        # Create viewport
        dpg.create_viewport(
            title="Trading Suite Widgets Demo",
            width=1280,
            height=720,
        )
        
        # Add primary dearpygui window
        with dpg.window(label="Demo", tag="primary_window"):
            # Create a menu bar
            with dpg.menu_bar():
                with dpg.menu(label="File"):
                    dpg.add_menu_item(label="New Chart", callback=self.add_chart_widget)
                    dpg.add_menu_item(label="New Orderbook", callback=self.add_orderbook_widget)
                    dpg.add_menu_item(label="New Trading Panel", callback=self.add_trading_widget)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Save Layout", callback=self.dashboard.save_layout)
                    dpg.add_menu_item(label="Reset Layout", callback=self.dashboard.reset_to_default)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Exit", callback=lambda: dpg.stop_dearpygui())
                
                with dpg.menu(label="View"):
                    dpg.add_menu_item(
                        label="Layout Tools", 
                        callback=lambda: self.dashboard.create_layout_tools()
                    )
        
        # Create initial widgets
        self.create_initial_widgets()
        
        # Setup viewport
        dpg.setup_dearpygui()
        dpg.show_viewport()
    
    def create_initial_widgets(self):
        """Create the initial set of widgets."""
        # Add a chart widget
        self.dashboard.add_widget(
            "btc_chart",
            ChartWidget(
                self.emitter,
                "coinbase",
                "BTC/USD",
                "1h",
            )
        )
        
        # Add an orderbook widget
        self.dashboard.add_widget(
            "btc_orderbook",
            OrderbookWidget(
                self.emitter,
                "coinbase",
                "BTC/USD",
            )
        )
        
        # Add a trading widget
        self.dashboard.add_widget(
            "btc_trading",
            TradingWidget(
                self.emitter,
                "coinbase",
                "BTC/USD",
            )
        )
        
        # Start simulated data
        self.start_simulated_data()
    
    def add_chart_widget(self):
        """Add a new chart widget."""
        self.dashboard.add_widget(
            f"chart_{len(self.dashboard.get_widget_ids())}",
            ChartWidget(
                self.emitter,
                "coinbase",
                "ETH/USD",
                "1h",
            )
        )
    
    def add_orderbook_widget(self):
        """Add a new orderbook widget."""
        self.dashboard.add_widget(
            f"orderbook_{len(self.dashboard.get_widget_ids())}",
            OrderbookWidget(
                self.emitter,
                "coinbase",
                "ETH/USD",
            )
        )
    
    def add_trading_widget(self):
        """Add a new trading widget."""
        self.dashboard.add_widget(
            f"trading_{len(self.dashboard.get_widget_ids())}",
            TradingWidget(
                self.emitter,
                "coinbase",
                "ETH/USD",
            )
        )
    
    def start_simulated_data(self):
        """Start sending simulated data to the widgets."""
        # Generate sample OHLCV data
        df = self.generate_sample_data()
        
        # Set up regular data updates
        with dpg.handler_registry():
            dpg.add_mouse_move_handler(callback=self.update_simulated_data)
        
        # Send initial candle data
        self.emitter.emit(
            Signals.NEW_CANDLES,
            exchange="coinbase",
            candles=df,
        )
        
        # Send initial orderbook data
        self.emitter.emit(
            Signals.ORDER_BOOK_UPDATE,
            exchange="coinbase",
            orderbook=self.generate_sample_orderbook(),
        )
    
    def generate_sample_data(self):
        """Generate sample OHLCV data for demonstration."""
        # Create a date range for the past 100 days
        end_date = datetime.now()
        dates = [end_date - timedelta(hours=i) for i in range(100, 0, -1)]
        timestamps = [int(date.timestamp()) for date in dates]
        
        # Generate random price data
        base_price = 50000.0  # Starting price
        closes = [base_price]
        
        # Random walk for price
        for i in range(1, 100):
            # Random price movement with some momentum
            price_change = np.random.normal(0, 500) + (closes[-1] - base_price) * 0.01
            new_price = max(100, closes[-1] + price_change)  # Ensure price stays positive
            closes.append(new_price)
        
        # Generate OHLCV data
        opens = [closes[i-1] for i in range(1, 100)] + [closes[-1] * 0.999]
        highs = [max(opens[i], closes[i]) * (1 + abs(np.random.normal(0, 0.01))) for i in range(100)]
        lows = [min(opens[i], closes[i]) * (1 - abs(np.random.normal(0, 0.01))) for i in range(100)]
        volumes = [abs(np.random.normal(10, 5)) for _ in range(100)]
        
        # Create DataFrame
        df = pd.DataFrame({
            "dates": timestamps,
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
        })
        
        self.last_price = closes[-1]
        self.last_candle_time = timestamps[-1]
        self.sample_data = df
        
        return df
    
    def generate_sample_orderbook(self):
        """Generate sample orderbook data for demonstration."""
        current_price = self.last_price
        
        # Generate bids (buy orders below current price)
        bids = []
        for i in range(1, 21):
            price = current_price * (1 - 0.001 * i)
            size = abs(np.random.normal(5, 2)) * (1 + 0.1 * i)  # More volume at lower prices
            bids.append([price, size])
        
        # Generate asks (sell orders above current price)
        asks = []
        for i in range(1, 21):
            price = current_price * (1 + 0.001 * i)
            size = abs(np.random.normal(5, 2)) * (1 + 0.05 * i)  # More volume at higher prices
            asks.append([price, size])
        
        # Sort orders
        bids.sort(key=lambda x: x[0], reverse=True)  # Highest price first
        asks.sort(key=lambda x: x[0])  # Lowest price first
        
        return {
            "bids": bids,
            "asks": asks,
        }
    
    def update_simulated_data(self, sender, app_data):
        """Update simulated data based on mouse movement to create dynamic updates."""
        # Only update occasionally to avoid overwhelming the UI
        if dpg.get_frame_count() % 30 != 0:
            return
        
        # Generate a new trade
        price_change = (app_data[1] - 400) / 200.0  # Use mouse Y position for price direction
        new_price = self.last_price * (1 + price_change * 0.001)
        
        # Ensure price is positive
        self.last_price = max(100, new_price)
        
        # Create trade data
        trade_data = {
            "price": self.last_price,
            "amount": abs(np.random.normal(0.1, 0.05)),
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        
        # Emit trade update
        self.emitter.emit(
            Signals.NEW_TRADE,
            exchange="coinbase",
            trade_data=trade_data,
        )
        
        # Occasionally update the orderbook (every ~2 seconds)
        if dpg.get_frame_count() % 60 == 0:
            self.emitter.emit(
                Signals.ORDER_BOOK_UPDATE,
                exchange="coinbase",
                orderbook=self.generate_sample_orderbook(),
            )
    
    def run(self):
        """Run the demo application."""
        # Setup the application
        self.setup()
        
        # Start the main loop
        dpg.start_dearpygui()
        
        # Cleanup when done
        dpg.destroy_context()


if __name__ == "__main__":
    app = WidgetsDemoApp()
    app.run() 