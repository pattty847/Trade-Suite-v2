from datetime import datetime, timedelta
import threading
import dearpygui.dearpygui as dpg


def timeframe_to_seconds(timeframe_str):
    """
    The timeframe_to_seconds function takes a timeframe string and converts it to seconds.
    
    Example: 
        '1m' == 60
        '5m' == 60 * 5
    
    :param timeframe_str: Determine the time frame of the data
    :return: The number of seconds in the timeframe
    :doc-author: Trelent
    """
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
    """
    The calculate_since function takes the following arguments:
        exchange (ccxt.Exchange): The ccxt Exchange object to use for fetching data.
        timeframe_str (str): A string representing the time frame of each candle, e.g., '5m' or '15m'.
        num_candles (int): The number of candles to fetch from the exchange's API endpoint.
    
    :param exchange: Convert the timeframe string to a timedelta object
    :param timeframe_str: Specify the timeframe
    :param num_candles: Calculate the total duration of the candles
    :return: A string in iso 8601 format:
    :doc-author: Trelent
    """
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
    """
    The center_window function takes a tag as an argument and centers the window
    with that tag in the viewport. It does this by first getting the width and height
    of both the viewport (the visible area of your screen) and then gets those same
    dimensions for your window after it has been rendered. Then, it calculates where to 
    position your window so that it is centered in relation to its parent container, 
    which is always going to be the viewport.
    
    :param tag: Identify the window to be centered
    :return: The window's position
    :doc-author: Trelent
    """
    # Get the viewport's width and height
    viewport_width, viewport_height = (
        dpg.get_viewport_client_width(),
        dpg.get_viewport_client_height(),
    )

    # Get the window's width and height after it has been rendered
    window_width, window_height = dpg.get_item_width(tag), dpg.get_item_height(tag)

    # Calculate the position to center the window
    pos_x = (viewport_width - window_width) * 0.5
    pos_y = (viewport_height - window_height) * 0.5

    # Set the window's position
    dpg.set_item_pos(tag, [pos_x, pos_y])


def create_loading_modal(message="Loading..."):
    """
    The create_loading_modal function creates a modal window with the given message and a loading indicator.

    :param message: Display a message to the user while they wait for the process to complete
    :return: A window object, which we can use to close the modal later
    :doc-author: Trelent
    """
    with dpg.window(label="Loading...", autosize=True, tag="loading_modal"):
        dpg.add_text(message)
        dpg.add_loading_indicator()

    # Center the modal once it's rendered
    dpg.render_dearpygui_frame()
    center_window("loading_modal")


def create_timed_popup(message, time, label="Take Note", additional_ui_callback=None):
    """
    Create a popup modal that displays a message for a specified time.

    :param message: The message to display in the popup.
    :param time: The duration in seconds for which the popup is displayed.
    :param additional_ui_callback: A callback function to add additional UI elements to the popup.
    """

    with dpg.window(label=label, autosize=True, tag="popup_modal"):
        dpg.add_text(message)
        if additional_ui_callback:
            additional_ui_callback()

    # Center the modal
    dpg.render_dearpygui_frame()
    center_window("popup_modal")

    # Set a timer to close and delete the popup
    threading.Timer(time, lambda: delete_popup_modal("popup_modal")).start()


def delete_popup_modal(window_tag):
    """
    Close and delete the specified popup modal.

    :param window_tag: The tag of the window to delete.
    """
    if dpg.does_item_exist(window_tag):
        dpg.delete_item(window_tag)


def searcher(searcher, result, search_list):
    """This function is used to search a listbox based on a list.

    Args:
        searcher (dpg input item): this is the tag of the input box the user types into
        result (dpg listbox/combo box (maybe?)): this is the listbox tag
        search_list (list): list of items you want to search
    """
    modified_list = []

    search_value = dpg.get_value(searcher)
    if search_value is None:
        search_value = ""

    if search_value == "*":
        modified_list.extend(iter(search_list))

    elif search_value.lower():
        modified_list.extend(
            item for item in search_list if search_value.lower() in item.lower()
        )

    else:
        modified_list.extend(search_list)

    dpg.configure_item(result, items=modified_list)
