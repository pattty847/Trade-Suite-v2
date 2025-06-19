from __future__ import annotations
import os
import logging
import shutil # Added shutil import
# Remove json import if no longer needed after full refactoring
# import json
from typing import Dict, Optional, List, Any, Type
import dearpygui.dearpygui as dpg

# Add ConfigManager import
from trade_suite.config import ConfigManager
from ...core.facade import CoreServicesFacade
from ...core.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget
from trade_suite.gui.widgets.chart_widget import ChartWidget
from trade_suite.gui.widgets.orderbook_widget import OrderbookWidget
from trade_suite.gui.widgets.price_level_widget import PriceLevelWidget
from trade_suite.gui.widgets.trading_widget import TradingWidget
from trade_suite.gui.widgets.sec_filing_viewer import SECFilingViewer

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...core.task_manager import TaskManager
    from trade_suite.gui.viewport import Viewport
    # Add type hint for SECDataFetcher if not already present or adjust import
    # from trade_suite.data.sec_data import SECDataFetcher # Example path, adjust as needed
    from trade_suite.config import ConfigManager # Add type hint for ConfigManager

class DashboardManager:
    """
    Manages dockable widgets and layout persistence using ConfigManager.
    
    This class handles:
    - Adding/removing widgets to the dashboard
    - Saving/loading widget configurations and DPG layout via ConfigManager
    - Recreating widgets based on saved configurations
    - Managing widget visibility and state
    - Providing layout management tools
    """
    
    def __init__(self, core: CoreServicesFacade, config_manager: ConfigManager):
        self.core = core
        self.config_manager = config_manager
        self.widgets = {}  # Store widget instances
        self.widget_configs = {} # Store widget configurations
        self.docking_space = None
        
        # Access components from the facade
        self.emitter = self.core.emitter
        self.task_manager = self.core.task_manager
        self.data = self.core.data
        self.sec_fetcher = self.core.sec_fetcher
        
        self.emitter.register(Signals.WIDGET_CLOSED, self.on_widget_closed)
        
        # Widget registry maps instance_id to widget instance
        self.widgets: Dict[str, DockableWidget] = {}
        
        # Use the short WIDGET_TYPE string for lookup, matching the saved config
        self.widget_classes: Dict[str, Type[DockableWidget]] = {
            "chart": ChartWidget,
            "orderbook": OrderbookWidget,
            "price_level": PriceLevelWidget,
            "trading": TradingWidget,
            "SECFilingViewer": SECFilingViewer,
        }
        
        # Track layout modification state
        self.layout_modified = False
    
    def initialize_layout(self, reset: bool = False) -> bool:
        """
        Initialize the layout system using ConfigManager.
        1. Loads widget configurations via ConfigManager.
        2. Recreates widget instances and their DPG windows.
        3. Applies the DPG layout (INI) via ConfigManager.
        
        Purpose: 
            To recreate the widgets and their DPG window layout based 
            on previously saved configuration files managed by `ConfigManager`. 
            It aims to restore the user's workspace exactly as they left it.

        Args:
            reset: If True, delete user config/layout before loading.

        Returns:
            True if any widgets were successfully recreated, False otherwise.
        """
        logging.info("Initializing layout using ConfigManager...")
        widgets_recreated = False

        # --- Reset Handling ---
        if reset:
            logging.info("Reset requested. Deleting user layout and widget configuration.")
            self.config_manager.delete_user_layout()
            self.config_manager.delete_user_widget_config()

        # --- Load Widget Configurations from ConfigManager ---
        widget_definitions = self.config_manager.load_widget_config()

        # --- Recreate Widgets ---
        if widget_definitions:
            logging.info(f"Recreating {len(widget_definitions)} widgets from loaded configuration...")
            for definition in widget_definitions:
                instance_id = definition.get("instance_id")
                # Use "widget_type" to match the key in the JSON file
                widget_type = definition.get("widget_type") 
                config = definition.get("config", {})

                if not instance_id or not widget_type:
                    logging.warning(f"Skipping invalid widget definition: {definition}")
                    continue

                if widget_type in self.widget_classes:
                    WidgetClass = self.widget_classes[widget_type]
                    try:
                        # Instantiate the widget, passing the core facade, id, and specific config
                        widget_instance = WidgetClass(
                            core=self.core,
                            instance_id=instance_id,
                            **config
                        )
                        
                        # Add widget to registry and create DPG window
                        if self.add_widget(instance_id, widget_instance, _loading_layout=True):
                            widgets_recreated = True
                            logging.debug(f"Successfully recreated widget: {instance_id} (Type: {widget_type})")
                        else:
                            logging.warning(f"Failed to add/create DPG window for widget: {instance_id}")

                    except Exception as e:
                        logging.error(f"Error recreating widget {instance_id} (Type: {widget_type}): {e}", exc_info=True)
                else:
                    logging.warning(f"Unknown widget type '{widget_type}' found in config. Skipping.")
            logging.info("Finished recreating widgets.")
        else:
            logging.info("No widget definitions found or loaded via ConfigManager. Starting potentially empty.")

        # --- Apply DPG Layout (INI) via ConfigManager ---
        user_ini_path = self.config_manager.get_user_layout_ini_path()
        factory_ini_path = self.config_manager.get_factory_layout_ini_path()
        user_ini_exists = os.path.exists(user_ini_path)

        if not user_ini_exists and os.path.exists(factory_ini_path):
            try:
                shutil.copy2(factory_ini_path, user_ini_path)
                logging.info(f"Copied factory layout INI to user path: {user_ini_path}")
                user_ini_exists = True
            except Exception as copy_e:
                logging.error(f"Error copying factory layout INI: {copy_e}")

        dpg.configure_app(docking=True, docking_space=True, init_file=user_ini_path)
        logging.info(f"DPG configured for docking. Save/init path: {user_ini_path}")

        if user_ini_exists:
            logging.info(f"Applying DPG layout from: {user_ini_path}")
            try:
                dpg.configure_app(init_file=user_ini_path)
                logging.info(f"DPG layout application triggered.")
            except Exception as e_load:
                 logging.error(f"Error applying DPG layout: {e_load}")
        
        self.layout_modified = False
        logging.info(f"Layout initialization finished. Widgets recreated: {widgets_recreated}")
        return widgets_recreated

    def add_widget(self, instance_id: str, widget_instance: DockableWidget, _loading_layout: bool = False) -> Optional[str]:
        """
        Adds a pre-initialized widget instance to the manager and creates its DPG window.
        """
        if instance_id in self.widgets:
            logging.warning(f"Widget with ID {instance_id} already exists. Focusing existing window.")
            # Optional: focus the existing widget window
            if dpg.does_item_exist(widget_instance.window_tag):
                dpg.focus_item(widget_instance.window_tag)
            return None

        self.widgets[instance_id] = widget_instance

        try:
            widget_instance.create_dpg_window()
            if not _loading_layout:
                self.layout_modified = True
            return instance_id
        except Exception as e:
            logging.error(f"Error creating DPG window for widget {instance_id}: {e}", exc_info=True)
            if instance_id in self.widgets:
                del self.widgets[instance_id]
            return None
    
    def remove_widget(self, instance_id: str) -> bool:
        """
        Remove a widget from the dashboard.
        
        Args:
            instance_id: ID of the widget to remove
            
        Returns:
            True if removed, False if not found or error
        """
        widget_instance = self.widgets.get(instance_id)
        if widget_instance:
            logging.info(f"Removing widget {instance_id}...")
            try:
                # Close the widget (unsubscribes, destroys the window)
                widget_instance.close()
                # Remove from registry AFTER successful close
                del self.widgets[instance_id]
                # Set layout modified flag
                self.layout_modified = True
                logging.info(f"Widget {instance_id} removed successfully.")
                return True
            except Exception as e:
                 logging.error(f"Error during removal of widget {instance_id}: {e}", exc_info=True)
                 # Widget might be partially removed or DPG item might linger
                 # Attempt to remove from registry anyway if error occurred during close
                 if instance_id in self.widgets:
                    del self.widgets[instance_id]
                 return False
        else:
            logging.warning(f"Attempted to remove non-existent widget ID: {instance_id}")
            return False
    
    def get_widget(self, instance_id: str) -> Optional[DockableWidget]:
        """
        Get a widget by ID.
        
        Args:
            instance_id: ID of the widget to retrieve
            
        Returns:
            The widget instance or None if not found
        """
        return self.widgets.get(instance_id)
    
    def reset_to_default(self) -> None:
        """
        Resets the dashboard to the default state.
        - Deletes user layout (INI) and widget configuration (JSON) using ConfigManager.
        - Removes all current widgets.
        - Re-initializes the layout (which will load defaults if user files are gone).
        """
        logging.info("Resetting dashboard to default state...")

        # 1. Delete user layout and widget config using ConfigManager
        try:
            self.config_manager.delete_user_layout()
            logging.info("User layout file deleted via ConfigManager.")
        except Exception as e:
            logging.error(f"Error deleting user layout file via ConfigManager: {e}", exc_info=True)

        try:
            self.config_manager.delete_user_widget_config()
            logging.info("User widget configuration file deleted via ConfigManager.")
        except Exception as e:
            logging.error(f"Error deleting user widget config file via ConfigManager: {e}", exc_info=True)

        # 2. Remove all current widgets from the dashboard
        # Iterate over a copy of keys since remove_widget modifies the dictionary
        current_widget_ids = list(self.widgets.keys())
        if not current_widget_ids:
            logging.info("No widgets currently active to remove during reset.")
        else:
            logging.info(f"Removing {len(current_widget_ids)} current widgets...")
            for widget_id in current_widget_ids:
                self.remove_widget(widget_id) # This handles DPG cleanup and registry removal
            logging.info("All current widgets removed.")
            # Verify registry is empty after removal
            if self.widgets:
                 logging.warning(f"Widget registry not empty after attempting removal: {list(self.widgets.keys())}")


        # 3. Re-initialize the layout
        # Since user files are deleted, this should ideally load the default state
        # or start fresh, depending on ConfigManager's behavior and if defaults exist.
        # The initialize_layout method now handles DPG setup.
        logging.info("Re-initializing layout after reset...")
        self.initialize_layout(reset=True) # Call without reset=True as we already deleted files
        
        # Maybe trigger a UI update or signal if needed
        self.emitter.emit(Signals.LAYOUT_RESET_COMPLETE)
        logging.info("Dashboard reset to default complete.")
    
    def save_as_default(self) -> None:
        """
        Save the current layout and widget configurations as the new default/factory state
        using the ConfigManager.

        WARNING: This overwrites the application's default settings.
        """
        logging.warning("Saving current layout as the new default. This will overwrite factory settings.")
        if not self.widgets:
            logging.warning("Save as default called, but no widgets are present. Skipping.")
            return
            
        # 1. Save DPG Layout (INI) as default using ConfigManager
        try:
            # Use ConfigManager to save DPG layout to the default path
            self.config_manager.save_dpg_layout(is_default=True)
            logging.info(f"Current DPG layout saved as default via ConfigManager.")
        except Exception as e:
            logging.error(f"Failed to save DPG layout as default via ConfigManager: {e}", exc_info=True)
            # Decide if we should continue saving widget config if layout save failed

        # 2. Prepare Widget Configuration Data (same logic as save_layout)
        widget_data = []
        for instance_id, widget in self.widgets.items():
            config = widget.get_config()
            if config is not None:
                widget_data.append({
                    "instance_id": instance_id,
                    "widget_type": widget.WIDGET_TYPE, # Use the WIDGET_TYPE attribute
                    "config": config,
                })

        # 3. Save Widget Configurations (JSON) as default using ConfigManager
        if widget_data:
            try:
                self.config_manager.save_widget_config(widget_data, is_default=True)
                logging.info(f"Widget configurations for {len(widget_data)} widgets saved as default via ConfigManager.")
            except Exception as e:
                logging.error(f"Failed to save widget configurations as default via ConfigManager: {e}", exc_info=True)
        else:
             logging.warning("No valid widget configurations obtained. Skipping default widget config save.")

        # Reset modified flag (saving as default also clears modification state)
        self.layout_modified = False
        logging.info("Save as default process finished.")
    
    def save_layout(self) -> None:
        """
        Save the current DPG layout (INI) and widget configurations (JSON)
        using the ConfigManager for user settings.
        """
        if not self.widgets:
            logging.warning("Save layout called, but no widgets are present. Skipping.")
            return

        logging.info("Saving current layout and widget configurations...")

        # --- BEGIN ADDED LOGGING ---
        logging.info("  [PRE-SAVE] Checking widget states before calling save_dpg_layout:")
        for pre_id, pre_widget in self.widgets.items():
            try:
                pre_tag = pre_widget.window_tag
                if dpg.does_item_exist(pre_tag):
                    pre_config = dpg.get_item_configuration(pre_tag)
                    pre_state = dpg.get_item_state(pre_tag)
                    logging.info(f"    Widget {pre_id} ({pre_tag}): Pos={pre_config.get('pos')}, Size=({pre_config.get('width')}, {pre_config.get('height')}), Docked={pre_state.get('docked')}")
                else:
                    logging.warning(f"    Widget {pre_id} ({pre_tag}) DPG item does not exist before INI save.")
            except Exception as log_e:
                logging.error(f"    Error logging state for {pre_id}: {log_e}")
        # --- END ADDED LOGGING ---

        # 1. Save DPG Layout (INI) using ConfigManager
        try:
            # Assuming save_dpg_layout internally calls dpg.save_init_file()
            self.config_manager.save_dpg_layout(is_default=False)
            logging.info(f"DPG layout save triggered via ConfigManager.") # Changed log msg slightly
        except Exception as e:
            logging.error(f"Failed to save DPG layout via ConfigManager: {e}", exc_info=True)
            # Decide if we should continue saving widget config if layout save failed
            # For now, we continue.

        # 2. Prepare Widget Configuration Data
        widget_data = []
        for instance_id, widget in self.widgets.items():
            config = widget.get_config()
            if config is not None:
                widget_data.append({
                    "instance_id": instance_id,
                    "widget_type": widget.WIDGET_TYPE, # Use the WIDGET_TYPE attribute
                    "config": config,
                })
        
        # 3. Save Widget Configurations (JSON) using ConfigManager
        if widget_data:
            try:
                self.config_manager.save_widget_config(widget_data, is_default=False)
                logging.info(f"Widget configurations for {len(widget_data)} widgets saved to user path via ConfigManager.")
            except Exception as e:
                logging.error(f"Failed to save widget configurations via ConfigManager: {e}", exc_info=True)
        else:
            # If there are no widgets, we should save an empty config
            # to reflect the current state.
            self.config_manager.save_widget_config([], is_default=False)

        # Reset modified flag after saving
        self.layout_modified = False
        logging.info("Layout saving process finished.")
    
    def create_layout_tools(self) -> int:
        """
        Create a window with layout management tools.
        
        Returns:
            Window ID of the layout tools
        """
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
            dpg.add_text(f"Active Widgets: {len(self.widgets)}", tag=f"{layout_tools_id}_widget_count")
            
        return layout_tools_id
    
    def _register_handlers(self) -> None:
        """
        Register event handlers for dashboard events.
        """
        # Example: Could listen for DPG resize/move events to set layout_modified = True
        # dpg.set_viewport_resize_callback(...)
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
        # TODO: This needs to be set more robustly, e.g., on widget add/remove,
        # and potentially listening to DPG item move/resize events if possible/necessary.
        return self.layout_modified 

    def on_widget_closed(self, instance_id: str) -> None:
        """
        Handle the event when a widget is closed.
        
        Args:
            instance_id: ID of the widget that was closed
        """
        logging.info(f"Widget {instance_id} closed. Removing from dashboard.")
        self.remove_widget(instance_id) 