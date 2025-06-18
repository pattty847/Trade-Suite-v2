import logging
import dearpygui.dearpygui as dpg
import dearpygui.demo as demo
import platform

from .widgets.dashboard_manager import DashboardManager
from ..core.facade import CoreServicesFacade
from ..core.signals import Signals
from ..config import ConfigManager
from ..gui.utils import center_window
from ..gui.utils import searcher


class DashboardProgram:
    """
    Main program class that uses the dockable widgets system.
    This class orchestrates the creation of widgets and the main menubar.
    """

    def __init__(self, core: CoreServicesFacade, config_manager: ConfigManager):
        """
        Initializes the DashboardProgram.
        """
        self.core = core
        self.config_manager = config_manager
        self.dashboard_manager = DashboardManager(core=self.core, config_manager=self.config_manager)
        
        self.default_exchange = self.config_manager.get_setting("default_exchange") or 'coinbase'

        self._setup_listeners()
        self._create_viewport_menubar()

    def initialize_layout(self):
        """Loads the widget layout from config."""
        self.dashboard_manager.initialize_layout()

    def on_viewport_resize(self, sender, app_data):
        """Callback for when the main viewport is resized."""
        width, height = dpg.get_viewport_width(), dpg.get_viewport_height()
        self.core.emitter.emit(
            Signals.VIEWPORT_RESIZED,
            width=width,
            height=height,
        )

    def _setup_listeners(self):
        """Register callbacks for signals."""
        self.core.emitter.register(Signals.NEW_CHART_REQUESTED, self._show_new_chart_dialog)
        self.core.emitter.register(Signals.NEW_ORDERBOOK_REQUESTED, self._show_new_orderbook_dialog)
        self.core.emitter.register(Signals.NEW_TRADING_PANEL_REQUESTED, self._show_new_trading_dialog)
        self.core.emitter.register(Signals.NEW_PRICE_LEVEL_REQUESTED, self._show_new_price_level_dialog)
        self.core.emitter.register(Signals.NEW_SEC_FILING_VIEWER_REQUESTED, self._show_new_sec_viewer_dialog)

    def _create_viewport_menubar(self):
        """Creates the main menubar attached to the viewport."""
        with dpg.viewport_menu_bar():
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="New Chart", callback=lambda: self.core.emitter.emit(Signals.NEW_CHART_REQUESTED))
                dpg.add_menu_item(label="New Orderbook", callback=lambda: self.core.emitter.emit(Signals.NEW_ORDERBOOK_REQUESTED))
                dpg.add_menu_item(label="New Trading Panel", callback=lambda: self.core.emitter.emit(Signals.NEW_TRADING_PANEL_REQUESTED))
                dpg.add_menu_item(label="New Price Level", callback=lambda: self.core.emitter.emit(Signals.NEW_PRICE_LEVEL_REQUESTED))
                dpg.add_menu_item(label="New SEC Filing Viewer", callback=lambda: self.core.emitter.emit(Signals.NEW_SEC_FILING_VIEWER_REQUESTED))
                dpg.add_separator()
                dpg.add_menu_item(label="Save Layout", callback=self.dashboard_manager.save_layout)
                dpg.add_menu_item(label="Reset Layout", callback=self.dashboard_manager.reset_to_default)
                dpg.add_separator()
                dpg.add_menu_item(label="Exit", callback=lambda: dpg.stop_dearpygui())
            
            with dpg.menu(label="View"):
                dpg.add_menu_item(label="Layout Tools", callback=self.dashboard_manager.create_layout_tools)
                dpg.add_menu_item(label="Debug Tools", callback=self._create_debug_window)

            self.exchange_menu_tag = "exchange_menu"
            dpg.add_menu(label="Exchange", tag=self.exchange_menu_tag)
            self._populate_exchange_menu()

    def _populate_exchange_menu(self):
        """Populates the 'Exchange' menu with a searchable list of exchanges."""
        if not self.core.data.exchange_list: 
            logging.warning("Populate exchange menu: No exchanges available.")
            return

        parent_menu = self.exchange_menu_tag
        
        if dpg.does_item_exist(parent_menu) and dpg.get_item_children(parent_menu, 1):
             for child in dpg.get_item_children(parent_menu, 1):
                dpg.delete_item(child)

        items = list(self.core.data.exchange_list.keys())
        
        input_tag = dpg.add_input_text(label="Search", parent=parent_menu, width=150)
        list_tag = dpg.add_listbox(
            items=items,
            parent=parent_menu,
            num_items=8,
            callback=lambda s, a, u: logging.info(f"Exchange '{a}' selected from menu (not implemented).")
        )
        
        dpg.set_item_callback(
            input_tag,
            callback=lambda: searcher(input_tag, list_tag, items)
        )
        
    def _show_new_chart_dialog(self):
        """Show dialog to create a new chart widget."""
        modal_id = dpg.generate_uuid()
        with dpg.window(label="New Chart", modal=True, tag=modal_id, width=300, no_close=True):
            center_window(modal_id)
            
            combo_exchange = dpg.add_combo(
                label="Exchange",
                items=list(self.core.data.exchange_list.keys()),
                default_value=self.default_exchange
            )
            
            symbols = self.core.data.exchange_list[self.default_exchange].symbols
            combo_symbol = dpg.add_combo(
                label="Symbol",
                items=symbols,
                default_value=symbols[0] if symbols else ""
            )
            
            timeframes = list(self.core.data.exchange_list[self.default_exchange].timeframes.keys())
            combo_timeframe = dpg.add_combo(
                label="Timeframe",
                items=timeframes,
                default_value="1h" if "1h" in timeframes else timeframes[0]
            )
            
            def update_options(sender, app_data):
                exchange = dpg.get_value(combo_exchange)
                symbols = self.core.data.exchange_list[exchange].symbols
                dpg.configure_item(combo_symbol, items=symbols, default_value=symbols[0] if symbols else "")
                
                timeframes = list(self.core.data.exchange_list[exchange].timeframes.keys())
                dpg.configure_item(combo_timeframe, items=timeframes, default_value="1h" if "1h" in timeframes else timeframes[0])
            
            dpg.set_item_callback(combo_exchange, update_options)
            
            def create_chart():
                exchange = dpg.get_value(combo_exchange)
                symbol = dpg.get_value(combo_symbol)
                timeframe = dpg.get_value(combo_timeframe)
                
                instance_id = f"ChartWidget_{exchange}_{symbol.replace('/', '_')}_{timeframe}_{dpg.generate_uuid()}"
                
                chart_widget = self.dashboard_manager.widget_classes["ChartWidget"](
                    core=self.core,
                    instance_id=instance_id,
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe
                )
                self.dashboard_manager.add_widget(instance_id, chart_widget)
                dpg.delete_item(modal_id)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=create_chart, width=75)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(modal_id), width=75)

    def _show_new_orderbook_dialog(self):
        self._show_generic_dialog("OrderbookWidget", "New Orderbook", ["exchange", "symbol"])

    def _show_new_trading_dialog(self):
        self._show_generic_dialog("TradingWidget", "New Trading Panel", ["exchange", "symbol"])
    
    def _show_new_price_level_dialog(self):
        self._show_generic_dialog("PriceLevelWidget", "New Price Level DOM", ["exchange", "symbol"])
        
    def _show_new_sec_viewer_dialog(self):
        instance_id = f"SECFilingViewer_{dpg.generate_uuid()}"
        widget_instance = self.dashboard_manager.widget_classes["SECFilingViewer"](
            core=self.core,
            instance_id=instance_id
        )
        self.dashboard_manager.add_widget(instance_id, widget_instance)

    def _show_generic_dialog(self, widget_class_name, title, params):
        modal_id = dpg.generate_uuid()
        with dpg.window(label=title, modal=True, tag=modal_id, width=300, no_close=True):
            center_window(modal_id)
            
            controls = {}
            if "exchange" in params:
                controls["exchange"] = dpg.add_combo(
                    label="Exchange",
                    items=list(self.core.data.exchange_list.keys()),
                    default_value=self.default_exchange
                )
            
            if "symbol" in params:
                symbols = self.core.data.exchange_list[self.default_exchange].symbols
                controls["symbol"] = dpg.add_combo(
                    label="Symbol",
                    items=symbols,
                    default_value=symbols[0] if symbols else ""
                )

            def update_symbols(sender, app_data):
                if "symbol" in controls and "exchange" in controls:
                    exchange = dpg.get_value(controls["exchange"])
                    symbols = self.core.data.exchange_list[exchange].symbols
                    dpg.configure_item(controls["symbol"], items=symbols, default_value=symbols[0] if symbols else "")
            
            if "exchange" in controls:
                dpg.set_item_callback(controls["exchange"], update_symbols)
            
            def create_widget():
                config = {param: dpg.get_value(controls[param]) for param in params}
                instance_id = f"{widget_class_name}_{'_'.join(config.values())}_{dpg.generate_uuid()}".replace('/', '_')
                
                widget_instance = self.dashboard_manager.widget_classes[widget_class_name](
                    core=self.core,
                    instance_id=instance_id,
                    **config
                )
                self.dashboard_manager.add_widget(instance_id, widget_instance)
                dpg.delete_item(modal_id)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=create_widget, width=75)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(modal_id), width=75)

    def _create_debug_window(self):
        """Creates a simple debug window."""
        with dpg.window(label="Debug Info", width=400, height=300):
            dpg.add_text(f"Platform: {platform.system()} {platform.release()}")
            dpg.add_text(f"Python: {platform.python_version()}")
            dpg.add_text(f"DearPyGui: {dpg.get_version()}")
            dpg.add_separator()
            dpg.add_text("Loaded Exchanges:")
            for ex in self.core.data.exchange_list.keys():
                dpg.add_text(ex)