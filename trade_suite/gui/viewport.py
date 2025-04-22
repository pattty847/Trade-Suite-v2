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
        # Flag to track if widgets were loaded from config
        self.widgets_loaded_from_config: bool = False 

        # Initialize components that TaskManager depends on
        self.sec_fetcher = SECDataFetcher()

        # Pass dependencies to TaskManager
        self.task_manager = TaskManager(data=self.data, sec_fetcher=self.sec_fetcher)
        
        # Instantiate DashboardManager, passing the config_manager instance
        self.dashboard_manager = DashboardManager(
            emitter=self.data.emitter,
            task_manager=self.task_manager,
            sec_fetcher=self.sec_fetcher,
            config_manager=self.config_manager # Pass the instance here
            # Remove old file path arguments
        )
        self.dashboard_program = DashboardProgram(    
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

        # --- Setup DearPyGui context BEFORE initializing layout --- 
        # This is crucial as DPG might need setup for layout loading to work correctly.
        # Corresponds to the working test_custom_layout.py sequence.
        self.create_viewport_and_menubar() # Create viewport and menubar first
        dpg.setup_dearpygui()

        # --- Initialize Dashboard Manager and Layout AFTER setup_dearpygui --- 
        # This MUST happen after create_context and setup_dearpygui, and before show_viewport
        logging.info("Initializing layout AFTER DPG setup...")
        self.widgets_loaded_from_config = self.dashboard_manager.initialize_layout()
        
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

        # --- Initialize program ---
        # Check if widgets were loaded from config during __enter__
        if not self.widgets_loaded_from_config:
            # If no widgets were loaded from config, initialize the default program layout
            logging.info("No saved widgets loaded from configuration, initializing default program layout.")
            self.dashboard_program.initialize()
        else:
            # Widgets were loaded, log how many
            # We access self.dashboard_manager.widgets which was populated by initialize_layout
            num_loaded = len(self.dashboard_manager.widgets) 
            logging.info(f"Successfully loaded {num_loaded} widgets from configuration.")
            # Ensure the exchange menu reflects any loaded exchanges if necessary,
            # although DashboardProgram.initialize usually handles widget creation logic.
            # If loaded widgets require specific exchange menu setup, add it here.
        
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
        
        # Viewport creation and DPG setup moved to __enter__
        # self.create_viewport_and_menubar()
        # dpg.setup_dearpygui()
        
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
                dpg.add_menu_item(label="Save Layout", callback=lambda: self.dashboard_manager.save_layout() if self.dashboard_manager else None)
                dpg.add_menu_item(label="Reset Layout", callback=lambda: self.dashboard_manager.reset_to_default() if self.dashboard_manager else None)
                dpg.add_separator()
                dpg.add_menu_item(label="Exit", callback=lambda: dpg.stop_dearpygui())
            
            with dpg.menu(label="View"):
                dpg.add_menu_item(label="Layout Tools", callback=lambda: self.dashboard_manager.create_layout_tools() if self.dashboard_manager else None)
                dpg.add_menu_item(label="Debug Tools", callback=lambda: self.dashboard_program._create_debug_window() if self.dashboard_program else None)
            
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
