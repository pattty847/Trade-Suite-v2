import dearpygui.dearpygui as dpg
import os
import logging

logging.basicConfig(level=logging.INFO)

INI_FILE = "test_layout.ini"
PRIMARY_WINDOW_TAG = "primary_window"

dpg.create_context()

# --- Layout Loading ---
# Check if the layout file exists before configuring
load_init = os.path.exists(INI_FILE)
logging.info(f"Layout file '{INI_FILE}' exists: {load_init}. Configuring app...")

# Configure app: Point to the INI file, load it if it exists, AND enable docking.
# This must be called AFTER create_context() and BEFORE create_viewport().
dpg.configure_app(
    init_file=INI_FILE,      # File to load from and save to
    load_init_file=load_init, # Load it only if it exists
    docking=True,            # Enable docking
    docking_space=True       # Enable the main viewport docking space (can be used instead of explicit dock_space below, but let's be explicit)
)

# --- Callback Function ---
def save_layout_callback():
    logging.info(f"Saving layout to: {INI_FILE}")
    dpg.save_init_file(INI_FILE)
    logging.info("Layout saved.")

# --- Window Definitions ---
# Create a primary window to host the docking space
# Do this AFTER configure_app
with dpg.window(tag=PRIMARY_WINDOW_TAG):
    # Add the docking space AFTER the primary window is created
    with dpg.window(label="Main Test Window", tag="main_test_window", width=300, height=200):
        dpg.add_text("Dock me or move me.")
        dpg.add_button(label="Save Layout", callback=save_layout_callback)

    with dpg.window(label="Side Test Window", tag="side_test_window", width=250, height=150):
        dpg.add_text("Dock me somewhere else.")

# --- Viewport and Startup ---
# Create viewport AFTER windows are defined (and after configure_app)
dpg.create_viewport(title='DPG Docking Layout Test', width=800, height=600)

logging.info("Setting up Dear PyGui...")
dpg.setup_dearpygui()
dpg.show_viewport()

# Maximize the primary window containing the dockspace
# This should be done AFTER setup_dearpygui() and show_viewport()
# Ensure the primary window exists before trying to maximize
if dpg.does_item_exist(PRIMARY_WINDOW_TAG):
    dpg.maximize_viewport()
    # Setting the primary window might also be needed depending on DPG version/behavior
    # dpg.set_primary_window(PRIMARY_WINDOW_TAG, True) 
else:
    logging.warning(f"Primary window with tag '{PRIMARY_WINDOW_TAG}' not found for maximizing.")

logging.info("Starting Dear PyGui...")
dpg.start_dearpygui()

logging.info("Destroying context...")
dpg.destroy_context()
logging.info("Test script finished.") 