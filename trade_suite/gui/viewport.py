import logging

import dearpygui.dearpygui as dpg

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.program import Program
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager


class Viewport:
    def __init__(self, data: Data, config_manager: ConfigManager) -> None:
        self.data = data
        self.config_manager = config_manager

        self.task_manager = TaskManager(self.data)
        self.program = Program(self.data, self.task_manager, self.config_manager)

    def __enter__(self):
        # Load the ccxt exchanges, symbols, and timeframes to the Data class
        # We need to wait for this to run and finish
        self.task_manager.run_task_until_complete(self.data.load_exchanges())

        # Setup dearpygui
        dpg.create_context()
        self.load_theme()
        self.setup_dpg()
        return self

    def load_theme(self):
        logging.info("Loading theme.")
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(
                    dpg.mvThemeCol_FrameBg,
                    (13, 13, 13, 255),
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_WindowBg,
                    (13, 13, 13, 255),
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_ChildBg,
                    (13, 13, 13, 255),
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_style(
                    dpg.mvStyleVar_FrameRounding, 2, category=dpg.mvThemeCat_Core
                )
                dpg.add_theme_style(
                    dpg.mvPlotStyleVar_MinorAlpha, 0.33, category=dpg.mvThemeCat_Plots
                )
                dpg.add_theme_style(
                    dpg.mvPlotStyleVar_PlotPadding, 0, 0, category=dpg.mvThemeCat_Plots
                )

            with dpg.theme_component(dpg.mvInputInt):
                dpg.add_theme_color(
                    dpg.mvThemeCol_FrameBg,
                    (13, 13, 13, 255),
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_WindowBg,
                    (13, 13, 13, 255),
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_ChildBg,
                    (13, 13, 13, 255),
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_style(
                    dpg.mvStyleVar_FrameRounding, 2, category=dpg.mvThemeCat_Core
                )
                dpg.add_theme_style(
                    dpg.mvPlotStyleVar_MinorAlpha, 0.33, category=dpg.mvThemeCat_Plots
                )
                dpg.add_theme_style(
                    dpg.mvPlotStyleVar_PlotPadding, 0, 0, category=dpg.mvThemeCat_Plots
                )

        dpg.bind_theme(global_theme)
        logging.info("Done loading theme.")

    def setup_dpg(self):
        """
        The setup_dpg function is responsible for setting up the DearPyGUI event loop, viewport, and primary window.
            It also sets a frame callback to initialize the program once it has been set up.

        :param self: Reference the class instance that is calling the function
        :return: The following:
        :doc-author: Trelent
        """
        logging.info("Setting up DearPyGUI loop, viewport, and primary window...")

        dpg.create_viewport(title="Crpnto Dahsbrod", width=1200, height=720)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_frame_callback(
            1, lambda: self.initialize_program()
        )  # not called until after start_dearpyui() has been called

        logging.info("Setup complete. Launching DPG.")

        dpg.start_dearpygui()  # main dpg event loop

    def initialize_program(self):
        """
        The initialize_program function is responsible for setting up the main program class and all of its subclasses.
        It also registers all signals that will be used in the program.

        The async loop is started within a daemon thread to allow non-blocking UI updates while async streaming is going on.

        :param self: Refer to the class itself
        :return: A list of the below registering or emition
        :doc-author: Trelent
        """
        # This will initialize all UI components and register their callback
        logging.info(f"Setting up the program classes and subclasses.")

        # MAIN PROGRAM/WINDOW CLASS INITIALIZATION
        # Adds the primary window to the viewport
        self.program.initialize()
        dpg.set_primary_window(self.program.primary_window_tag, True)

        dpg.set_viewport_resize_callback(
            lambda: self.data.emitter.emit(
                Signals.VIEWPORT_RESIZED,
                width=dpg.get_viewport_width(),
                height=dpg.get_viewport_height(),
            )
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.info("Trying to shutdown...")
        if exc_type:
            logging.error(
                "An exception occurred: ", exc_info=(exc_type, exc_val, exc_tb)
            )

        logging.info("Updating settings...")

        self.config_manager.update_setting("last_exchange", self.program.last_exchange)

        logging.info("Done.")

        self.task_manager.run_task_until_complete(self.data.close_all_exchanges())
        self.task_manager.stop_all_tasks()
        dpg.destroy_context()
        logging.info("Destroyed DearPyGUI context.")
