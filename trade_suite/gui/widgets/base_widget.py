import logging
import dearpygui.dearpygui as dpg
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod

from ...core.facade import CoreServicesFacade
from ...core.signals import Signals


class DockableWidget(ABC):
    """Base class for all dockable widgets in the application.
    
    Provides common functionality for creating, managing, and docking widgets.
    Uses stable IDs to ensure widgets can be identified across sessions.
    """
    
    WIDGET_TYPE: str = "base"
    WIDGET_TITLE: str = "Base Widget"

    def __init__(
        self,
        core: CoreServicesFacade,
        instance_id: str,
        width: int = 400,
        height: int = 300,
        **kwargs
    ):
        """Initialize a dockable widget.
        
        Args:
            core: The core services facade.
            instance_id: Unique ID for this specific instance.
            width: Initial window width.
            height: Initial window height.
            **kwargs: Additional configuration for the widget (e.g., symbol, exchange).
        """
        self.core = core
        self.instance_id = instance_id
        self.task_manager = core.task_manager
        self.emitter = core.emitter
        
        self.window_tag = f"widget.{self.WIDGET_TYPE}.{self.instance_id}"
        
        logging.debug(f"Creating widget: title='{self.WIDGET_TITLE}', type='{self.WIDGET_TYPE}', instance='{self.instance_id}', generated_tag='{self.window_tag}'")

        self.width = width
        self.height = height
        self.kwargs = kwargs
        
        self.is_created = False
        
        self.content_tag = f"{self.window_tag}_content"
        self.menu_bar_tag = f"{self.window_tag}_menu"
        self.status_bar_tag = f"{self.window_tag}_status"
        
    def create_dpg_window(self, parent: Optional[int] = None) -> str:
        """Create the dockable widget window."""
        if self.is_created:
            if dpg.does_item_exist(self.window_tag):
                logging.warning(f"Widget {self.WIDGET_TITLE} (tag: {self.window_tag}) already created, focusing it.")
                dpg.focus_item(self.window_tag)
                return self.window_tag
            else:
                logging.warning(f"Widget {self.WIDGET_TITLE} (tag: {self.window_tag}) marked as created but DPG item doesn't exist. Recreating.")
                self.is_created = False
        
        window_kwargs = {
            "label": f"{self.WIDGET_TITLE}##{self.instance_id}",
            "tag": self.window_tag,
            "width": self.width,
            "height": self.height,
            "on_close": self._on_window_close
        }
        window_kwargs.update(self.kwargs)
        
        if parent:
            window_kwargs["parent"] = parent
            
        if dpg.does_item_exist(self.window_tag):
            logging.error(f"FATAL: Attempting to create window with duplicate tag: {self.window_tag}.")
            return self.window_tag

        try:
            with dpg.window(**window_kwargs):
                if hasattr(self, "build_menu") and callable(getattr(self, "build_menu")):
                    self.menu_bar_tag = f"{self.window_tag}_menu"
                    with dpg.menu_bar(tag=self.menu_bar_tag):
                        self.build_menu()
                
                self.content_tag = f"{self.window_tag}_content"
                with dpg.group(tag=self.content_tag):
                    self.build_content()
                
                if hasattr(self, "build_status_bar") and callable(getattr(self, "build_status_bar")):
                    self.status_bar_tag = f"{self.window_tag}_status"
                    with dpg.group(tag=self.status_bar_tag, horizontal=True):
                        self.build_status_bar()
            
            self.register_handlers()
            self.is_created = True
            logging.debug(f"Successfully created window with tag: {self.window_tag}")
            
            try:
                requirements = self.get_requirements()
                self.task_manager.subscribe(self, requirements)
                logging.info(f"Widget {self.window_tag} subscribed with requirements: {requirements}")
            except Exception as e:
                logging.error(f"Error subscribing widget {self.window_tag}: {e}", exc_info=True)
            
            return self.window_tag

        except Exception as e:
            logging.error(f"Error creating window with tag {self.window_tag}: {e}", exc_info=True)
            if dpg.does_item_exist(self.window_tag):
                dpg.delete_item(self.window_tag)
            self.is_created = False
            raise
    
    def build_content(self) -> None:
        """Build the widget's main content. Must be implemented by derived classes."""
        raise NotImplementedError("Subclasses must implement build_content()")
    
    @abstractmethod
    def get_requirements(self) -> Dict[str, Any]:
        """Define the data requirements for this widget. Must be implemented by derived classes."""
        raise NotImplementedError("Subclasses must implement get_requirements()")

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Returns a dictionary containing the necessary configuration
        to recreate this specific widget instance.
        """
        raise NotImplementedError("Subclasses must implement get_config()")
    
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
            self.create_dpg_window()
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
    
    def _on_window_close(self) -> None:
        """Callback function executed when the widget window is closed via DPG."""
        logging.info(f"Window close detected for widget {self.window_tag}. Cleaning up...")
        try:
            self.task_manager.unsubscribe(self)
            logging.info(f"Widget {self.window_tag} unsubscribed.")
        except Exception as e:
            logging.error(f"Error unsubscribing widget {self.window_tag}: {e}", exc_info=True)
            
        self.is_created = False
        self.emitter.emit(Signals.WIDGET_CLOSED, widget_id=self.instance_id)

    def close(self) -> None:
        """Close and destroy the widget."""
        # This method might be called programmatically (e.g., by DashboardManager.remove_widget)
        # The _on_window_close callback handles user-initiated closes.
        # Both should result in unsubscription. Call unsubscribe here too for robustness,
        # TaskManager.unsubscribe should be idempotent.
        if self.is_created:
            logging.info(f"Programmatic close called for widget {self.window_tag}. Unsubscribing and deleting item.")
            try:
                self.task_manager.unsubscribe(self)
                logging.info(f"Widget {self.window_tag} unsubscribed (programmatic close).")
            except Exception as e:
                logging.error(f"Error unsubscribing widget {self.window_tag} (programmatic close): {e}", exc_info=True)
                
            if dpg.does_item_exist(self.window_tag):
                dpg.delete_item(self.window_tag)
            self.is_created = False
        else:
            logging.debug(f"Programmatic close called for widget {self.window_tag}, but it was not marked as created.") 