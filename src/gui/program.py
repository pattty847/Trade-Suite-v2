import logging
import dearpygui.dearpygui as dpg
from src.data.data_source import Data
from src.gui import tags

from src.gui.components.test_window import Window

from .signals import Signals, SignalEmitter
from src.gui.components.chart import Chart
from src.gui.tags import PRIMARY_WINDOW


class Program:

    """
    This is the MainWindow class which contains the set up of other windows, the navigation bar, etc.
    """

    def __init__(self, emitter: SignalEmitter, data: Data) -> None:
        self.emitter = emitter
        self.data = data
        
        self.active_windows = {}
        self.emitter.register(Signals.CREATE_CHART, self.create_chart_window)

    def run(self):
        logging.info(f"Building MainWindow UI.")
        
        # This is the primary window for the application
        with dpg.window(tag=PRIMARY_WINDOW, label="Label"):
            # with dpg.menu_bar():
            #     with dpg.menu(label='Exchanges'):
            #         dpg.add_listbox(
            #             default_value=self.data.exchanges[0],
            #             items=self.data.exchanges,
            #             callback=lambda s, a: self.emitter.emit(Signals.CREATE_CHART, a)
            #         )
            Chart(
                self.emitter, 
                self.data,
                exchange='coinbasepro'
            )
                
                
    def create_chart_window(self, exchange):
        chart = Chart(
            self.emitter, 
            self.data,
            exchange=exchange
        )
        
        self.active_windows[chart.uuid] = chart