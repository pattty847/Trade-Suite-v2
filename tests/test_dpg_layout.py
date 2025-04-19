import dearpygui.dearpygui as dpg
import os
import logging
import json

logging.basicConfig(level=logging.INFO)

INI_FILE = "test_layout.ini"
DYNAMIC_WINDOWS_FILE = "dynamic_windows.json"
PRIMARY_WINDOW_TAG = "primary_window"
DYNAMIC_WINDOW_PREFIX = "dynamic_window_"

dpg.create_context()

# --- Track Dynamic Windows ---
# Load existing dynamic windows if the file exists
dynamic_window_count = 0
dynamic_window_tags = []

if os.path.exists(DYNAMIC_WINDOWS_FILE):
    try:
        with open(DYNAMIC_WINDOWS_FILE, 'r') as f:
            dynamic_window_tags = json.load(f)
            dynamic_window_count = len(dynamic_window_tags)
            logging.info(f"Loaded {dynamic_window_count} dynamic windows from {DYNAMIC_WINDOWS_FILE}")
    except Exception as e:
        logging.error(f"Error loading dynamic windows: {e}")
        dynamic_window_tags = []

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

# --- Callback Functions ---
def save_layout_callback():
    logging.info(f"Saving layout to: {INI_FILE}")
    dpg.save_init_file(INI_FILE)
    
    # Save dynamic window tags
    with open(DYNAMIC_WINDOWS_FILE, 'w') as f:
        json.dump(dynamic_window_tags, f)
        
    logging.info(f"Layout saved. Dynamic windows ({len(dynamic_window_tags)}) saved to {DYNAMIC_WINDOWS_FILE}")

def create_dynamic_window():
    global dynamic_window_count
    dynamic_window_count += 1
    
    # Create a stable, predictable tag
    window_tag = f"{DYNAMIC_WINDOW_PREFIX}{dynamic_window_count}"
    
    # Add to our list of tags if not already there
    if window_tag not in dynamic_window_tags:
        dynamic_window_tags.append(window_tag)
    
    # Create the window
    with dpg.window(label=f"Dynamic Window {dynamic_window_count}", tag=window_tag, width=200, height=150):
        dpg.add_text(f"I am dynamic window #{dynamic_window_count}")
        dpg.add_button(label="Save Layout", callback=save_layout_callback)
    
    logging.info(f"Created dynamic window with tag: {window_tag}")

# --- Create Dynamic Windows from Previous Session ---
for tag in dynamic_window_tags:
    with dpg.window(label=tag.replace(DYNAMIC_WINDOW_PREFIX, "Dynamic Window "), tag=tag, width=200, height=150):
        window_num = tag.replace(DYNAMIC_WINDOW_PREFIX, "")
        dpg.add_text(f"I am dynamic window #{window_num}")
        dpg.add_button(label="Save Layout", callback=save_layout_callback)
    logging.info(f"Recreated dynamic window: {tag}")

# --- Window Definitions ---
# Create a primary window to host the docking space
# Do this AFTER configure_app
with dpg.window(tag=PRIMARY_WINDOW_TAG):
    # Add the docking space AFTER the primary window is created
    with dpg.window(label="Main Test Window", tag="main_test_window", width=300, height=200):
        dpg.add_text("Dock me or move me.")
        dpg.add_button(label="Save Layout", callback=save_layout_callback)
        dpg.add_button(label="Create New Window", callback=create_dynamic_window)

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