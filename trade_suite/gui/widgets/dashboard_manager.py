import os
import logging
from typing import Dict, Optional, List, Any, Type
import dearpygui.dearpygui as dpg

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget


class DashboardManager:
    """
    Manages dockable widgets and layout persistence.
    
    This class handles:
    - Adding/removing widgets to the dashboard
    - Saving/loading layout configurations
    - Managing widget visibility and state
    - Providing layout management tools
    """
    
    def __init__(
        self, 
        emitter: SignalEmitter,
        default_layout_file: str = "config/factory_layout.ini",
        user_layout_file: str = "config/user_layout.ini",
    ):
        """
        Initialize the dashboard manager.
        
        Args:
            emitter: Signal emitter for event communication
            default_layout_file: Path to the default/factory layout file
            user_layout_file: Path to the user's custom layout file
        """
        self.emitter = emitter
        self.default_layout = default_layout_file
        self.user_layout = user_layout_file
        
        # Widget registry maps widget_id to widget instance
        # TODO: Store the widgets plus the data streams they subscribe to
        # {
        #     "chart": {"subscriptions": ["BTC/USD", "BTC/USDT"]}, 
        #     "orderbook": {"subscriptions": ["BTC/USD", "BTC/USDT"]},
        #     "trading": {"subscriptions": ["BTC/USD", "BTC/USDT"]}
        # }
        self.widgets: Dict[str, DockableWidget] = {}
        
        # Create layout directories if they don't exist
        self._ensure_layout_directories()
        
        # Register event handlers
        self._register_handlers()
        
        # Track layout modification state
        self.layout_modified = False
    
    def initialize_layout(self, reset: bool = False) -> None:
        """
        Initialize the layout system using the configure_app method primarily.

        Args:
            reset: If True, reset to the default layout
        """
        # Handle reset: remove user layout if requested
        if reset and os.path.exists(self.user_layout):
            os.remove(self.user_layout)
            logging.info(f"Reset requested, removed user layout: {self.user_layout}")

        # Determine which layout file to load initially
        file_to_load = None
        load_default_layout = False

        if os.path.exists(self.user_layout):
            file_to_load = self.user_layout
            logging.info(f"User layout exists. Will load: {file_to_load}")
        elif os.path.exists(self.default_layout):
            file_to_load = self.default_layout
            load_default_layout = True  # Mark that we loaded the default
            logging.info(f"User layout not found. Will load default layout: {file_to_load}")
        else:
            logging.info("No existing layout file found. Will use default window arrangements.")

        # Configure DPG for docking and load the determined layout file.
        # init_file is set to the file we want to LOAD initially.
        # The save target might be adjusted afterwards if we loaded the default.
        dpg.configure_app(
            docking=True,
            docking_space=True,
            init_file=file_to_load if file_to_load else self.user_layout, # Load file if exists, else set default save target
            load_init_file=file_to_load is not None # Load only if a file was found
        )
        logging.info(f"Configured app. Initial load target: {file_to_load if file_to_load else 'None'}. Save target initially set to: {file_to_load if file_to_load else self.user_layout}")

        # IMPORTANT: If we loaded the DEFAULT layout, we need to redirect SAVES to the USER layout file.
        if load_default_layout:
            dpg.configure_app(init_file=self.user_layout)
            logging.info(f"Redirected save target to user layout file: {self.user_layout}")
    
    def add_widget(self, widget_id: str, widget: DockableWidget) -> int:
        """
        Add a widget to the dashboard.
        
        Args:
            widget_id: Unique identifier for the widget
            widget: The widget instance
            
        Returns:
            The widget's window ID
        """
        # Store in registry
        self.widgets[widget_id] = widget
        
        # Create the widget window
        window_id = widget.create()
        
        # Set layout modified flag
        self.layout_modified = True
        return window_id
    
    def remove_widget(self, widget_id: str) -> bool:
        """
        Remove a widget from the dashboard.
        
        Args:
            widget_id: ID of the widget to remove
            
        Returns:
            True if removed, False if not found
        """
        if widget_id in self.widgets:
            # Close the widget (destroys the window)
            self.widgets[widget_id].close()
            # Remove from registry
            del self.widgets[widget_id]
            # Set layout modified flag
            self.layout_modified = True
            return True
        return False
    
    def get_widget(self, widget_id: str) -> Optional[DockableWidget]:
        """
        Get a widget by ID.
        
        Args:
            widget_id: ID of the widget to retrieve
            
        Returns:
            The widget instance or None if not found
        """
        return self.widgets.get(widget_id)
    
    def reset_to_default(self) -> None:
        """Reset to the default layout."""
        if os.path.exists(self.user_layout):
            os.remove(self.user_layout)
            
        if os.path.exists(self.default_layout):
            # Load the default layout
            dpg.load_init_file(self.default_layout)
            # Refresh the UI
            self.emitter.emit(Signals.VIEWPORT_RESIZED, 
                              width=dpg.get_viewport_width(), 
                              height=dpg.get_viewport_height())
    
    def save_as_default(self) -> None:
        """Save current layout as the default."""
        dpg.save_init_file(self.default_layout)
        logging.info(f"Saved current layout as default: {self.default_layout}")
    
    def save_layout(self) -> None:
        """Save the current layout to the user layout file."""
        dpg.save_init_file(self.user_layout)
        self.layout_modified = False
        logging.info(f"Saved layout to: {self.user_layout}")
    
    def create_layout_tools(self) -> int:
        """
        Create a window with layout management tools.
        
        Returns:
            Window ID of the layout tools
        """
        # Create a widget for layout tools
        layout_tools_id = dpg.generate_uuid()
        
        with dpg.window(label="Layout Tools", tag=layout_tools_id, 
                       width=260, height=200, pos=[20, 20]):
            dpg.add_text("Layout Management")
            dpg.add_separator()
            
            dpg.add_button(
                label="Reset to Default Layout", 
                callback=self.reset_to_default,
                width=-1
            )
            
            dpg.add_button(
                label="Save Current as Default", 
                callback=self.save_as_default,
                width=-1
            )
            
            dpg.add_button(
                label="Save Current Layout", 
                callback=self.save_layout,
                width=-1
            )
            
            # Add debug info
            dpg.add_separator()
            dpg.add_text(f"Active Widgets: {len(self.widgets)}")
            
        return layout_tools_id
    
    def _ensure_layout_directories(self) -> None:
        """Ensure layout file directories exist."""
        # Create directories for layout files if they don't exist
        for file_path in [self.default_layout, self.user_layout]:
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logging.info(f"Created layout directory: {directory}")
    
    def _register_handlers(self) -> None:
        """Register event handlers for dashboard events."""
        # Could add custom dashboard events here
        pass
        
    def get_widget_ids(self) -> List[str]:
        """
        Get a list of all widget IDs.
        
        Returns:
            List of widget IDs
        """
        return list(self.widgets.keys())
    
    def is_layout_modified(self) -> bool:
        """
        Check if the layout has been modified since last save.
        
        Returns:
            True if modified, False otherwise
        """
        return self.layout_modified 