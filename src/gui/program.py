import dearpygui.dearpygui as dpg
import dearpygui.demo as demo

from src.config import ConfigManager
from src.data.data_source import Data
from src.gui.components.chart import Chart
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager


class MenuBar:
    def __init__(self, emitter: SignalEmitter, data: Data, task_manger: TaskManager) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manger = task_manger
        with dpg.menu_bar(tag=self.tag):            
            
            with dpg.menu(label="DPG"):
                with dpg.menu(label="Tools"):
                    dpg.add_menu_item(label="Show Demo", callback=demo.show_demo)
                    dpg.add_menu_item(label="Show About", callback=lambda:dpg.show_tool(dpg.mvTool_About))
                    dpg.add_menu_item(label="Show Metrics", callback=lambda:dpg.show_tool(dpg.mvTool_Metrics))
                    dpg.add_menu_item(label="Show Documentation", callback=lambda:dpg.show_tool(dpg.mvTool_Doc))
                    dpg.add_menu_item(label="Show Debug", callback=lambda:dpg.show_tool(dpg.mvTool_Debug))
                    dpg.add_menu_item(label="Show Style Editor", callback=lambda:dpg.show_tool(dpg.mvTool_Style))
                    dpg.add_menu_item(label="Show Font Manager", callback=lambda:dpg.show_tool(dpg.mvTool_Font))
                    dpg.add_menu_item(label="Show Item Registry", callback=lambda:dpg.show_tool(dpg.mvTool_ItemRegistry))


            with dpg.menu(label="Exchanges"):
                dpg.add_listbox(list(self.data.exchange_list.keys()), callback=lambda s, a, u: self.emitter.emit(Signals.CREATE_CHART, exchange=a))

class Program:

    """
    This is the MainWindow class which contains the set up of other windows, the navigation bar, etc.
    """

    def __init__(self, emitter: SignalEmitter, data: Data, task_manager: TaskManager, config_manager: ConfigManager) -> None:
        self.primary_window_tag = 'PRIMARY_WINDOW'
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        self.config_manager = config_manager
        
        self.last_exchange = self.config_manager.get_setting('last_exchange')
        self.exchange_settings = self.config_manager.get_setting(self.last_exchange)
        self.last_symbol = self.exchange_settings['last_symbol'] if self.exchange_settings else None
        self.last_timeframe = self.exchange_settings['last_timeframe'] if self.exchange_settings else None
        
        self.emitter.register(Signals.CREATE_CHART, callback=self.create_chart)
        
    def initialize(self):
        with dpg.window(tag=self.primary_window_tag, menubar=True):
            self.menu_bar: MenuBar = MenuBar(self.emitter, self.data, self.task_manager)
            self.create_chart(self.last_exchange)
            if self.last_exchange:
                self.chart.task_manager.start_stream(self.last_exchange, self.last_symbol, self.last_timeframe, False)
            
    def create_chart(self, exchange):
        if self.last_exchange != exchange and dpg.does_alias_exist(self.last_exchange):
            dpg.delete_item(self.last_exchange)
            
        self.last_exchange = exchange
        self.chart: Chart = Chart(self.primary_window_tag, exchange, self.emitter, self.data, self.task_manager, self.config_manager)