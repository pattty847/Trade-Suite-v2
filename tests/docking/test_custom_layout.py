import dearpygui.dearpygui as dpg
import os
import json
import uuid
import logging # Added for better logging

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

INI_PATH = "test_layout.ini"
WIDGET_DATA_PATH = "test_widgets.json"

# --- Widget Classes ---
class SimpleWidget:
    """A basic widget example that can be dynamically created and managed."""
    def __init__(self, instance_id: str, config: dict, layout_manager):
        self.instance_id = instance_id
        self.config = config
        self.layout_manager = layout_manager
        self.window_tag = f"widget_win_{self.instance_id}"

    def create(self):
        """Creates the DPG window for this widget."""
        if dpg.does_item_exist(self.window_tag):
            logging.warning(f"Window {self.window_tag} already exists. Skipping creation.")
            return
        logging.info(f"Creating DPG window for widget {self.instance_id} with tag {self.window_tag}")
        with dpg.window(
            label=self.config.get("label", f"Widget {self.instance_id[:8]}"),
            tag=self.window_tag,
            on_close=self._on_window_close,
            width=200, # Default size
            height=150 # Default size
        ):
            dpg.add_text(f"ID: {self.instance_id}")
            dpg.add_text(f"Label: {self.config.get('label', 'N/A')}")
            # Add more content based on config if needed
            dpg.add_input_text(label="Config Value", default_value=self.config.get("value", ""), callback=self._on_value_change)

    def get_config(self) -> dict:
        """Returns the current configuration of the widget."""
        return self.config

    def _on_window_close(self, sender, app_data, user_data):
        """Callback when the DPG window is closed."""
        logging.info(f"DPG window closed for widget: {self.instance_id} (Tag: {self.window_tag})")
        self.layout_manager.remove_widget(self.instance_id)
        # Note: DPG handles deleting the window item itself when 'on_close' is triggered
        # and the window is actually closed by the user. We just need to handle our internal state.

    def _on_value_change(self, sender, app_data, user_data):
        """Callback to update the config when the input text changes."""
        self.config["value"] = app_data
        logging.debug(f"Widget {self.instance_id} value updated: {app_data}") # Use debug level for frequent updates

# --- Layout Manager ---
class LayoutManager:
    """Manages the lifecycle and persistence of dynamic widgets."""
    def __init__(self):
        self.active_widgets = {}
        # Map widget type names (strings) to their actual classes
        self.widget_classes = {
            "SimpleWidget": SimpleWidget
            # Add other widget types here if needed
        }
        self._next_widget_index = 0 # Simple counter for default labels

    def add_widget(self, instance_id: str = None, widget_type: str = "SimpleWidget", config: dict = None):
        """Creates, registers, and displays a new widget instance."""
        if widget_type not in self.widget_classes:
            logging.error(f"Error: Unknown widget type '{widget_type}'")
            return None

        if instance_id is None:
            instance_id = uuid.uuid4().hex

        if instance_id in self.active_widgets:
            logging.warning(f"Widget with ID {instance_id} already exists.")
            # Optionally, could focus the existing window here
            return self.active_widgets[instance_id]

        if config is None:
            self._next_widget_index += 1
            config = {"label": f"Widget {self._next_widget_index}", "value": f"Default {self._next_widget_index}"}

        WidgetClass = self.widget_classes[widget_type]
        widget_instance = WidgetClass(instance_id, config, self)

        logging.info(f"Adding widget: {instance_id} (Type: {widget_type}, Config: {config})")
        self.active_widgets[instance_id] = widget_instance
        widget_instance.create() # Create the DPG window
        return widget_instance

    def remove_widget(self, instance_id: str):
        """Removes a widget instance from active tracking."""
        if instance_id in self.active_widgets:
            logging.info(f"Removing widget {instance_id} from layout manager tracking.")
            del self.active_widgets[instance_id]
            # Note: The corresponding dpg.window should be deleted via its on_close callback
            # or explicitly if removed programmatically without closing the window.
        else:
            logging.warning(f"Attempted to remove non-existent widget ID: {instance_id}")

    def save_layout(self, ini_path: str, json_path: str):
        """Saves the DPG window layout (.ini) and widget configurations (.json)."""
        logging.info(f"Starting layout save to {ini_path} and {json_path}")

        # Log current state *before* saving INI
        logging.info("Current DPG state of active widgets before saving:")
        if not self.active_widgets:
            logging.info("  -> No active widgets to log state for.")
        for instance_id, widget in self.active_widgets.items():
            tag = widget.window_tag
            if dpg.does_item_exist(tag):
                config = dpg.get_item_configuration(tag)
                state = dpg.get_item_state(tag)
                logging.info(f"  Widget ID: {instance_id} | Tag: {tag}")
                logging.info(f"    Config: Pos={config.get('pos')}, Size={config.get('width')},{config.get('height')}, Label='{config.get('label')}'")
                logging.info(f"    State: Visible={state.get('visible')}, Docked={state.get('docked')}") # Added docked state
            else:
                logging.warning(f"  Widget ID: {instance_id} | Tag: {tag} does not exist in DPG at save time.")

        # 1. Save DPG window states (position, size, docking, etc.)
        try:
            dpg.save_init_file(ini_path)
            logging.info(f"  -> Successfully saved DPG state to {ini_path}")
        except Exception as e:
            logging.error(f"  -> Error saving DPG state to {ini_path}: {e}")
            # Decide if we should proceed with saving JSON if INI save fails
            # For now, we'll continue

        # 2. Prepare widget data for saving
        widget_data = []
        for instance_id, widget in self.active_widgets.items():
            widget_data.append({
                "instance_id": instance_id,
                "widget_type": type(widget).__name__,
                "config": widget.get_config() # Get potentially updated config
            })

        # 3. Save widget data to JSON
        try:
            with open(json_path, 'w') as f:
                json.dump(widget_data, f, indent=4)
            logging.info(f"  -> Successfully saved widget configurations to {json_path}")
        except Exception as e:
            logging.error(f"Error saving widget data to {json_path}: {e}")

        logging.info(f"Layout saving finished.")

    def load_layout(self, ini_path: str, json_path: str):
        """Loads widget configurations (.json) and applies DPG layout (.ini)."""
        logging.info(f"Starting layout load from {ini_path} and {json_path}")
        widget_data = []
        # 1. Load widget configurations from JSON
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    widget_data = json.load(f)
                logging.info(f"  -> Successfully loaded {len(widget_data)} widget configurations from {json_path}")
            except Exception as e:
                logging.error(f"Error loading widget data from {json_path}: {e}")
                widget_data = [] # Reset on error
        else:
            logging.info(f"  -> Widget configuration file {json_path} not found. Starting fresh.")

        # 2. Recreate widget instances and their DPG windows *before* loading INI
        highest_index = 0
        recreated_widget_tags = []
        if widget_data: # Check if list is not empty
            logging.info(f"  -> Recreating {len(widget_data)} widgets based on loaded data...")
            for data in widget_data:
                instance_id = data.get("instance_id")
                widget_type = data.get("widget_type")
                config = data.get("config", {})

                if not instance_id or not widget_type:
                    logging.warning(f"Warning: Skipping invalid widget data entry: {data}")
                    continue

                # Use a local variable to avoid modifying the method signature for logging
                _widget_instance = self.add_widget(instance_id, widget_type, config)
                if _widget_instance:
                    recreated_widget_tags.append(_widget_instance.window_tag)
                    # Try to find the highest index from loaded labels for the counter
                    try:
                        label_parts = config.get("label", "").split()
                        if len(label_parts) > 1 and label_parts[0] == "Widget":
                            index = int(label_parts[-1])
                            highest_index = max(highest_index, index)
                    except ValueError:
                        pass # Ignore labels not matching the pattern
            self._next_widget_index = highest_index # Update counter
            logging.info(f"  -> Finished recreating widgets. Next index: {self._next_widget_index + 1}")
        else:
            logging.info("  -> No previous widget data found or loaded.")
            self._next_widget_index = 0

        # 2.5 Log state *after* creation, *before* applying INI
        logging.info(f"State of {len(recreated_widget_tags)} recreated widgets BEFORE applying INI:")
        if not recreated_widget_tags:
             logging.info("  -> No widgets were recreated.")
        for tag in recreated_widget_tags:
            if dpg.does_item_exist(tag):
                config = dpg.get_item_configuration(tag)
                state = dpg.get_item_state(tag)
                logging.info(f"  Tag: {tag}")
                logging.info(f"    Config: Pos={config.get('pos')}, Size={config.get('width')},{config.get('height')}")
                logging.info(f"    State: Visible={state.get('visible')}, Docked={state.get('docked')}")
            else:
                logging.warning(f"  Tag: {tag} (expected to exist) does not exist BEFORE applying INI.")

        # 3. Apply DPG layout from INI *after* windows are created
        ini_applied = False
        if os.path.exists(ini_path):
            logging.info(f"  -> Applying DPG layout from {ini_path}...")
            try:
                # Use configure_app which is safer than load_init_file during runtime setup
                dpg.configure_app(docking=True, docking_space=True, init_file=ini_path)
                logging.info(f"  -> Successfully applied DPG layout from {ini_path}")
                ini_applied = True
            except Exception as e:
                 logging.error(f"  -> Error applying DPG layout from {ini_path}: {e}")
        else:
            logging.info(f"  -> DPG layout file {ini_path} not found. Using default layout.")

        # 3.5 Log state *after* applying INI
        logging.info(f"State of {len(recreated_widget_tags)} recreated widgets AFTER applying INI (Applied={ini_applied}):")
        if not recreated_widget_tags:
             logging.info("  -> No widgets were recreated to check state.")
        for tag in recreated_widget_tags:
            if dpg.does_item_exist(tag):
                config = dpg.get_item_configuration(tag)
                state = dpg.get_item_state(tag)
                logging.info(f"  Tag: {tag}")
                logging.info(f"    Config: Pos={config.get('pos')}, Size={config.get('width')},{config.get('height')}")
                logging.info(f"    State: Visible={state.get('visible')}, Docked={state.get('docked')}")
            else:
                # This might happen if the INI file somehow removes a window, though unlikely here
                logging.warning(f"  Tag: {tag} does not exist AFTER applying INI.")


        logging.info("Layout loading finished.")


# --- Main Application Logic ---
def main():
    dpg.create_context()
    logging.info("DPG Context Created.")

    layout_manager = LayoutManager()

    # --- Callbacks ---
    def _add_new_widget_callback():
        logging.info("'Add SimpleWidget' button clicked")
        layout_manager.add_widget()

    def _save_layout_callback():
        logging.info("'Save Layout' button clicked")
        layout_manager.save_layout(INI_PATH, WIDGET_DATA_PATH)

    # --- Control Window (Create BEFORE load so it exists if INI references it) ---
    # Note: We create it here, but its state (pos/size) will be potentially
    # overridden by load_layout if it was saved in the INI.
    logging.info("Creating control window.")
    with dpg.window(label="Controls", tag="control_window", width=300, height=100):
        # Start hidden, rely on INI or default DPG placement to show it
        dpg.add_button(label="Add SimpleWidget", callback=_add_new_widget_callback)
        dpg.add_button(label="Save Layout", callback=_save_layout_callback)

    # --- DPG Setup (Viewport and main setup) ---
    logging.info("Setting up DPG viewport...")
    dpg.create_viewport(title='Dynamic Layout Test', width=1280, height=720)
    # setup_dearpygui must be called after creating the viewport and before showing it.
    dpg.setup_dearpygui()
    logging.info("DPG setup complete.")

    # --- Initial Layout Load ---
    # Load layout *after* setup_dearpygui but *before* showing the viewport
    # or starting the render loop. This seems like a more robust point.
    layout_manager.load_layout(INI_PATH, WIDGET_DATA_PATH)

    # Now show the viewport *after* the INI might have configured it (including visibility)
    dpg.show_viewport()
    logging.info("Viewport shown.")


    logging.info("Starting Dear PyGui render loop...")
    # Use the manual render loop as requested
    while dpg.is_dearpygui_running():
        # Insert per-frame logic here if needed
        dpg.render_dearpygui_frame()

    logging.info("Dear PyGui render loop stopped. Cleaning up...")
    dpg.destroy_context()
    logging.info("DPG Context Destroyed. Cleanup complete.")


if __name__ == "__main__":
    main() 