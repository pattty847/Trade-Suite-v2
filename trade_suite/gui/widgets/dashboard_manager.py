import os
import logging
import json
from typing import Dict, Optional, List, Any, Type
import dearpygui.dearpygui as dpg

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

class DashboardManager:
    """
    Manages dockable widgets and layout persistence.
    
    This class handles:
    - Adding/removing widgets to the dashboard
    - Saving/loading widget configurations (JSON) and DPG layout (INI)
    - Recreating widgets based on saved configurations
    - Managing widget visibility and state
    - Providing layout management tools
    """
    
    def __init__(
        self,
        emitter: SignalEmitter,
        task_manager: 'TaskManager',
        sec_fetcher: 'SECDataFetcher',
        default_layout_file: str = "config/factory_layout.ini",
        user_layout_file: str = "config/user_layout.ini",
        user_widgets_file: str = "config/user_widgets.json",
    ):
        """
        Initialize the dashboard manager.
        
        Args:
            emitter: Signal emitter for event communication
            task_manager: Task manager for subscriptions
            sec_fetcher: SEC data fetcher instance
            default_layout_file: Path to the default/factory DPG layout file
            user_layout_file: Path to the user's custom DPG layout file
            user_widgets_file: Path to the user's custom widget configuration file
        """
        self.emitter = emitter
        self.task_manager = task_manager
        self.sec_fetcher = sec_fetcher
        self.default_layout = default_layout_file
        self.user_layout = user_layout_file
        self.user_widgets = user_widgets_file
        
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
        
        # Create layout directories if they don't exist
        # Ensure directory for widget file also exists
        self._ensure_layout_directories([self.default_layout, self.user_layout, self.user_widgets])
        
        # Register event handlers
        self._register_handlers()
        
        # Track layout modification state
        self.layout_modified = False
    
    def initialize_layout(self, reset: bool = False) -> None:
        """
        Initialize the layout system.
        1. Loads widget configurations from JSON (if available).
        2. Recreates widget instances and their DPG windows.
        3. Applies the DPG layout (INI) to the recreated windows.

        Args:
            reset: If True, reset to the default layout (implies deleting user files).
        """
        logging.info("Initializing layout...")
        # --- Reset Handling ---
        if reset:
            logging.info("Reset requested. Removing user layout and widget configuration files.")
            if os.path.exists(self.user_layout):
                os.remove(self.user_layout)
            if os.path.exists(self.user_widgets):
                os.remove(self.user_widgets)

        # --- Load Widget Configurations ---
        widget_data = self._load_widget_config()

        # --- Recreate Widgets ---
        if widget_data:
            logging.info(f"Recreating {len(widget_data)} widgets from loaded configuration...")
            for config in widget_data:
                instance_id = config.get("instance_id")
                widget_type = config.get("widget_type")
                widget_config = config.get("config", {})

                if not instance_id or not widget_type:
                    logging.warning(f"Skipping invalid widget data entry: {config}")
                    continue

                if widget_type in self.widget_classes:
                    WidgetClass = self.widget_classes[widget_type]
                    try:
                        # Prepare common dependencies
                        common_args = {
                            "emitter": self.emitter,
                            "task_manager": self.task_manager,
                            "instance_id": instance_id,
                        }
                        
                        # Add specific dependencies if needed
                        if WidgetClass is SECFilingViewer:
                            common_args["sec_fetcher"] = self.sec_fetcher
                        
                        # Instantiate the widget using its specific config and dependencies
                        widget_instance = WidgetClass(
                            **common_args,
                            **widget_config # Pass specific config (e.g., exchange, symbol)
                        )

                        # Use the add_widget method (which calls widget.create() internally)
                        # This keeps registry and creation logic consistent
                        self.add_widget(instance_id, widget_instance, _loading_layout=True)
                        logging.debug(f"Successfully recreated widget: {instance_id} (Type: {widget_type})")

                    except Exception as e:
                        logging.error(f"Error recreating widget {instance_id} (Type: {widget_type}): {e}", exc_info=True)
                else:
                    logging.warning(f"Unknown widget type '{widget_type}' found in config. Skipping.")
            logging.info("Finished recreating widgets.")
        else:
            logging.info("No previous widget configurations found or loaded. Starting fresh.")
            # Optionally: Create a default set of widgets here if desired

        # --- Apply DPG Layout (INI) ---
        ini_file_to_load = None
        load_default_layout = False
        if os.path.exists(self.user_layout):
            ini_file_to_load = self.user_layout
            logging.info(f"User DPG layout exists. Will apply: {ini_file_to_load}")
        elif os.path.exists(self.default_layout):
             # NOTE: We generally don't load the default INI, as it might not match
             # the widgets created by a fresh start or a potentially different user_widgets.json.
             # Default widgets should ideally be created programmatically if no user config exists.
             # If you *really* want to load default INI, uncomment below:
             # ini_file_to_load = self.default_layout
             # load_default_layout = True
             # logging.info(f"User DPG layout not found. Applying default layout: {ini_file_to_load}")
             logging.info(f"User DPG layout not found. Using default DPG window placement.")
        else:
             logging.info("No existing DPG layout file found. Using default DPG window placement.")

        # Configure DPG for docking and apply the INI file *after* windows are recreated
        # The save target should always be the user layout file.
        try:
            dpg.configure_app(
                docking=True,
                docking_space=True,
                init_file=self.user_layout, # Always set the SAVE target to user layout
                load_init_file=ini_file_to_load is not None # Load only if a user file was found
            )
            if ini_file_to_load:
                logging.info(f"Successfully applied DPG layout from {ini_file_to_load}")
            else:
                logging.info("DPG configured without loading an INI file.")
        except Exception as e:
            logging.error(f"Error configuring app or applying DPG layout from {ini_file_to_load}: {e}")

        logging.info("Layout initialization finished.")
    
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
        Reset to the default layout state.

        This now means:
        1. Clearing current widgets.
        2. Deleting user layout and widget files.
        3. Re-initializing the layout (which will start fresh or create defaults).
        4. Restarting the application might be necessary for a clean reset.
        """
        logging.warning("Resetting layout to default. This will clear current widgets and delete user layout files.")

        # 1. Clear current widgets cleanly
        # Create a list of keys to avoid modifying dict during iteration
        widget_ids_to_remove = list(self.widgets.keys())
        for widget_id in widget_ids_to_remove:
            self.remove_widget(widget_id) # Use remove_widget for proper cleanup

        # 2. Delete user files
        if os.path.exists(self.user_layout):
            os.remove(self.user_layout)
            logging.info(f"Removed user layout file: {self.user_layout}")
        if os.path.exists(self.user_widgets):
            os.remove(self.user_widgets)
            logging.info(f"Removed user widget config file: {self.user_widgets}")

        # 3. Re-initialize (will now find no user files)
        # NOTE: Depending on application structure, a full restart might be cleaner.
        # For now, re-initializing attempts to rebuild the state.
        # Clear the internal widget registry again just in case remove failed partially
        self.widgets.clear()
        self.initialize_layout() # Call initialize again, which will now start fresh

        # 4. Inform user restart might be needed
        logging.warning("Layout reset complete. A restart may be required for all changes to take effect cleanly.")
        # Consider emitting a signal that the main app can catch to trigger a restart dialog?
        # self.emitter.emit(Signals.REQUEST_RESTART, reason="Layout reset to default.")
    
    def save_as_default(self) -> None:
        """
        Save current layout and widget config as the default. (Use with caution!)
        """
        logging.warning(f"Saving current state as FACTORY DEFAULT to {self.default_layout} and a corresponding default widget file. This overwrites the application default.")
        # 1. Save DPG Layout as default
        dpg.save_init_file(self.default_layout)
        logging.info(f"Saved current DPG layout as default: {self.default_layout}")

        # 2. Save Widget Config as default (derive name)
        default_widget_file = self.default_layout.replace(".ini", "_widgets.json") # Or choose a fixed name
        widget_data = self._prepare_widget_config_data()
        try:
            with open(default_widget_file, 'w') as f:
                json.dump(widget_data, f, indent=4)
            logging.info(f"Saved current widget configurations as default: {default_widget_file}")
        except Exception as e:
            logging.error(f"Error saving default widget data to {default_widget_file}: {e}")
    
    def trigger_save_layout(self) -> None:
        """
        Schedule the layout save operation for the next frame.
        This ensures DPG has fully registered all window states before saving.
        """
        logging.info("Scheduling layout save for next frame")
        dpg.set_frame_callback(self.save_layout)

    def save_layout(self) -> None:
        """
        Save the current DPG layout (INI) and widget configurations (JSON).
        """
        # 1. Save DPG window states (position, size, docking, etc.) to INI
        try:
            dpg.save_init_file(self.user_layout)
            logging.info(f"Successfully saved DPG layout to {self.user_layout}")
        except Exception as e:
            logging.error(f"Error saving DPG layout to {self.user_layout}: {e}")
            # Decide if we should proceed with saving JSON if INI save fails
            # For now, we'll continue

        # 2. Save widget configurations to JSON
        widget_data = self._prepare_widget_config_data()
        try:
            with open(self.user_widgets, 'w') as f:
                json.dump(widget_data, f, indent=4)
            logging.info(f"Successfully saved widget configurations to {self.user_widgets}")
            self.layout_modified = False # Reset modified flag only on successful save
        except Exception as e:
            logging.error(f"Error saving widget data to {self.user_widgets}: {e}")

        logging.info(f"Layout saving finished.")
    
    def _prepare_widget_config_data(self) -> List[Dict[str, Any]]:
        """
        Helper method to gather configuration data from all active widgets.
        """
        widget_data = []
        for instance_id, widget in self.widgets.items():
            try:
                widget_config = widget.get_config()
                widget_data.append({
                    "instance_id": instance_id, # Store the key used in the registry
                    "widget_type": widget.widget_type, # Store the type string from the widget
                    "config": widget_config # Store the specific config dict
                })
            except Exception as e:
                 logging.error(f"Failed to get config for widget {instance_id} (type {widget.widget_type}): {e}", exc_info=True)
        return widget_data
    
    def _load_widget_config(self) -> List[Dict[str, Any]]:
        """
        Loads widget configurations from the user JSON file.
        """
        widget_data = []
        if os.path.exists(self.user_widgets):
            try:
                with open(self.user_widgets, 'r') as f:
                    widget_data = json.load(f)
                logging.info(f"Successfully loaded {len(widget_data)} widget configurations from {self.user_widgets}")
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON from widget config file {self.user_widgets}: {e}")
                widget_data = [] # Reset on error
            except Exception as e:
                logging.error(f"Error loading widget data from {self.user_widgets}: {e}", exc_info=True)
                widget_data = [] # Reset on error
        else:
            logging.info(f"Widget configuration file {self.user_widgets} not found.")
        return widget_data
    
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
    
    def _ensure_layout_directories(self, file_paths: List[str]) -> None:
        """
        Ensure directories for the given file paths exist.
        """
        for file_path in file_paths:
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logging.info(f"Created layout directory: {directory}")
    
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