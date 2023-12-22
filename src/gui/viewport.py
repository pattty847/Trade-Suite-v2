from asyncio import Queue
import asyncio
import logging
import threading
import dearpygui.dearpygui as dpg

from src.data.data_source import Data
from src.gui.signals import Signals, SignalEmitter
from src.gui.program import Program
from src.gui.task_manager import TaskManager


class Viewport:
    def __init__(self, emitter: SignalEmitter, data: Data, loop: asyncio.AbstractEventLoop) -> None:
        self.emitter = emitter
        self.data = data
        self.loop = loop
        
        # TODO: Make the TaskManager, start the thread for itself in its class file. Remove the asyncio from this
        # file completely. 
        self.task_manager = TaskManager(loop)
        self.program: Program = None
        
    def __enter__(self):
        # Load the ccxt exchanges, symbols, and timeframes to the Data class
        # We need to wait for this to run and finish
        self.loop.run_until_complete(self.data.load_exchanges())
        
        # Setup dearpygui
        dpg.create_context()
        self.setup_dpg()
        return self
    
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
        dpg.set_frame_callback(1, lambda: self.initialize_program()) # not called until after start_dearpyui() has been called
        
        logging.info("DearPyGUI setup complete, launching event loop.")
        
        dpg.start_dearpygui() # main dpg event loop
    
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
        logging.info(f'Frame #1: Setting up the Program classes and subclasses.')
        
        # MAIN PROGRAM/WINDOW CLASS INITIALIZATION
        self.program = Program(self.emitter, self.data, self.task_manager)
        dpg.set_primary_window(self.program.tag, True)
        
        # Start the asyncio loop in a separate thread
        threading.Thread(target=self.start_asyncio_loop, daemon=True).start()
        
        # Register all signals here.
        
        # This could be a function to run this initialilze_program function but for the UI component
        # It will be a list of the below registering or emition.
        # self.program.componenet.register_callbacks()
        
        self.emitter.register(Signals.VIEWPORT_RESIZED, None)
        dpg.set_viewport_resize_callback(
            lambda: self.emitter.emit(
                Signals.VIEWPORT_RESIZED,
                width=dpg.get_viewport_width(),
                height=dpg.get_viewport_height(),
            )
        )
        
    def start_asyncio_loop(self):
        """
        The start_asyncio_loop function is a wrapper for the asyncio.run() function, which runs an event loop until it is stopped.
        The start_asyncio_loop function starts the event loop in a separate thread so that it can run concurrently with other code.
        
        :param self: Represent the instance of the class
        :return: Nothing
        :doc-author: Trelent
        """
        logging.info(f'Starting async thread.')
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logging.error(
                "An exception occurred: ", exc_info=(exc_type, exc_val, exc_tb)
            )
        asyncio.run_coroutine_threadsafe(self.data.close_all_exchanges(), self.loop)
        dpg.destroy_context()
        logging.info("Destroyed DearPyGUI context.")