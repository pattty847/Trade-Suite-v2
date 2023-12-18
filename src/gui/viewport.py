import logging
import dearpygui.dearpygui as dpg
import dearpygui.demo
from src.data.data_source import Data
from src.gui.signals import Signals, SignalEmitter

from src.gui.tags import PRIMARY_WINDOW
from src.gui.program import Program


class Viewport:
    def __init__(self, emitter: SignalEmitter, data: Data) -> None:
        self.emitter = emitter
        self.data = data

    def setup_dpg(self):
        logging.info("Setting up DearPyGUI loop, viewport, and primary window...")

        Program(self.emitter, self.data).run() # Main entrance to program/ui components and primary window referenced below

        dpg.create_viewport(title="Crpnto Dahsbrod", width=1200, height=720)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window(PRIMARY_WINDOW, True)

        logging.info("DearPyGUI setup complete, launching event loop.")
        
    def __enter__(self):
        dpg.create_context()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logging.error(
                "An exception occurred: ", exc_info=(exc_type, exc_val, exc_tb)
            )
        dpg.destroy_context()
        logging.info("Destroyed DearPyGUI context.")

    def run(self):
        self.setup_dpg()
        while dpg.is_dearpygui_running():
            dpg.render_dearpygui_frame()
