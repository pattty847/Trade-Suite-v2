import logging
import dearpygui.dearpygui as dpg
from typing import Dict, Any, Optional, Callable

from trade_suite.gui.signals import SignalEmitter


class DockableWidget:
    """Base class for all dockable widgets in the application.
    
    Provides common functionality for creating, managing, and docking widgets.
    Uses stable IDs to ensure widgets can be identified across sessions.
    """
    
    def __init__(
        self, 
        title: str, 
        widget_type: str, # e.g., 'chart', 'orderbook'
        emitter: SignalEmitter, 
        instance_id: Optional[str] = None, # e.g., 'default', 'coinbase_BTC/USD'
        width: int = 400,
        height: int = 300,
        **kwargs
    ):
        """Initialize a dockable widget.
        
        Args:
            title: Window title (used as label)
            widget_type: Type identifier for the widget (e.g., 'chart')
            emitter: Signal emitter for event communication
            instance_id: Unique ID for this specific instance (e.g., 'coinbase_BTC/USD')
            width: Initial window width
            height: Initial window height
            **kwargs: Additional window parameters
        """
        # --- Use widget_type and instance_id directly for a stable STRING tag ---
        self.widget_type = widget_type
        self.instance_id = instance_id or "default"
        # Create a stable, purely string-based tag
        # Example: "widget_chart_coinbase_btcusd_1h" or "widget_orderbook_default"
        self.window_tag = f"widget_{self.widget_type}_{self.instance_id}".lower().replace("/", "_").replace(" ", "_")
        
        logging.debug(f"Creating widget: title='{title}', type='{self.widget_type}', instance='{self.instance_id}', generated_tag='{self.window_tag}'")

        self.title = title # This will be the 'label'
        self.emitter = emitter
        self.width = width
        self.height = height
        self.kwargs = kwargs
        
        # Track if widget has been created yet
        self.is_created = False
        
        # Keep refs to child items for easier management (using the new window_tag)
        self.content_tag = f"{self.window_tag}_content"
        self.menu_bar_tag = f"{self.window_tag}_menu"
        self.status_bar_tag = f"{self.window_tag}_status"
        
    def create(self, parent: Optional[int] = None) -> str: # Return type is string tag
        """Create the dockable widget window.
        
        Args:
            parent: Optional parent container
            
        Returns:
            Widget window tag (string)
        """
        if self.is_created:
            # Check if item still exists, DPG might have removed it
            if dpg.does_item_exist(self.window_tag):
                logging.warning(f"Widget {self.title} (tag: {self.window_tag}) already created, returning existing tag")
                return self.window_tag
            else:
                logging.warning(f"Widget {self.title} (tag: {self.window_tag}) marked as created but DPG item doesn't exist. Recreating.")
                self.is_created = False # Force recreation
            
        window_kwargs = {
            "label": self.title, # User-friendly label
            "tag": self.window_tag,   # Stable, predictable string tag
            "width": self.width,
            "height": self.height,
            "no_saved_settings": False # Ensure saving is enabled (default)
        }
        window_kwargs.update(self.kwargs)
        
        if parent:
            window_kwargs["parent"] = parent
            
        # Check for potential tag collision before creating
        if dpg.does_item_exist(self.window_tag):
            logging.error(f"FATAL: Attempting to create window with duplicate tag: {self.window_tag}. Existing item type: {dpg.get_item_info(self.window_tag)['type']}")
            # Decide how to handle this - maybe raise error or return existing tag?
            # For now, let's log and return the existing tag, though this might hide issues.
            return self.window_tag

        try:
            with dpg.window(**window_kwargs):
                # Create menu bar if implemented by derived class
                if hasattr(self, "build_menu") and callable(getattr(self, "build_menu")):
                    # Ensure menu bar tag is unique if window tag had collision potential (though handled above)
                    self.menu_bar_tag = f"{self.window_tag}_menu"
                    with dpg.menu_bar(tag=self.menu_bar_tag):
                        self.build_menu()
                
                # Main content group
                self.content_tag = f"{self.window_tag}_content"
                with dpg.group(tag=self.content_tag):
                    self.build_content()
                
                # Optional status bar 
                if hasattr(self, "build_status_bar") and callable(getattr(self, "build_status_bar")):
                    self.status_bar_tag = f"{self.window_tag}_status"
                    with dpg.group(tag=self.status_bar_tag, horizontal=True):
                        self.build_status_bar()
            
            # Register event handlers
            self.register_handlers()
            self.is_created = True
            logging.debug(f"Successfully created window with tag: {self.window_tag}")
            
            return self.window_tag

        except Exception as e:
            logging.error(f"Error creating window with tag {self.window_tag}: {e}", exc_info=True)
            # Attempt to clean up if window creation failed partially?
            if dpg.does_item_exist(self.window_tag):
                dpg.delete_item(self.window_tag)
            self.is_created = False
            raise # Re-raise the exception after logging
    
    def build_content(self) -> None:
        """Build the widget's main content. Must be implemented by derived classes."""
        raise NotImplementedError("Subclasses must implement build_content()")
    
    def build_menu(self) -> None:
        """Build the widget's menu bar. Optional for derived classes."""
        pass
    
    def build_status_bar(self) -> None:
        """Build the widget's status bar. Optional for derived classes."""
        pass
    
    def register_handlers(self) -> None:
        """Register event handlers. Should be implemented by derived classes."""
        pass
    
    def show(self) -> None:
        """Show the widget."""
        if not self.is_created:
            self.create()
        dpg.configure_item(self.window_tag, show=True)
    
    def hide(self) -> None:
        """Hide the widget."""
        if self.is_created:
            dpg.configure_item(self.window_tag, show=False)
    
    def update(self, data: Any) -> None:
        """Update widget with data. Should be implemented by derived classes.
        
        Args:
            data: Data to update the widget with
        """
        pass
    
    def close(self) -> None:
        """Close and destroy the widget."""
        if self.is_created:
            dpg.delete_item(self.window_tag)
            self.is_created = False 