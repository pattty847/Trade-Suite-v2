import asyncio
import logging
import os
from typing import Dict, List

import dearpygui.dearpygui as dpg

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.data.sec_api import SECDataFetcher
from trade_suite.gui.dashboard_program import DashboardProgram
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.widgets import DashboardManager
from trade_suite.gui.utils import searcher


class Viewport:
    def __init__(self, data: Data, config_manager: ConfigManager) -> None:
        self.data = data
        self.config_manager = config_manager

        self.task_manager = TaskManager(self.data)
        self.sec_fetcher = SECDataFetcher(emitter=self.data.emitter)
        
        # Dashboard manager will be created in initialize_program
        self.dashboard_manager = None
        
        # Program will be created in initialize_program
        self.program = None

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
        
        # Configure docking
        default_layout = "config/factory_layout.ini"
        user_layout = "config/user_layout.ini"
        
        # If the user layout does not exist yet, prime it with the factory layout
        if not os.path.exists(user_layout) and os.path.exists(default_layout):
            dpg.load_init_file(default_layout)
        
        # Configure app with docking enabled and layout persistence
        dpg.configure_app(docking=True, docking_space=True, init_file=user_layout)
        
        self.load_theme()
        return self

    def load_theme(self):
        logging.info("Loading theme.")
        # with dpg.theme() as global_theme:
        #     with dpg.theme_component(dpg.mvAll):
        #         dpg.add_theme_color(
        #             dpg.mvThemeCol_FrameBg,
        #             (13, 13, 13, 255),
        #             category=dpg.mvThemeCat_Core,
        #         )
        #         dpg.add_theme_color(
        #             dpg.mvThemeCol_WindowBg,
        #             (13, 13, 13, 255),
        #             category=dpg.mvThemeCat_Core,
        #         )
        #         dpg.add_theme_color(
        #             dpg.mvThemeCol_ChildBg,
        #             (13, 13, 13, 255),
        #             category=dpg.mvThemeCat_Core,
        #         )
        #         dpg.add_theme_style(
        #             dpg.mvStyleVar_FrameRounding, 2, category=dpg.mvThemeCat_Core
        #         )
        #         dpg.add_theme_style(
        #             dpg.mvPlotStyleVar_MinorAlpha, 0.33, category=dpg.mvThemeCat_Plots
        #         )
        #         dpg.add_theme_style(
        #             dpg.mvPlotStyleVar_PlotPadding, 0, 0, category=dpg.mvThemeCat_Plots
        #         )

        #     with dpg.theme_component(dpg.mvInputInt):
        #         dpg.add_theme_color(
        #             dpg.mvThemeCol_FrameBg,
        #             (13, 13, 13, 255),
        #             category=dpg.mvThemeCat_Core,
        #         )
        #         dpg.add_theme_color(
        #             dpg.mvThemeCol_WindowBg,
        #             (13, 13, 13, 255),
        #             category=dpg.mvThemeCat_Core,
        #         )
        #         dpg.add_theme_color(
        #             dpg.mvThemeCol_ChildBg,
        #             (13, 13, 13, 255),
        #             category=dpg.mvThemeCat_Core,
        #         )
        #         dpg.add_theme_style(
        #             dpg.mvStyleVar_FrameRounding, 2, category=dpg.mvThemeCat_Core
        #         )
        #         dpg.add_theme_style(
        #             dpg.mvPlotStyleVar_MinorAlpha, 0.33, category=dpg.mvThemeCat_Plots
        #         )
        #         dpg.add_theme_style(
        #             dpg.mvPlotStyleVar_PlotPadding, 0, 0, category=dpg.mvThemeCat_Plots
        #         )

        # dpg.bind_theme(global_theme)
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll): # Apply to all widget types unless overridden
                # --- Overall Colors ---
                # Very dark backgrounds
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 30), category=dpg.mvThemeCat_Core) # Dark grey window background
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (30, 30, 30), category=dpg.mvThemeCat_Core) # Dark background for tables/child windows
                # Slightly lighter frames (inputs, selects)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 45), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (55, 55, 55), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (65, 65, 65), category=dpg.mvThemeCat_Core)
                # Text color
                dpg.add_theme_color(dpg.mvThemeCol_Text, (210, 210, 210), category=dpg.mvThemeCat_Core) # Light grey text
                # Borders and Separators (make them subtle)
                dpg.add_theme_color(dpg.mvThemeCol_Border, (60, 60, 60), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (60, 60, 60), category=dpg.mvThemeCat_Core)
                # Headers (like table headers, collapsing headers)
                dpg.add_theme_color(dpg.mvThemeCol_Header, (55, 55, 55), category=dpg.mvThemeCat_Core) # Slightly lighter grey
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (65, 65, 65), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (75, 75, 75), category=dpg.mvThemeCat_Core)
                # Buttons (adjust as needed)
                dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 55, 55), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (65, 65, 65), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (75, 75, 75), category=dpg.mvThemeCat_Core)
                # Tabs (adjust for desired active/inactive look)
                # ... add mvThemeCol_Tab* colors ...

                # --- Overall Styles (Density) ---
                # Reduce padding and spacing
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 4, 2, category=dpg.mvThemeCat_Core) # Less vertical padding in frames
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 4, 2, category=dpg.mvThemeCat_Core) # Tighter spacing between items
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 4, 4, category=dpg.mvThemeCat_Core) # Less padding around window content
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 2, 2, category=dpg.mvThemeCat_Core) # TIGHT table cell padding
                # Remove borders around input frames etc.
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 1, category=dpg.mvThemeCat_Core) # Keep a thin window border maybe

        # Bind the theme globally after creating it
        dpg.bind_theme(global_theme)
        
        logging.info("Done loading theme.")

    def start_program(self):
        """
        The setup_dpg function is responsible for setting up the DearPyGUI event loop, viewport, and primary window.
            It also sets a frame callback to initialize the program once it has been set up.

        :param self: Reference the class instance that is calling the function
        :return: The following:
        :doc-author: Trelent
        """
        logging.info("Setting up DearPyGUI loop, viewport, and primary window...")

        dpg.create_viewport(title="Trading Suite v2", width=1200, height=720)
        
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
                dpg.add_menu_item(label="Debug Tools", callback=lambda: self.program._create_debug_window() if self.program else None)
            
            # Placeholder for Exchange menu - will be populated after exchanges are loaded
            # Use a consistent tag for easier reference later
            self.exchange_menu_tag = dpg.generate_uuid()
            with dpg.menu(label="Exchange", tag=self.exchange_menu_tag):
                # We'll fill this dynamically after the program is initialized
                pass
        
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_frame_callback(
            1, lambda: self.initialize_program()
        )  # not called until after start_dearpyui() has been called

        logging.info("Setup complete. Launching DPG.")

        # Use manual render loop instead of dpg.start_dearpygui()
        # This allows us to process the signal queue on every frame
        try:
            initialized = False
            while dpg.is_dearpygui_running():
                # Process the signal queue before rendering each frame
                self.data.emitter.process_signal_queue()
                
                # Render the frame
                dpg.render_dearpygui_frame()
                
                # Check if we've initialized yet (first frame callback will handle this)
                if not initialized and dpg.get_frame_count() > 0:
                    initialized = True
        except Exception as e:
            logging.error(f"Error in main render loop: {e}", exc_info=True)

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

        # Create dashboard manager 
        self.dashboard_manager = DashboardManager(
            emitter=self.data.emitter,
            default_layout_file="config/factory_layout.ini",
            user_layout_file="config/user_layout.ini",
        )
        
        # Initialize the dashboard layout
        self.dashboard_manager.initialize_layout()
            
        # Create and initialize the program with the dashboard manager
        self.program = DashboardProgram(
            parent=None,  # No parent window anymore as we're not using a primary window
            data=self.data,
            task_manager=self.task_manager,
            config_manager=self.config_manager,
            dashboard_manager=self.dashboard_manager,
            sec_fetcher=self.sec_fetcher
        )
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
        # Cleanup resources
        self.task_manager.cleanup()
        self.sec_fetcher.close()
        dpg.destroy_context()

        if exc_type:
            logging.error(
                "An exception occurred: ", exc_info=(exc_type, exc_val, exc_tb)
            )
        else:
            logging.info("Finished shutting down.")
