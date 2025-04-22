import asyncio
import logging
import os
from typing import Dict, List, Optional

import dearpygui.dearpygui as dpg

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.data.sec_api import SECDataFetcher
from trade_suite.gui.dashboard_program import DashboardProgram
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.widgets import DashboardManager
from trade_suite.gui.utils import load_font, load_theme, searcher


class Viewport:
    def __init__(self, data: Data, config_manager: ConfigManager) -> None:
        self.data = data
        self.config_manager = config_manager

        # Initialize components that TaskManager depends on
        self.sec_fetcher = SECDataFetcher()

        # Pass dependencies to TaskManager
        self.task_manager = TaskManager(data=self.data, sec_fetcher=self.sec_fetcher)
        
        self.dashboard_manager = DashboardManager(
            emitter=self.data.emitter,
            task_manager=self.task_manager,
            sec_fetcher=self.sec_fetcher,
            default_layout_file="config/factory_layout.ini",
            user_layout_file="config/user_layout.ini",
            user_widgets_file="config/user_widgets.json"
        )
        self.program = DashboardProgram(    
            parent=None,  # No parent window anymore as we're not using a primary window
            data=self.data,
            task_manager=self.task_manager,
            config_manager=self.config_manager,
            dashboard_manager=self.dashboard_manager, # Use the one created in __enter__
            sec_fetcher=self.sec_fetcher
        )

    def __enter__(self):
        """
        The __enter__ function is called when the with statement is executed.
        It returns an object that will be bound to the target of the with statement.
        The __exit__ function is called after all code in the block has been executed, or if an exception occurred while executing it.

        :param self: Reference the class itself
        :return: Self, which is the data class
        :doc-author: Trelent
        """
        # Load the ccxt exchanges, symbols, and timeframes to the Data class
        # We need to wait for this to run and finish
        self.task_manager.run_task_until_complete(self.data.load_exchanges())

        # Setup dearpygui
        dpg.create_context()
        
        # Load the font and theme
        load_font()
        load_theme()

        # --- Initialize Dashboard Manager and Layout EARLY --- 
        # This MUST happen after create_context and before create_viewport
        self.dashboard_manager.initialize_layout() # Calls configure_app internally
        return self

    def start_program(self):
        """
        The setup_dpg function is responsible for setting up the DearPyGUI event loop, viewport, and primary window.
            It also sets a frame callback to initialize the program once it has been set up.

        :param self: Reference the class instance that is calling the function
        :return: The following:
        :doc-author: Trelent
        """
        logging.info("Setting up DearPyGUI loop, viewport, and primary window...")

        # Initialize the program BEFORE creating viewport to ensure windows are created
        # in the correct order for layout persistence
        self.initialize_program()
        
        self.create_viewport_and_menubar()
        
        dpg.setup_dearpygui()
        dpg.show_viewport()
        
        # Maximize viewport for better docking experience
        dpg.maximize_viewport()
        # dpg.set_exit_callback

        logging.info("Setup complete. Launching DPG.")

        # --- Start the DearPyGUI loop ---
        # Use manual render loop instead of dpg.start_dearpygui()
        # This allows us to process the signal queue on every frame
        try:
            # If process_signal_queue() raises, you swallow it and the loop 
            # continues with undefined state. Wrap each iteration in a try/except 
            # or—better—make SignalEmitter fail‑safe.
            while dpg.is_dearpygui_running():
                # Process the signal queue before rendering each frame
                self.data.emitter.process_signal_queue()
                
                # Render the frame
                dpg.render_dearpygui_frame()
        except Exception as e:
            logging.error(f"Error in main render loop: {e}", exc_info=True)

    def create_viewport_and_menubar(self):
        dpg.create_viewport(title="Trading Suite v2", width=1200, height=720)
        """Create the viewport menu bar."""
        # Add viewport menu bar (attached to viewport, not to any window)
        with dpg.viewport_menu_bar():
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="New Chart", callback=lambda: self.data.emitter.emit(Signals.NEW_CHART_REQUESTED))
                dpg.add_menu_item(label="New Orderbook", callback=lambda: self.data.emitter.emit(Signals.NEW_ORDERBOOK_REQUESTED))
                dpg.add_menu_item(label="New Trading Panel", callback=lambda: self.data.emitter.emit(Signals.NEW_TRADING_PANEL_REQUESTED))
                dpg.add_menu_item(label="New Price Level", callback=lambda: self.data.emitter.emit(Signals.NEW_PRICE_LEVEL_REQUESTED))
                dpg.add_menu_item(label="New SEC Filing Viewer", callback=lambda: self.data.emitter.emit(Signals.NEW_SEC_FILING_VIEWER_REQUESTED))
                dpg.add_separator()
                dpg.add_menu_item(label="Save Layout", callback=lambda: self.dashboard_manager.trigger_save_layout() if self.dashboard_manager else None)
                dpg.add_menu_item(label="Reset Layout", callback=lambda: self.dashboard_manager.reset_to_default() if self.dashboard_manager else None)
                dpg.add_separator()
                dpg.add_menu_item(label="Exit", callback=lambda: dpg.stop_dearpygui())
            
            with dpg.menu(label="View"):
                dpg.add_menu_item(label="Layout Tools", callback=lambda: self.dashboard_manager.create_layout_tools() if self.dashboard_manager else None)
                dpg.add_menu_item(label="Debug Tools", callback=lambda: self.program._create_debug_window() if self.program else None)
            
            # Placeholder for Exchange menu - will be populated after exchanges are loaded
            # Use a consistent tag for easier reference later
            self.exchange_menu_tag = f"exchange_menu"
            dpg.add_menu(label="Exchange", tag=self.exchange_menu_tag)

    def populate_exchange_menu(self):
        """Populate the Exchange menu with available exchanges."""
        if not self.data.exchanges:
            logging.warning("No exchanges available to populate menu")
            return
            
        # Now we can directly access the Exchange menu using the tag we stored
        if not hasattr(self, 'exchange_menu_tag') or not dpg.does_item_exist(self.exchange_menu_tag):
            logging.warning("Exchange menu tag not found or menu doesn't exist")
            return
            
        exchange_menu = self.exchange_menu_tag
        
        # Clear existing items
        try:
            existing_items = dpg.get_item_children(exchange_menu)[1]
            for item in existing_items:
                dpg.delete_item(item)
        except:
            logging.warning("Error clearing Exchange menu items", exc_info=True)
            
        # Add search functionality
        input_tag = dpg.add_input_text(label="Search", parent=exchange_menu)
        
        # Add exchange listbox
        exchange_list_tag = dpg.add_listbox(
            items=list(self.data.exchanges),
            parent=exchange_menu,
            callback=lambda s, a, u: self.data.emitter.emit(Signals.CREATE_EXCHANGE_TAB, exchange=a),
            num_items=10,
        )
        
        # Setup search callback
        dpg.set_item_callback(
            input_tag,
            callback=lambda: searcher(
                input_tag, exchange_list_tag, list(self.data.exchanges)
            ),
        )

    def initialize_program(self):
        """
        The initialize_program function is responsible for initializing the program classes and subclasses.
            This function will initialize all UI components and register their callback.


        :param self: Reference the class instance
        :return: None
        :doc-author: Trelent
        """

        # This will initialize all UI components and register their callback
        logging.info(f"Setting up the program classes and subclasses.")
            
        # Create and initialize the program with the dashboard manager
        # Ensure dashboard_manager was created in __enter__
        if not self.dashboard_manager:
            logging.error("DashboardManager was not initialized in __enter__!")
            # Handle error appropriately - maybe raise an exception or stop
            dpg.stop_dearpygui()
            return

        # Initialize program by creating widgets for each exchange
        self.program.initialize()
        
        # We no longer set a primary window - all windows are equal and dockable
        # dpg.set_primary_window(self.primary_window_tag, True)
        
        # Populate the Exchange menu with available exchanges
        self.populate_exchange_menu()
        
        # Setup viewport resize handler
        dpg.set_viewport_resize_callback(
            lambda: self.data.emitter.emit(
                Signals.VIEWPORT_RESIZED,
                width=dpg.get_viewport_width(),
                height=dpg.get_viewport_height(),
            )
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        The __exit__ function is called when the context manager exits.
        The __exit__ function takes three arguments: exc_type, exc_value and traceback.
        If an exception occurred while executing the body of with statement,
        the arguments will be the exception type, value and traceback object as returned by sys.exc_info().
        Otherwise all three arguments will be None.

        :param self: Represent the instance of the class
        :param exc_type: Determine if an exception has occurred
        :param exc_val: Get the exception value
        :param exc_tb: Pass the traceback object
        :return: None
        :doc-author: Trelent
        """
        logging.info("Shutting down...")
        # Cleanup resources (TaskManager now handles sec_fetcher.close)
        self.task_manager.cleanup()
        dpg.destroy_context()

        if exc_type:
            logging.error(
                "An exception occurred: ", exc_info=(exc_type, exc_val, exc_tb)
            )
        else:
            logging.info("Finished shutting down.")
