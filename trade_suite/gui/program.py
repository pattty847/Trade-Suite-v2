import dearpygui.dearpygui as dpg
import dearpygui.demo as demo
import ccxt.pro as ccxt

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.components.chart import Chart
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import searcher


class MenuBar:
    def __init__(
        self, emitter: SignalEmitter, data: Data, task_manger: TaskManager
    ) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manger = task_manger
        with dpg.menu_bar(tag=self.tag):
            with dpg.menu(label="DPG"):
                with dpg.menu(label="Tools"):
                    dpg.add_menu_item(label="Show Demo", callback=demo.show_demo)
                    dpg.add_menu_item(
                        label="Show About",
                        callback=lambda: dpg.show_tool(dpg.mvTool_About),
                    )
                    dpg.add_menu_item(
                        label="Show Metrics",
                        callback=lambda: dpg.show_tool(dpg.mvTool_Metrics),
                    )
                    dpg.add_menu_item(
                        label="Show Documentation",
                        callback=lambda: dpg.show_tool(dpg.mvTool_Doc),
                    )
                    dpg.add_menu_item(
                        label="Show Debug",
                        callback=lambda: dpg.show_tool(dpg.mvTool_Debug),
                    )
                    dpg.add_menu_item(
                        label="Show Style Editor",
                        callback=lambda: dpg.show_tool(dpg.mvTool_Style),
                    )
                    dpg.add_menu_item(
                        label="Show Font Manager",
                        callback=lambda: dpg.show_tool(dpg.mvTool_Font),
                    )
                    dpg.add_menu_item(
                        label="Show Item Registry",
                        callback=lambda: dpg.show_tool(dpg.mvTool_ItemRegistry),
                    )

            with dpg.menu(label="Exchanges"):
                with dpg.menu(label="My Exchanges"):
                    dpg.add_listbox(
                        list(self.data.exchange_list.keys()),
                        callback=lambda s, a, u: self.emitter.emit(
                            Signals.CREATE_EXCHANGE_TAB, exchange=a
                        ),
                    )
                with dpg.menu(label="All Exchanges"):
                    input_tag = dpg.add_input_text(label="Search")
                    exchange_list = dpg.add_listbox(
                        list(ccxt.exchanges),
                        callback=lambda s, a, u: self.emitter.emit(
                            Signals.CREATE_EXCHANGE_TAB, exchange=a
                        ),
                        num_items=10
                    )
                    dpg.set_item_callback(input_tag, callback=lambda: searcher(input_tag, exchange_list, list(ccxt.exchanges)))


class Program:

    """
    This is the MainWindow class which contains the set up of other windows, the navigation bar, etc.
    """

    def __init__(
        self, data: Data, task_manager: TaskManager, config_manager: ConfigManager
    ) -> None:
        self.primary_window_tag = "PRIMARY_WINDOW"
        self.emitter = data.emitter
        self.data = data
        self.task_manager = task_manager
        self.config_manager = config_manager

        self.last_exchange = self.config_manager.get_setting("last_exchange")
        self.exchange_settings = self.config_manager.get_setting(self.last_exchange)
        self.last_symbol = (
            self.exchange_settings["last_symbol"] if self.exchange_settings else None
        )
        self.last_timeframe = (
            self.exchange_settings["last_timeframe"] if self.exchange_settings else None
        )

        self.emitter.register(Signals.CREATE_EXCHANGE_TAB, callback=self.create_exchange_tab)

    # First function called after DearPyGUI is setup
    def initialize(self):
        """
        The initialize function is called when the program starts.
        It creates a window with a menu bar and tab bar.
        The tab bar has tabs for each exchange in the data object's exchange_list attribute.
        
        :param self: Refer to the object that is being created
        :return: A tuple of the tab_bar and menu_bar
        :doc-author: Trelent
        """
        with dpg.window(tag=self.primary_window_tag, menubar=True):
            self.menu_bar: MenuBar = MenuBar(self.emitter, self.data, self.task_manager)

            with dpg.tab_bar(
                callback=self.task_manager.set_visable_tab
            ) as self.tab_bar:
                if self.data.exchange_list:
                    # Check if last_exchange exists and is valid
                    for exchange in self.data.exchange_list:
                        self.create_exchange_tab(exchange)
                    # The first tab's id needs to be set initially as the visable tab
                    self.task_manager.visable_tab = dpg.get_item_children(self.tab_bar)[1][0]

    def create_exchange_tab(self, exchange):
        """
        The create_exchange_tab function is used to create a new tab for the exchange that was selected.
            It will check if the exchange has already been loaded, and if not it will load it.
            Then it creates a new Chart object with all of its parameters.
        
        :param self: Represent the instance of the object itself
        :param exchange: Determine which exchange to load
        :return: The chart class, which is a widget
        :doc-author: Trelent
        """
        if exchange not in self.data.exchange_list:
            self.task_manager.run_task_with_loading_popup(self.data.load_exchanges(exchange=exchange))
            self.chart: Chart = Chart(
                parent=self.tab_bar,
                exchange=exchange,
                emitter=self.emitter,
                data=self.data,
                task_manager=self.task_manager,
                config_manager=self.config_manager,
            )
        else:
            self.chart: Chart = Chart(
                parent=self.tab_bar,
                exchange=exchange,
                emitter=self.emitter,
                data=self.data,
                task_manager=self.task_manager,
                config_manager=self.config_manager,
            )
