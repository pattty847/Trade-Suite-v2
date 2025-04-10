import logging
import dearpygui.dearpygui as dpg
from typing import Dict, Any, Optional, Callable

from trade_suite.gui.signals import SignalEmitter


class DockableWidget:
    """Base class for all dockable widgets in the application.
    
    Provides common functionality for creating, managing, and docking widgets.
    Uses stable IDs to ensure widgets can be identified across sessions.
    """
    
    # Class-level registry of widget types to ensure stable IDs
    REGISTRY: Dict[str, int] = {}
    
    @classmethod
    def register_widget_type(cls, widget_name: str) -> int:
        """Register a widget type with a stable ID.
        
        Args:
            widget_name: Unique name for the widget type
            
        Returns:
            Stable UUID for the widget type
        """
        if widget_name not in cls.REGISTRY:
            cls.REGISTRY[widget_name] = dpg.generate_uuid()
        return cls.REGISTRY[widget_name]
    
    def __init__(
        self, 
        title: str, 
        widget_type: str, 
        emitter: SignalEmitter, 
        instance_id: Optional[str] = None,
        width: int = 400,
        height: int = 300,
        **kwargs
    ):
        """Initialize a dockable widget.
        
        Args:
            title: Window title
            widget_type: Type identifier for the widget
            emitter: Signal emitter for event communication
            instance_id: Optional unique ID if multiple instances of same type
            width: Initial window width
            height: Initial window height
            **kwargs: Additional window parameters
        """
        # Get the stable type ID
        self.widget_type_id = self.register_widget_type(widget_type)
        
        # Create a stable instance ID if multiple instances of same type
        self.instance_id = instance_id or "default"
        self.window_tag = f"{self.widget_type_id}_{self.instance_id}"
        
        self.title = title
        self.emitter = emitter
        self.width = width
        self.height = height
        self.kwargs = kwargs
        
        # Track if widget has been created yet
        self.is_created = False
        
        # Keep refs to child items for easier management
        self.content_tag = f"{self.window_tag}_content"
        self.menu_bar_tag = f"{self.window_tag}_menu"
        self.status_bar_tag = f"{self.window_tag}_status"
        
    def create(self, parent: Optional[int] = None) -> int:
        """Create the dockable widget window.
        
        Args:
            parent: Optional parent container
            
        Returns:
            Widget window ID
        """
        if self.is_created:
            logging.warning(f"Widget {self.title} already created, returning existing ID")
            return self.window_tag
            
        window_kwargs = {
            "label": self.title,
            "tag": self.window_tag,
            "width": self.width,
            "height": self.height
        }
        window_kwargs.update(self.kwargs)
        
        if parent:
            window_kwargs["parent"] = parent
            
        with dpg.window(**window_kwargs):
            # Create menu bar if implemented by derived class
            if hasattr(self, "build_menu") and callable(getattr(self, "build_menu")):
                with dpg.menu_bar(tag=self.menu_bar_tag):
                    self.build_menu()
            
            # Main content group
            with dpg.group(tag=self.content_tag):
                self.build_content()
            
            # Optional status bar 
            if hasattr(self, "build_status_bar") and callable(getattr(self, "build_status_bar")):
                with dpg.group(tag=self.status_bar_tag, horizontal=True):
                    self.build_status_bar()
        
        # Register event handlers
        self.register_handlers()
        self.is_created = True
        
        return self.window_tag
    
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