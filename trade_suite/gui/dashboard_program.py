import logging
import dearpygui.dearpygui as dpg
import dearpygui.demo as demo

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.data.sec_api import SECDataFetcher
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import searcher, center_window
from trade_suite.gui.widgets import (
    DashboardManager,
    ChartWidget,
    OrderbookWidget,
    TradingWidget,
    PriceLevelWidget,
    SECFilingViewer,
)


class DashboardProgram:
    """
    Main program class that uses the dockable widgets system.
    This replaces the original Program class with a more flexible dashboard approach.
    TODO: As the file grows, it should be refactored into multiple files, breaking down the dialog creation/handling 
    logic into separate UI components or helper classes.
    """

    def __init__(
        self,
        parent,
        data: Data,
        task_manager: TaskManager, 
        config_manager: ConfigManager,
        dashboard_manager: DashboardManager,
        sec_fetcher: SECDataFetcher,
    ):
        """
        Initialize the dashboard program.
        
        Args:
            parent: Parent window
            data: Data source instance
            task_manager: Task manager for async operations
            config_manager: Configuration manager
            dashboard_manager: Dashboard manager for widget layout
            sec_fetcher: SEC data fetcher instance
        """
        self.parent = parent
        self.data = data
        self.emitter = data.emitter
        self.task_manager = task_manager
        self.config_manager = config_manager
        self.dashboard_manager = dashboard_manager
        self.sec_fetcher = sec_fetcher
        
        # Store references to widgets by exchange
        self.widgets = {}
        
        # Track default exchange
        self.default_exchange = self.config_manager.get_setting("default_exchange") or 'coinbase'
        
        # Counter for unique SEC Viewer instances
        self._sec_viewer_count = 0
        
        # Register event handlers
        self._register_event_handlers()

    def _register_event_handlers(self):
        """Register event handlers for signals."""
        self.emitter.register(Signals.SYMBOL_CHANGED, self._on_symbol_changed)
        self.emitter.register(Signals.CREATE_EXCHANGE_TAB, self._on_create_exchange)
        self.emitter.register(Signals.NEW_CHART_REQUESTED, self._show_new_chart_dialog)
        self.emitter.register(Signals.NEW_ORDERBOOK_REQUESTED, self._show_new_orderbook_dialog)
        self.emitter.register(Signals.NEW_TRADING_PANEL_REQUESTED, self._show_new_trading_dialog)
        self.emitter.register(Signals.NEW_PRICE_LEVEL_REQUESTED, self._show_new_price_level_dialog)
        self.emitter.register(Signals.NEW_SEC_FILING_VIEWER_REQUESTED, self._handle_new_sec_viewer_request)

    def initialize(self):
        """Initialize the dashboard program."""
        # Create widgets for each exchange
        if self.data.exchange_list:
            for exchange_id in self.data.exchange_list:
                self._create_widgets_for_exchange(exchange_id)
        else:
            logging.warning("No exchanges found in the data source.")


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
        # TODO: Save/Load the last symbol and timeframe for each exchange
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
        # TODO: Figure out how to have these widget subscribe to data directly from the data source
        # TODO: Figure out how to handle duplicate widgets listening to the same data
        # {
        #     "chart": {"subscriptions": ["BTC/USD", "BTC/USDT"]}, 
        #     "orderbook": {"subscriptions": ["BTC/USD", "BTC/USDT"]},
        #     "trading": {"subscriptions": ["BTC/USD", "BTC/USDT"]}
        # }
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
        # TODO: How do we identify the chart widget, send data there, as well as duplicate widgets listening to the same data?
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
                
                # Start orderbook stream ONLY IF NOT ALREADY RUNNING
                # Use a consistent stream ID format
                stream_id = f"orderbook_{exchange}_{symbol}"
                if not self.task_manager.is_stream_running(stream_id):
                    logging.info(f"Starting orderbook stream {stream_id} for widget {orderbook_widget.window_tag}")
                    # Use the specific widget tag in the stream task name for potential finer control later?
                    # Maybe keep it generic for now: f"orderbook_{exchange}_{symbol}"
                    self.task_manager.start_task(
                        stream_id,
                        self.data.watch_orderbook(orderbook_widget.window_tag, exchange, symbol)
                    )
                else:
                    logging.info(f"Orderbook stream {stream_id} already running. New widget {orderbook_widget.window_tag} will use existing stream.")
                
                # Close the dialog
                # Need to delete the modal window itself, not just the button's parent group
                dpg.delete_item(combo_symbol) # Assuming combo_symbol is unique to this dialog instance
                parent_window = dpg.get_item_parent(combo_symbol) # Get the modal window tag
                if dpg.does_item_exist(parent_window):
                    dpg.delete_item(parent_window)
            
            with dpg.group(horizontal=True):
                dpg.add_button(label="Create", callback=create_orderbook)
                # Properly reference the modal window for cancel
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dpg.get_item_parent(dpg.last_item())))
    
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
    
    def _show_new_price_level_dialog(self):
        """Show a modal dialog to create a new price level widget."""
        modal_id = dpg.generate_uuid()
        # Correctly use the list of exchanges
        available_exchanges = self.data.exchanges
        selected_exchange = available_exchanges[0] if available_exchanges else None
        # Need to get symbols differently now, perhaps from data.exchange_list dictionary
        selected_symbol = self._get_default_symbol(selected_exchange) if selected_exchange else None

        if not available_exchanges:
            logging.error("Cannot create Price Level widget: No exchanges loaded.")
            return

        with dpg.window(label="New Price Level Widget", modal=True, tag=modal_id, width=400, no_close=True):
            # Exchange Selection
            exchange_combo = dpg.add_combo(
                label="Exchange",
                items=available_exchanges,
                default_value=selected_exchange
            )
            # Symbol Selection
            symbol_combo = dpg.add_combo(
                label="Symbol",
                items=[], # Start empty, populate on exchange change
                default_value=selected_symbol
            )
            # Tick Size Input (Optional, could use widget default)
            tick_size_input = dpg.add_input_float(
                label="Default Tick Size",
                default_value=1.0,
                min_value=0.00000001, # Allow very small ticks
                format="%.8f"
            )
            # Max Depth Input (Optional)
            max_depth_input = dpg.add_input_int(
                label="Max Depth Levels",
                default_value=15,
                min_value=5,
                max_value=100
            )

            # Callback to update symbols when exchange changes
            def update_symbols(sender, app_data):
                exchange = dpg.get_value(exchange_combo)
                symbols = []
                # Access symbols via the exchange_list dictionary
                if exchange and self.data.exchange_list and exchange in self.data.exchange_list:
                    symbols = self.data.exchange_list[exchange].symbols
                new_default_symbol = self._get_default_symbol(exchange) if symbols else None
                dpg.configure_item(symbol_combo, items=symbols, default_value=new_default_symbol)

            dpg.set_item_callback(exchange_combo, update_symbols)
            # Initial population
            update_symbols(None, None)

            with dpg.group(horizontal=True):
                # Callback for the create button
                def create_price_level():
                    exchange = dpg.get_value(exchange_combo)
                    symbol = dpg.get_value(symbol_combo)
                    tick_size = dpg.get_value(tick_size_input)
                    max_depth = dpg.get_value(max_depth_input)

                    if exchange and symbol:
                        # Generate a unique ID for the widget instance
                        widget_id = f"{exchange}_{symbol}_pricelevel_{dpg.generate_uuid()}".lower().replace("/", "")
                        try:
                            new_widget = PriceLevelWidget(
                                emitter=self.emitter,
                                exchange=exchange,
                                symbol=symbol,
                                instance_id=widget_id,
                                default_tick_size=tick_size,
                                max_depth=max_depth
                            )
                            self.dashboard_manager.add_widget(widget_id, new_widget)

                            # Start order book stream only if not already running
                            stream_id = f"orderbook_{exchange}_{symbol}" # Consistent ID
                            if not self.task_manager.is_stream_running(stream_id):
                                logging.info(f"Starting orderbook stream {stream_id} for PriceLevelWidget {new_widget.window_tag}")
                                # The PriceLevelWidget listens for ORDER_BOOK_UPDATE signals
                                # We need to start the generic watch_orderbook stream
                                # Pass a unique tag (e.g., the widget tag) so the data source knows where it originated?
                                # For now, let's assume the data source emits generically and widgets filter.
                                self.task_manager.start_task(
                                    stream_id, # Use the generic stream ID
                                    self.data.watch_orderbook(tab=new_widget.window_tag, exchange=exchange, symbol=symbol)
                                )
                            else:
                                logging.info(f"Orderbook stream {stream_id} already running. PriceLevelWidget {new_widget.window_tag} will use existing stream.")

                            logging.info(f"Created new price level widget: {widget_id}")
                            dpg.delete_item(modal_id) # Close the dialog
                        except Exception as e:
                            logging.error(f"Failed to create PriceLevelWidget {widget_id}: {e}", exc_info=True)
                    else:
                        logging.warning("Cannot create Price Level widget: missing exchange or symbol.")

                dpg.add_button(label="Create", callback=create_price_level, width=75)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(modal_id), width=75)

            center_window(modal_id) # Center the modal

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

    def _handle_new_sec_viewer_request(self):
        """Handles the request to create a new SEC Filing Viewer widget."""
        self._sec_viewer_count += 1
        instance_id = f"instance_{self._sec_viewer_count}"
        widget_id = f"sec_filing_viewer_{instance_id}"
        
        logging.info(f"Creating new SEC Filing Viewer with ID: {widget_id}")
        
        sec_viewer = SECFilingViewer(
            emitter=self.emitter,
            sec_fetcher=self.sec_fetcher,
            task_manager=self.task_manager,
            instance_id=instance_id
        )
        
        # Add the widget using the dashboard manager
        # It will be created and shown automatically if not part of the saved layout
        self.dashboard_manager.add_widget(widget_id, sec_viewer)
        # Explicitly show it if needed, or let docking handle it
        # sec_viewer.show() 