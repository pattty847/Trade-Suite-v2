import asyncio
import logging
import os
from typing import Dict, List, Optional

import dearpygui.dearpygui as dpg
import platform

from .dashboard_program import DashboardProgram
from .utils import center_window
from ..config import ConfigManager
from trade_suite.gui.utils import load_font, load_theme, searcher
from ..core.facade import CoreServicesFacade


class Viewport:
    """The main window container for the application."""

    def __init__(self, config_manager: ConfigManager, core: CoreServicesFacade):
        self.config_manager = config_manager
        self.core = core
        self.program: DashboardProgram = None

    def __enter__(self):
        dpg.create_context()
        
        # Enable docking feature for the application.
        dpg.configure_app(docking=True, docking_space=True)
        
        load_font()
        dpg.create_viewport(title='Trade Suite v2', width=1800, height=1000)
        load_theme()
        
        # The DashboardProgram now handles setting up the menubar and managing widgets.
        self.program = DashboardProgram(self.core, self.config_manager)
        
        # Setup DPG and the primary dockspace before initializing the layout.
        dpg.setup_dearpygui()
        
        dpg.add_window(tag="primary_window")

        # CRITICAL: Initialize the layout here. This recreates widgets from config
        # so they exist before the .ini file is loaded by `show_viewport`.
        self.program.initialize_layout()

        dpg.show_viewport()
        dpg.set_primary_window("primary_window", True)
        dpg.set_viewport_resize_callback(self.program.on_viewport_resize)
        
        return self

    def run(self):
        """Starts the main application loop."""
        # The layout is now initialized in __enter__.
        # The run loop is only responsible for rendering frames.
        while dpg.is_dearpygui_running():
            # Process signals from the backend thread
            self.core.emitter.process_signal_queue()
            # Render the GUI
            dpg.render_dearpygui_frame()

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.info("Destroying DPG context...")
        
        # Ensure facade cleanup is called to stop the background thread
        self.core.cleanup()

        # Make sure to save the layout on exit if it has been modified
        if self.program.dashboard_manager.is_layout_modified():
            logging.info("Layout modified, saving on exit...")
            self.program.dashboard_manager.save_layout()
            
        dpg.destroy_context()
        logging.info("DPG context destroyed.")
