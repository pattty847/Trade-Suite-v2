#!/usr/bin/env python
"""
Demo script to create and display an SEC Filing Viewer window.
This demonstrates the integration of the SEC data fetcher with the GUI.
"""

import os
import logging
import asyncio
import dearpygui.dearpygui as dpg

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set EDGAR identity through environment variable if needed
if not os.environ.get("EDGAR_IDENTITY"):
    os.environ["EDGAR_IDENTITY"] = "TradingSuite User trading.suite@example.com"

# Import our components
from trade_suite.gui.signals import SignalEmitter
from trade_suite.data.sec_data import SECDataFetcher
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.widgets.sec_filing_viewer import SECFilingViewer

class DemoApp:
    """Simple demo application for the SEC Filing Viewer."""
    
    def __init__(self):
        # Set up core components
        self.emitter = SignalEmitter()
        
        # Pass the emitter directly to TaskManager
        self.task_manager = TaskManager(self.emitter)
        self.sec_fetcher = SECDataFetcher(self.emitter)
        
        # Initialize DearPyGUI
        dpg.create_context()
        dpg.create_viewport(title="SEC Filing Viewer Demo", width=1000, height=800)
        dpg.setup_dearpygui()
        
        # Create the viewer in setup method
        self.viewer = None
    
    def setup(self):
        """Set up the demo application."""
        # Create a main window
        with dpg.window(label="SEC Filing Viewer Demo", tag="main_window", width=1000, height=800):
            dpg.add_text("Welcome to the SEC Filing Viewer Demo")
            dpg.add_text("This demonstrates fetching and displaying SEC filings, insider transactions, and financial data.")
            dpg.add_separator()
            
            # Ticker input and buttons
            dpg.add_text("Enter a ticker to create a new SEC Filing Viewer:")
            with dpg.group(horizontal=True):
                ticker_input = dpg.add_input_text(label="Ticker", default_value="AAPL", width=100)
                dpg.add_button(label="Create Viewer", callback=lambda: self.create_viewer(dpg.get_value(ticker_input)))
            
            dpg.add_separator()
            
            # Instructions
            dpg.add_text("Instructions:")
            dpg.add_text("1. Enter a stock ticker (e.g., AAPL, MSFT, GOOGL)")
            dpg.add_text("2. Click 'Create Viewer' to open the SEC Filing Viewer")
            dpg.add_text("3. In the viewer, use the buttons to fetch filings, insider transactions, or financials")
        
        # Set up signal processing in the main loop
        dpg.set_viewport_resize_callback(lambda: self.on_resize())
    
    def create_viewer(self, ticker):
        """Create and show a new SEC Filing Viewer for the given ticker."""
        logging.info(f"Creating SEC Filing Viewer for {ticker}")
        
        # Create the viewer instance
        self.viewer = SECFilingViewer(
            emitter=self.emitter,
            sec_fetcher=self.sec_fetcher,
            task_manager=self.task_manager,
            instance_id=f"demo_{ticker}"
        )
        
        # Create and show the widget
        self.viewer.create()
        self.viewer.show()
        
        # Pre-fill the ticker input
        if dpg.does_item_exist(self.viewer.ticker_input_tag):
            dpg.set_value(self.viewer.ticker_input_tag, ticker.upper())
    
    def on_resize(self):
        """Handle viewport resize events."""
        if self.viewer and self.viewer.is_created:
            # Adjust viewer size if needed
            width, height = dpg.get_viewport_width(), dpg.get_viewport_height()
            if width > 600 and height > 500:
                dpg.configure_item(self.viewer.window_tag, width=min(width-50, 800), height=min(height-50, 700))
    
    def run(self):
        """Run the demo application."""
        try:
            # Show the viewport
            dpg.show_viewport()
            
            # Main loop
            while dpg.is_dearpygui_running():
                # Process signals each frame
                self.emitter.process_signal_queue()
                
                # Render a frame
                dpg.render_dearpygui_frame()
                
        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            # Clean up resources
            if self.sec_fetcher:
                self.sec_fetcher.close()
            
            # Clean up DPG
            dpg.destroy_context()

if __name__ == "__main__":
    app = DemoApp()
    app.setup()
    app.run() 