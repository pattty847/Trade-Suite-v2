import asyncio
import dearpygui.dearpygui as dpg
import dearpygui.demo as demo

from src.data.data_source import Data
from src.gui import tags
from src.gui.components.chart import Chart
from src.gui.signals import Signals, SignalEmitter
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

                with dpg.menu(label="Settings"):
                    dpg.add_menu_item(label="Wait For Input", check=True, callback=lambda s, a: dpg.configure_app(wait_for_input=a))
                    dpg.add_menu_item(label="Toggle Fullscreen", callback=lambda:dpg.toggle_viewport_fullscreen())

class Program:

    """
    This is the MainWindow class which contains the set up of other windows, the navigation bar, etc.
    """

    def __init__(self, emitter: SignalEmitter, data: Data, task_manager: TaskManager) -> None:
        self.tag = tags.PRIMARY_WINDOW
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
        
    def initialize(self):
        with dpg.window(tag=self.tag, menubar=True):
            self.menu_bar: MenuBar = MenuBar(self.emitter, self.data, self.task_manager)
            self.chart: Chart = Chart(self.emitter, self.data, self.task_manager)