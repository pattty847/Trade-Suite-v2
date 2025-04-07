import asyncio
import logging
from typing import Dict, List

import dearpygui.dearpygui as dpg
import dearpygui.demo as demo
import ccxt.pro as ccxt

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.components.chart import Chart
from trade_suite.gui.components.tpo import TAB
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import searcher
from trade_suite.data.state import StateManager


class MenuBar:
    def __init__(
        self, emitter: SignalEmitter, data: Data, task_manager: TaskManager
    ) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager
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

            with dpg.menu(label="New Chart"):
                input_tag = dpg.add_input_text(label="Search")
                exchange_list_menu_bar = dpg.add_listbox(
                    list(ccxt.exchanges),
                    callback=lambda s, a, u: self.emitter.emit(
                        Signals.CREATE_EXCHANGE_TAB, exchange=a
                    ),
                    num_items=10,
                )
                dpg.set_item_callback(
                    input_tag,
                    callback=lambda: searcher(
                        input_tag, exchange_list_menu_bar, list(ccxt.exchanges)
                    ),
                )

            with dpg.menu(label="Tab Testing"):
                new_tab_search = dpg.add_input_text(label="Search")
                new_tab_exchange_list = dpg.add_listbox(
                    list(ccxt.exchanges),
                    callback=lambda s, a, u: self.emitter.emit(
                        Signals.CREATE_TAB, exchange=a
                    ),
                    num_items=10,
                )
                dpg.set_item_callback(
                    new_tab_search,
                    callback=lambda: searcher(
                        new_tab_search, new_tab_exchange_list, list(ccxt.exchanges)
                    ),
                )


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
        self.state_manager: StateManager = StateManager()

        self.default_exchange = self.config_manager.get_setting("default_exchange")
        self.exchange_settings = self.config_manager.get_setting(self.default_exchange)
        self.last_symbol = (
            self.exchange_settings["last_symbol"] if self.exchange_settings else None
        )
        self.last_timeframe = (
            self.exchange_settings["last_timeframe"] if self.exchange_settings else None
        )

        self.charts = {}

        self.emitter.register(
            Signals.CREATE_EXCHANGE_TAB,
            callback=self.create_exchange_tab,
        )
        self.emitter.register(
            Signals.CREATE_TAB,
            callback=self.create_tab,
        )

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
                # If the user initialized the Data class with a list of exchanges, we'll create tabs for each one of them
                if self.data.exchange_list:
                    # Check if default_exchange exists and is valid
                    for exchange_id, _ in self.data.exchange_list.items():
                        self.create_exchange_tab(exchange_id)
                    # The visable tab will need to be set to the first chart
                    self.task_manager.visable_tab = dpg.get_item_children(self.tab_bar)[
                        1
                    ][0]

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
            # TODO: Add popup for error when exchange connot be loaded and why
            self.task_manager.run_task_with_loading_popup(
                self.data.load_exchanges(exchanges=exchange)
            )
            chart: Chart = Chart(
                parent=self.tab_bar,
                exchange=exchange,
                emitter=self.emitter,
                data=self.data,
                task_manager=self.task_manager,
                config_manager=self.config_manager,
                state_manager=self.state_manager,
            )
        else:
            chart: Chart = Chart(
                parent=self.tab_bar,
                exchange=exchange,
                emitter=self.emitter,
                data=self.data,
                task_manager=self.task_manager,
                config_manager=self.config_manager,
                state_manager=self.state_manager,
            )
        self.charts["Chart", chart.tab_id]: Chart = chart

    def create_tab(self, exchange):
        tab = TAB(
            parent=self.tab_bar,
            exchange=exchange,
            emitter=self.emitter,
            data=self.data,
            task_manager=self.task_manager,
            config_manager=self.config_manager,
        )
        self.charts["TPO", tab.tab_id]: TAB = tab
