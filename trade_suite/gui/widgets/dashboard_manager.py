import os
import logging
import shutil # Added shutil import
# Remove json import if no longer needed after full refactoring
# import json
from typing import Dict, Optional, List, Any, Type
import dearpygui.dearpygui as dpg

# Add ConfigManager import
from trade_suite.config import ConfigManager
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.widgets.base_widget import DockableWidget
from trade_suite.gui.widgets.chart_widget import ChartWidget
from trade_suite.gui.widgets.orderbook_widget import OrderbookWidget
from trade_suite.gui.widgets.price_level_widget import PriceLevelWidget
from trade_suite.gui.widgets.trading_widget import TradingWidget
from trade_suite.gui.widgets.sec_filing_viewer import SECFilingViewer, SECDataFetcher

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from trade_suite.gui.task_manager import TaskManager
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
    
    def __init__(
        self,
        emitter: SignalEmitter,
        task_manager: 'TaskManager',
        sec_fetcher: 'SECDataFetcher', # Keep if needed by SECFilingViewer instantiation
        config_manager: 'ConfigManager' # Add config_manager parameter
        # Remove default_layout_file, user_layout_file, user_widgets_file parameters
    ):
        """
        Initialize the dashboard manager.
        
        Args:
            emitter: Signal emitter for event communication
            task_manager: Task manager for subscriptions
            sec_fetcher: SEC data fetcher instance (passed to relevant widgets)
            config_manager: The application's configuration manager instance.
        """
        self.emitter = emitter
        self.task_manager = task_manager
        self.sec_fetcher = sec_fetcher # Keep temporarily, might pass to common_args
        self.config_manager = config_manager # Store config_manager
        
        # Remove self.default_layout, self.user_layout, self.user_widgets attributes
        
        # Widget registry maps instance_id to widget instance
        self.widgets: Dict[str, DockableWidget] = {}
        
        # Map widget type names (strings) to their actual classes
        # This is crucial for recreating widgets from the JSON config
        self.widget_classes: Dict[str, Type[DockableWidget]] = {
            "chart": ChartWidget,
            "orderbook": OrderbookWidget,
            "price_level": PriceLevelWidget,
            "trading": TradingWidget,
            "SECFilingViewer": SECFilingViewer,
            # Add other widget types here
        }
        
        # Remove call to self._ensure_layout_directories()
        
        # Register event handlers
        self._register_handlers()
        
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
            # Use ConfigManager to delete user files
            self.config_manager.delete_user_layout()
            self.config_manager.delete_user_widget_config()
            # Note: Existing widgets might need explicit removal if reset is called mid-session
            # This logic assumes initialize_layout is called early

        # --- Load Widget Configurations from ConfigManager ---
        widget_definitions = self.config_manager.load_widget_config()

        # --- Recreate Widgets ---
        if widget_definitions:
            logging.info(f"Recreating {len(widget_definitions)} widgets from loaded configuration...")
            for definition in widget_definitions:
                instance_id = definition.get("instance_id")
                widget_type = definition.get("widget_type")
                config = definition.get("config", {})

                if not instance_id or not widget_type:
                    logging.warning(f"Skipping invalid widget definition: {definition}")
                    continue

                if widget_type in self.widget_classes:
                    # Get the widget class from the registry so owe can create an instance during runtime
                    WidgetClass = self.widget_classes[widget_type]
                    try:
                        # Prepare common dependencies
                        common_args = {
                            "emitter": self.emitter,
                            "task_manager": self.task_manager,
                            "instance_id": instance_id,
                        }

                        # Add specific dependencies ONLY if required by the widget type
                        if WidgetClass is SECFilingViewer:
                            # Ensure sec_fetcher is available in self
                            # This is passed to the SECFilingViewer constructor
                            if hasattr(self, 'sec_fetcher'):
                                common_args["sec_fetcher"] = self.sec_fetcher
                            else:
                                logging.error(f"SECDataFetcher not available for SECFilingViewer {instance_id}. Skipping.")
                                continue

                        # Instantiate the widget
                        widget_instance = WidgetClass(
                            **common_args, 
                            **config # Pass specific config (e.g., exchange, symbol)
                        )
                        
                        # Add widget to registry and create DPG window
                        # Pass _loading_layout=True to prevent marking layout as modified prematurely
                        widget_window_tag = self.add_widget(instance_id, widget_instance, _loading_layout=True)
                        if widget_window_tag:
                           # --- BEGIN ADDED LOGGING ---
                           try:
                               if dpg.does_item_exist(widget_window_tag):
                                   w_config = dpg.get_item_configuration(widget_window_tag)
                                   w_state = dpg.get_item_state(widget_window_tag)
                                   logging.info(f"  [POST-CREATE] Widget {instance_id} ({widget_window_tag}): Pos={w_config.get('pos')}, Size=({w_config.get('width')}, {w_config.get('height')}), Docked={w_state.get('docked')}")
                               else:
                                   logging.warning(f"  [POST-CREATE] Widget {instance_id} ({widget_window_tag}) DPG item does not exist after creation attempt.")
                           except Exception as log_e:
                               logging.error(f"  [POST-CREATE] Error logging state for {instance_id}: {log_e}")
                           # --- END ADDED LOGGING ---
                           widgets_recreated = True # Mark as True if at least one widget is added
                           logging.debug(f"Successfully recreated widget: {instance_id} (Type: {widget_type})")
                        else:
                            logging.warning(f"Failed to add/create widget: {instance_id} (Type: {widget_type})")

                    except Exception as e:
                        logging.error(f"Error recreating widget {instance_id} (Type: {widget_type}): {e}", exc_info=True)
                else:
                    logging.warning(f"Unknown widget type '{widget_type}' found in config. Skipping.")
            logging.info("Finished recreating widgets.")
        else:
            logging.info("No widget definitions found or loaded via ConfigManager. Starting potentially empty.")
            # If no widgets are loaded, the layout will be empty unless default widgets are added elsewhere

        # --- Apply DPG Layout (INI) via ConfigManager ---
        # Get the paths for user and factory layouts
        user_ini_path = self.config_manager.get_user_layout_ini_path()
        factory_ini_path = self.config_manager.get_factory_layout_ini_path()

        # Determine if the user layout INI file exists
        user_ini_exists = os.path.exists(user_ini_path)

        # --- Default Layout Handling ---
        if not user_ini_exists:
            logging.info(f"User layout INI not found at {user_ini_path}. Checking for factory default.")
            if os.path.exists(factory_ini_path):
                try:
                    shutil.copy2(factory_ini_path, user_ini_path) # copy2 preserves metadata
                    logging.info(f"Copied factory layout INI ({factory_ini_path}) to user path ({user_ini_path}).")
                    user_ini_exists = True # Mark as existing now
                except Exception as copy_e:
                    logging.error(f"Error copying factory layout INI {factory_ini_path} to {user_ini_path}: {copy_e}")
                    # Proceed without the user INI if copy fails
            else:
                logging.warning(f"Factory layout INI also not found at {factory_ini_path}. DPG will use default placement.")
        # --- End Default Layout Handling ---

        # Configure basic app settings and *save* path immediately
        # This sets up docking and tells DPG where to save the layout on exit (always the user path).
        # It does NOT load the layout yet.
        try:
            dpg.configure_app(
                docking=True,
                docking_space=True,
                init_file=user_ini_path # DPG saves here on exit, and potentially loads from here
            )
            logging.info(f"DPG configured for docking. Save/init path: {user_ini_path}")
        except Exception as e:
            logging.error(f"Error configuring DPG docking/save path: {e}")
            # If this fails, loading probably won't work either, but we proceed cautiously

        # --- Explicitly Apply/Load the DPG Layout (INI) ---
        # This should happen AFTER all windows from the config have been recreated.
        # If the user_ini exists (either originally or copied from factory), apply it.
        if user_ini_exists:
            logging.info(f"Applying DPG layout from: {user_ini_path}")
            try:
                # Re-apply configuration, focusing on the init_file to trigger layout load
                # We keep docking settings as they were set just before.
                # The key is calling this *after* windows are created.
                dpg.configure_app(init_file=user_ini_path)
                logging.info(f"DPG layout application triggered using init_file: {user_ini_path}")
                # --- BEGIN ADDED LOGGING ---
                logging.info("  [POST-INI APPLY] Checking widget states:")
                for post_id, post_widget in self.widgets.items():
                    try:
                        post_tag = post_widget.window_tag # Assuming widget has window_tag attribute
                        if dpg.does_item_exist(post_tag):
                            post_config = dpg.get_item_configuration(post_tag)
                            post_state = dpg.get_item_state(post_tag)
                            logging.info(f"    Widget {post_id} ({post_tag}): Pos={post_config.get('pos')}, Size=({post_config.get('width')}, {post_config.get('height')}), Docked={post_state.get('docked')}")
                        else:
                            logging.warning(f"    Widget {post_id} ({post_tag}) DPG item does not exist after INI apply.")
                    except Exception as log_e:
                         logging.error(f"    Error logging state for {post_id}: {log_e}")
                # --- END ADDED LOGGING ---
            except Exception as e_load:
                 logging.error(f"Error applying DPG layout via configure_app(init_file=...): {e_load}")
        else:
            # This case should now only happen if neither user nor factory INI existed, or copy failed
            logging.info(f"DPG layout INI not found or failed to copy. DPG will use default window placement.")
            # Even if not loading, configure_app was already called to set the save path.

        # Reset layout modified flag after initialization
        self.layout_modified = False
        logging.info(f"Layout initialization finished. Widgets recreated: {widgets_recreated}")
        return widgets_recreated # Return status
    
    def add_widget(self, widget_id: str, widget: DockableWidget, _loading_layout: bool = False) -> Optional[str]:
        """
        Add a widget to the dashboard.
        
        Args:
            widget_id: Unique identifier for the widget (should match widget.instance_id)
            widget: The widget instance
            _loading_layout: Internal flag to prevent modifying layout state during init
            
        Returns:
            The widget's window tag (string) or None if creation failed
        """
        if widget_id in self.widgets:
            logging.warning(f"Widget with ID {widget_id} already exists in registry. Overwriting.")
            # Decide if overwrite is okay, or if we should maybe focus existing?
            # For now, we replace. Ensure old one is cleaned up if necessary.
            # self.remove_widget(widget_id) # Careful with potential recursion/callbacks

        # Store in registry BEFORE creating DPG item
        self.widgets[widget_id] = widget

        try:
            # Create the widget window (returns the window tag)
            window_tag = widget.create()

            if not window_tag: # Check if creation returned a valid tag
                 logging.error(f"Widget {widget_id} failed to create DPG window. Removing from registry.")
                 del self.widgets[widget_id]
                 return None

            # Set layout modified flag only if not loading
            if not _loading_layout:
                self.layout_modified = True
                logging.debug(f"Widget added: {widget_id}. Layout marked as modified.")

            return window_tag
        except Exception as e:
            logging.error(f"Error creating widget {widget_id}: {e}", exc_info=True)
            # Clean up registry if creation failed
            if widget_id in self.widgets:
                del self.widgets[widget_id]
            return None
    
    def remove_widget(self, widget_id: str) -> bool:
        """
        Remove a widget from the dashboard.
        
        Args:
            widget_id: ID of the widget to remove
            
        Returns:
            True if removed, False if not found or error
        """
        widget_instance = self.widgets.get(widget_id)
        if widget_instance:
            logging.info(f"Removing widget {widget_id}...")
            try:
                # Close the widget (unsubscribes, destroys the window)
                widget_instance.close()
                # Remove from registry AFTER successful close
                del self.widgets[widget_id]
                # Set layout modified flag
                self.layout_modified = True
                logging.info(f"Widget {widget_id} removed successfully.")
                return True
            except Exception as e:
                 logging.error(f"Error during removal of widget {widget_id}: {e}", exc_info=True)
                 # Widget might be partially removed or DPG item might linger
                 # Attempt to remove from registry anyway if error occurred during close
                 if widget_id in self.widgets:
                    del self.widgets[widget_id]
                 return False
        else:
            logging.warning(f"Attempted to remove non-existent widget ID: {widget_id}")
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
        self.initialize_layout(reset=False) # Call without reset=True as we already deleted files
        
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
            try:
                config = widget.get_config()
                if config is None:
                     logging.warning(f"Widget {instance_id} ({widget.widget_type}) returned None for get_config(). Skipping for default save.")
                     continue
                widget_data.append({
                    "instance_id": instance_id,
                    "widget_type": widget.widget_type,
                    "config": config,
                })
            except Exception as e:
                logging.error(f"Error getting config for widget {instance_id} ({widget.widget_type}) during save_as_default: {e}", exc_info=True)

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
            try:
                config = widget.get_config() # Use the widget's own method
                if config is None:
                     logging.warning(f"Widget {instance_id} ({widget.widget_type}) returned None for get_config(). Skipping.")
                     continue # Skip widgets that don't provide config
                widget_data.append({
                    "instance_id": instance_id,
                    "widget_type": widget.widget_type,
                    "config": config,
                })
            except Exception as e:
                logging.error(f"Error getting config for widget {instance_id} ({widget.widget_type}): {e}", exc_info=True)
                # Optionally skip this widget or handle error differently

        # 3. Save Widget Configurations (JSON) using ConfigManager
        if widget_data:
            try:
                self.config_manager.save_widget_config(widget_data, is_default=False)
                logging.info(f"Widget configurations for {len(widget_data)} widgets saved to user path via ConfigManager.")
            except Exception as e:
                logging.error(f"Failed to save widget configurations via ConfigManager: {e}", exc_info=True)
        else:
            logging.warning("No valid widget configurations obtained. Skipping widget config save.")

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