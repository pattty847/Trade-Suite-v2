from datetime import datetime, timedelta
import dearpygui.dearpygui as dpg

def timeframe_to_seconds(timeframe_str):
    # Extracts the numerical value and unit from the timeframe string
    numeric_part = int(timeframe_str[:-1])
    unit = timeframe_str[-1]

    if unit == "m":
        return numeric_part * 60
    elif unit == "h":
        return numeric_part * 60 * 60
    elif unit == "d":
        return numeric_part * 60 * 60 * 24
    else:
        raise ValueError("Invalid timeframe format")


def calculate_since(exchange, timeframe_str, num_candles):
    # Convert the timeframe string to timedelta
    timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe_str)
    timeframe_duration = timedelta(seconds=timeframe_duration_in_seconds)

    # Calculate the total duration
    total_duration = timeframe_duration * num_candles

    # Current time
    now = datetime.utcnow()

    # Calculate the 'since' time
    since_time = now - total_duration

    # Convert 'since' time to Unix timestamp in milliseconds
    since_iso8601 = since_time.isoformat() + "Z"
    return since_iso8601

def center_window(tag):
    # Get the viewport's width and height
    viewport_width, viewport_height = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
    
    # Get the window's width and height after it has been rendered
    window_width, window_height = dpg.get_item_width(tag), dpg.get_item_height(tag)
    
    # Calculate the position to center the window
    pos_x = (viewport_width - window_width) * 0.5
    pos_y = (viewport_height - window_height) * 0.5
    
    # Set the window's position
    dpg.set_item_pos(tag, [pos_x, pos_y])
    
    
def create_loading_modal(message):
    with dpg.window(label="Loading", autosize=True, tag="loading_modal"):
        dpg.add_text(message)
        dpg.add_loading_indicator()

    # Center the modal once it's rendered
    dpg.render_dearpygui_frame()
    center_window("loading_modal")