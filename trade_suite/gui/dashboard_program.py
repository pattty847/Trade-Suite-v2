import logging
import dearpygui.dearpygui as dpg
import dearpygui.demo as demo

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import searcher
from trade_suite.gui.widgets import (
    DashboardManager,
    ChartWidget,
    OrderbookWidget,
    TradingWidget,
)


class DashboardProgram:
    """
    Main program class that uses the dockable widgets system.
    This replaces the original Program class with a more flexible dashboard approach.
    """

    def __init__(
        self,
        parent,
        data: Data,
        task_manager: TaskManager, 
        config_manager: ConfigManager,
        dashboard_manager: DashboardManager = None
    ):
        """
        Initialize the dashboard program.
        
        Args:
            parent: Parent window
            data: Data source instance
            task_manager: Task manager for async operations
            config_manager: Configuration manager
            dashboard_manager: Dashboard manager for widget layout (created if None)
        """
        self.parent = parent
        self.data = data
        self.emitter = data.emitter
        self.task_manager = task_manager
        self.config_manager = config_manager
        
        # Create dashboard manager if not provided
        self.dashboard_manager = dashboard_manager or DashboardManager(
            emitter=self.emitter,
            default_layout_file="config/factory_layout.ini",
            user_layout_file="config/user_layout.ini",
        )
        
        # Store references to widgets by exchange
        self.widgets = {}
        
        # Track default exchange
        self.default_exchange = self.config_manager.get_setting("default_exchange") or 'coinbase'
        
        # Register event handlers
        self._register_event_handlers()

    def _register_event_handlers(self):
        """Register event handlers for signals."""
        self.emitter.register(Signals.SYMBOL_CHANGED, self._on_symbol_changed)
        self.emitter.register(Signals.CREATE_EXCHANGE_TAB, self._on_create_exchange)
        self.emitter.register(Signals.NEW_CHART_REQUESTED, self._show_new_chart_dialog)
        self.emitter.register(Signals.NEW_ORDERBOOK_REQUESTED, self._show_new_orderbook_dialog)
        self.emitter.register(Signals.NEW_TRADING_PANEL_REQUESTED, self._show_new_trading_dialog)

    def initialize(self):
        """Initialize the dashboard program."""
        # Initialize dashboard layout
        # self.dashboard_manager.initialize_layout()
        
        # Set up the menu bar
        self._setup_menu_bar()
        
        # Create widgets for each exchange
        if self.data.exchange_list:
            for exchange_id in self.data.exchange_list:
                self._create_widgets_for_exchange(exchange_id)
        else:
            logging.warning("No exchanges found in the data source.")

    def _setup_menu_bar(self):
        """Set up the main menu bar."""
        # Skip creating menu bar if there's no parent window
        # Since we now have a viewport-level menu bar, this is fine
        if self.parent is None:
            logging.info("No parent window for menu bar, skipping window-level menu bar creation")
            return
            
        with dpg.menu_bar(parent=self.parent):
            with dpg.menu(label="File"):
                dpg.add_menu_item(
                    label="New Chart", 
                    callback=lambda: self._show_new_chart_dialog()
                )
                dpg.add_menu_item(
                    label="New Orderbook", 
                    callback=lambda: self._show_new_orderbook_dialog()
                )
                dpg.add_menu_item(
                    label="New Trading Panel", 
                    callback=lambda: self._show_new_trading_dialog()
                )
                dpg.add_separator()
                dpg.add_menu_item(
                    label="Save Layout", 
                    callback=self.dashboard_manager.save_layout
                )
                dpg.add_menu_item(
                    label="Reset Layout", 
                    callback=self.dashboard_manager.reset_to_default
                )
                dpg.add_separator()
                dpg.add_menu_item(
                    label="Exit", 
                    callback=lambda: dpg.stop_dearpygui()
                )
            
            with dpg.menu(label="View"):
                dpg.add_menu_item(
                    label="Layout Tools", 
                    callback=lambda: self.dashboard_manager.create_layout_tools()
                )
                dpg.add_menu_item(
                    label="Debug Tools",
                    callback=lambda: self._create_debug_window()
                )
            
            with dpg.menu(label="New Exchange"):
                input_tag = dpg.add_input_text(label="Search")
                exchange_list = dpg.add_listbox(
                    items=list(self.data.exchanges),
                    callback=lambda s, a, u: self._on_create_exchange(a),
                    num_items=10,
                )
                dpg.set_item_callback(
                    input_tag,
                    callback=lambda: searcher(
                        input_tag, exchange_list, list(self.data.exchanges)
                    ),
                )

    def _on_create_exchange(self, exchange):
        """Handle creating a new exchange tab."""
        if exchange not in self.data.exchange_list:
            # Load the exchange if not already loaded
            self.task_manager.run_task_with_loading_popup(
                self.data.load_exchanges(exchanges=exchange),
                message=f"Loading exchange {exchange}..."
            )
        
        # Create widgets for the exchange
        self._create_widgets_for_exchange(exchange)

    def _create_widgets_for_exchange(self, exchange):
        """Create widgets for an exchange."""
        if exchange in self.widgets:
            logging.info(f"Widgets for {exchange} already exist, skipping creation.")
            return
            
        # Get exchange settings
        exchange_settings = self.config_manager.get_setting(exchange) or {}
        
        # Determine default symbol and timeframe
        default_symbol = exchange_settings.get('last_symbol') or self._get_default_symbol(exchange)
        default_timeframe = exchange_settings.get('last_timeframe') or self._get_default_timeframe(exchange)
        
        # Create chart widget
        chart_widget = ChartWidget(
            emitter=self.emitter,
            exchange=exchange,
            symbol=default_symbol,
            timeframe=default_timeframe,
        )
        self.dashboard_manager.add_widget(f"{exchange}_chart", chart_widget)
        
        # Create orderbook widget
        orderbook_widget = OrderbookWidget(
            emitter=self.emitter,
            exchange=exchange,
            symbol=default_symbol,
        )
        self.dashboard_manager.add_widget(f"{exchange}_orderbook", orderbook_widget)
        
        # Create trading widget
        trading_widget = TradingWidget(
            emitter=self.emitter,
            exchange=exchange,
            symbol=default_symbol,
        )
        self.dashboard_manager.add_widget(f"{exchange}_trading", trading_widget)
        
        # Store references to widgets
        self.widgets[exchange] = {
            'chart': chart_widget,
            'orderbook': orderbook_widget,
            'trading': trading_widget,
        }
        
        # Start data streams
        self._start_data_streams_for_exchange(exchange, default_symbol, default_timeframe)
        
        logging.info(f"Created widgets for exchange: {exchange}")

    def _start_data_streams_for_exchange(self, exchange, symbol, timeframe):
        """Start data streams for an exchange."""
        # Create a unique ID for the chart widget's tab
        chart_widget = self.widgets[exchange]['chart']
        tab_id = chart_widget.window_tag
        
        # Start the stream for the chart
        self.task_manager.start_stream_for_chart(
            tab=tab_id,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
        )
        
        logging.info(f"Started data streams for {exchange} {symbol} {timeframe}")

    def _on_symbol_changed(self, exchange, tab, new_symbol):
        """Handle symbol change events between widgets."""
        # Check if this is a widget for one of our exchanges
        for widget_exchange, widgets in self.widgets.items():
            if widget_exchange == exchange:
                # Get the widget that originated the change
                originating_widget = None
                for widget_name, widget in widgets.items():
                    if widget.window_tag == tab:
                        originating_widget = widget
                        break
                
                # Propagate to other widgets for the same exchange
                if originating_widget:
                    for widget_name, widget in widgets.items():
                        if widget.window_tag != tab:  # Don't re-emit to the originator
                            self.emitter.emit(
                                Signals.SYMBOL_CHANGED,
                                exchange=exchange,
                                tab=widget.window_tag,
                                new_symbol=new_symbol
                            )
    
    def _get_default_symbol(self, exchange):
        """Get the default symbol for an exchange."""
        if exchange not in self.data.exchange_list:
            return "BTC/USD"
            
        symbols = self.data.exchange_list[exchange].symbols
        # Try to find a Bitcoin market
        for symbol in ["BTC/USD", "BTC/USDT"]:
            if symbol in symbols:
                return symbol
                
        # Return the first symbol if no Bitcoin market found
        return symbols[0] if symbols else "BTC/USD"
    
    def _get_default_timeframe(self, exchange):
        """Get the default timeframe for an exchange."""
        if exchange not in self.data.exchange_list:
            return "1h"
            
        timeframes = list(self.data.exchange_list[exchange].timeframes.keys())
        # Try to find a 1h timeframe
        if "1h" in timeframes:
            return "1h"
            
        # Return the second timeframe (usually better than the first which is often too short)
        return timeframes[1] if len(timeframes) > 1 else timeframes[0]
    
    def _show_new_chart_dialog(self):
        """Show dialog to create a new chart widget."""
        with dpg.window(label="New Chart", modal=True, width=300, height=200):
            combo_exchange = dpg.add_combo(
                label="Exchange",
                items=list(self.data.exchange_list.keys()),
                default_value=self.default_exchange
            )
            
            # Get symbols for the default exchange
            symbols = self.data.exchange_list[self.default_exchange].symbols
            combo_symbol = dpg.add_combo(
                label="Symbol",
                items=symbols,
                default_value=self._get_default_symbol(self.default_exchange)
            )
            
            # Get timeframes for the default exchange
            timeframes = list(self.data.exchange_list[self.default_exchange].timeframes.keys())
            combo_timeframe = dpg.add_combo(
                label="Timeframe",
                items=timeframes,
                default_value=self._get_default_timeframe(self.default_exchange)
            )
            
            # Update symbols and timeframes when exchange changes
            def update_symbols_timeframes(sender, app_data):
                exchange = app_data
                symbols = self.data.exchange_list[exchange].symbols
                timeframes = list(self.data.exchange_list[exchange].timeframes.keys())
                
                dpg.configure_item(combo_symbol, items=symbols)
                dpg.configure_item(combo_timeframe, items=timeframes)
                
                # Set defaults
                dpg.set_value(combo_symbol, self._get_default_symbol(exchange))
                dpg.set_value(combo_timeframe, self._get_default_timeframe(exchange))
            
            dpg.set_item_callback(combo_exchange, update_symbols_timeframes)
            
            def create_chart():
                exchange = dpg.get_value(combo_exchange)
                symbol = dpg.get_value(combo_symbol)
                timeframe = dpg.get_value(combo_timeframe)
                
                # Create unique ID for the widget
                widget_id = f"chart_{exchange}_{symbol}_{timeframe}".lower().replace("/", "")
                
                # Create the chart widget
                chart_widget = ChartWidget(
                    emitter=self.emitter,
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                self.dashboard_manager.add_widget(widget_id, chart_widget)
                
                # Start data stream for the new chart
                self.task_manager.start_stream_for_chart(
                    tab=chart_widget.window_tag,
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                
                # Close the dialog
                dpg.delete_item(dpg.last_item())
            
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=create_chart)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dpg.current_item_parent()))
    
    def _show_new_orderbook_dialog(self):
        """Show dialog to create a new orderbook widget."""
        with dpg.window(label="New Orderbook", modal=True, width=300, height=150):
            combo_exchange = dpg.add_combo(
                label="Exchange",
                items=list(self.data.exchange_list.keys()),
                default_value=self.default_exchange
            )
            
            # Get symbols for the default exchange
            symbols = self.data.exchange_list[self.default_exchange].symbols
            combo_symbol = dpg.add_combo(
                label="Symbol",
                items=symbols,
                default_value=self._get_default_symbol(self.default_exchange)
            )
            
            # Update symbols when exchange changes
            def update_symbols(sender, app_data):
                exchange = app_data
                symbols = self.data.exchange_list[exchange].symbols
                dpg.configure_item(combo_symbol, items=symbols)
                dpg.set_value(combo_symbol, self._get_default_symbol(exchange))
            
            dpg.set_item_callback(combo_exchange, update_symbols)
            
            def create_orderbook():
                exchange = dpg.get_value(combo_exchange)
                symbol = dpg.get_value(combo_symbol)
                
                # Create unique ID for the widget
                widget_id = f"orderbook_{exchange}_{symbol}".lower().replace("/", "")
                
                # Create the orderbook widget
                orderbook_widget = OrderbookWidget(
                    emitter=self.emitter,
                    exchange=exchange,
                    symbol=symbol,
                )
                self.dashboard_manager.add_widget(widget_id, orderbook_widget)
                
                # Start orderbook stream
                stream_id = f"orderbook_{exchange}_{symbol}_{orderbook_widget.window_tag}"
                self.task_manager.start_task(
                    stream_id,
                    self.data.watch_orderbook(orderbook_widget.window_tag, exchange, symbol)
                )
                
                # Close the dialog
                dpg.delete_item(dpg.last_item())
            
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=create_orderbook)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dpg.current_item_parent()))
    
    def _show_new_trading_dialog(self):
        """Show dialog to create a new trading widget."""
        with dpg.window(label="New Trading Panel", modal=True, width=300, height=150):
            combo_exchange = dpg.add_combo(
                label="Exchange",
                items=list(self.data.exchange_list.keys()),
                default_value=self.default_exchange
            )
            
            # Get symbols for the default exchange
            symbols = self.data.exchange_list[self.default_exchange].symbols
            combo_symbol = dpg.add_combo(
                label="Symbol",
                items=symbols,
                default_value=self._get_default_symbol(self.default_exchange)
            )
            
            # Update symbols when exchange changes
            def update_symbols(sender, app_data):
                exchange = app_data
                symbols = self.data.exchange_list[exchange].symbols
                dpg.configure_item(combo_symbol, items=symbols)
                dpg.set_value(combo_symbol, self._get_default_symbol(exchange))
            
            dpg.set_item_callback(combo_exchange, update_symbols)
            
            def create_trading_panel():
                exchange = dpg.get_value(combo_exchange)
                symbol = dpg.get_value(combo_symbol)
                
                # Create unique ID for the widget
                widget_id = f"trading_{exchange}_{symbol}".lower().replace("/", "")
                
                # Create the trading widget
                trading_widget = TradingWidget(
                    emitter=self.emitter,
                    exchange=exchange,
                    symbol=symbol,
                )
                self.dashboard_manager.add_widget(widget_id, trading_widget)
                
                # Close the dialog
                dpg.delete_item(dpg.last_item())
            
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=create_trading_panel)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dpg.current_item_parent()))
    
    def _create_debug_window(self):
        """Create a window with debug information and tools."""
        debug_window = dpg.generate_uuid()
        with dpg.window(label="Debug Tools", tag=debug_window, width=300, height=200):
            dpg.add_text("DearPyGUI Debug Tools")
            dpg.add_separator()
            
            dpg.add_button(
                label="Show DearPyGUI Demo",
                callback=lambda: demo.show_demo()
            )
            
            dpg.add_button(
                label="Show Item Registry",
                callback=lambda: dpg.show_tool(dpg.mvTool_ItemRegistry)
            )
            
            dpg.add_button(
                label="Show Metrics",
                callback=lambda: dpg.show_tool(dpg.mvTool_Metrics)
            )
            
            dpg.add_button(
                label="Show About",
                callback=lambda: dpg.show_tool(dpg.mvTool_About)
            )
            
            dpg.add_button(
                label="Save Current Layout",
                callback=self.dashboard_manager.save_layout
            ) 