import asyncio
import logging
import threading
import dearpygui.dearpygui as dpg

from data.data_source import Data
from gui.signals import Signals
from gui.utils import calculate_since, create_loading_modal

"""
Mechanism:

Separate Thread for Asyncio: It creates a dedicated background thread (self.thread) solely to run an asyncio event loop (self.loop). This is a standard and good approach to prevent blocking the main DearPyGUI thread.

Running Coroutines: When the GUI needs to start an async operation (like watch_trades or fetch_candles), it calls a method like start_task or start_stream_for_chart. These methods use asyncio.run_coroutine_threadsafe(coroutine, self.loop) to schedule the coroutine to run on the dedicated asyncio loop in the background thread.

Task Tracking: It keeps track of running tasks in a dictionary (self.tasks) using generated names (e.g., trades_{exchange}_{symbol}_{tab}). This allows specific tasks to be cancelled later (e.g., when switching symbols or closing a tab). It also uses self.tabs to group tasks belonging to a specific GUI tab.

GUI Updates (Implied): While TaskManager starts the data fetching/streaming tasks (by calling methods on the self.data object), it doesn't directly handle the incoming data or update the GUI itself. The coroutines it starts (like self.data.watch_trades and self.data.watch_orderbook) are responsible for processing the data received from ccxt and, presumably, using the SignalEmitter (which we know Data has) to send signals with the processed data. The GUI components (Chart, Orderbook, etc.) would listen for these signals and update themselves using dpg.set_value or similar functions, likely wrapped in dpg.submit_callback to ensure thread safety if the signal handling happens directly in the async context (though often the signal emitter handles dispatching to the main thread).

Blocking Operations: For operations that need to wait for a result (like the initial candle fetch), it provides run_task_until_complete and run_task_with_loading_popup. These use future.result(), which blocks the calling thread (the main GUI thread in the case of the popup) until the async task completes. Using the loading popup version is good UX for this.
"""


class TaskManager:
    def __init__(self, data: Data):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.tasks = {}
        self.data = data
        self.active_symbol = None
        self.visable_tab = None
        self.tabs = {}

    def set_visable_tab(self, sender, app_data, user_data):
        """
        The set_visable_tab function is called when the user clicks on a tab.
        It sets the visable_tab variable to be equal to the id of the tab, which is passed in from the callback
        function in the 'app_data' parameter. The visable_tab variable will then be used by other functions.

        :param self: Represent the instance of the class
        :param sender: Identify the widget that called the function
        :param app_data: Set the visable_tab variable to the value of app_data
        :param user_data: Pass data to the callback function
        :return: The value of the visable_tab variable
        :doc-author: Trelent
        """
        self.visable_tab = app_data

    def run_loop(self):
        """
        The run_loop function is the main function that starts the asyncio event loop.
            It sets up a new event loop and runs it forever.

        :param self: Represent the instance of a class
        :return: Nothing
        :doc-author: Trelent
        """
        logging.info(f"Starting async thread.")
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_task(self, name: str, coro):
        """
        The start_task function is a wrapper around asyncio.run_coroutine_threadsafe,
        which allows us to run coroutines in the main thread's event loop from other threads.
        It also adds the task to a dictionary of tasks so that we can cancel them later.

        :param self: Access the class variables and methods
        :param name: str: Identify the task
        :param coro:
        :return: A task object
        :doc-author: Trelent
        """
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))

    def create_task(self, name: str, coro):
        """Alias for start_task with parameters in different order for better readability."""
        return self.start_task(name, coro)

    def start_stream_for_chart(self, tab, exchange, symbol, timeframe):
        """
        The start_stream_for_chart function is called when a user clicks on a market in the UI.
        It will stop any existing tasks for that tab, and start new ones to stream data from the exchange.
        The function also calls get_candles_for_market which emits candles to listeners.

        :param self: Bind the method to an object
        :param tab: Identify the tab that is being used
        :param exchange: Specify which exchange we want to get data from
        :param symbol: Determine which market to get data for
        :param timeframe: Determine the interval of time to be used for the chart
        :return: A list of tasks
        :doc-author: Trelent
        """

        # We want to stop the old tab's tasks when requesting a new stream
        if tab in self.tabs:
            for task in self.tabs[tab]:
                self.stop_task(task)

        # This will emit the candles to listeners
        self._get_candles_for_market(
            tab, exchange, symbol, timeframe
        ) 
        
        trades_task = f"trades_{exchange}_{symbol}_{tab}"
        orderbook_task = f"orderbook_{exchange}_{symbol}_{tab}"

        self.start_task(
            trades_task,
            coro=self.data.watch_trades(
                tab=tab, exchange=exchange, symbol=symbol, track_stats=True
            ),
        )

        self.start_task(
            orderbook_task,
            coro=self.data.watch_orderbook(
                tab=tab,
                exchange=exchange,
                symbol=symbol,
            ),
        )

        self.tabs[tab] = [trades_task, orderbook_task]

    def _get_candles_for_market(self, tab, exchange, symbol, timeframe):
        """
        The get_candles_for_market function is used to fetch candles for a given market.

        :param self: Access the class instance
        :param tab: Identify which tab the data is being fetched for
        :param exchange: Specify which exchange to get the data from
        :param symbol: Get the candles for a specific symbol
        :param timeframe: Determine the timeframe of the candles
        :return: The following:
        :doc-author: Trelent
        """
        # TODO: Make number of candles variable
        since = calculate_since(
            self.data.exchange_list[exchange], timeframe, num_candles=500
        )

        self.run_task_with_loading_popup(
            self.data.fetch_candles(
                tab=tab,
                exchanges=[exchange],
                symbols=[symbol],
                timeframes=[timeframe],
                since=since,
                write_to_db=False,
            )
        )

    def run_task_until_complete(self, coro):
        """
        The run_task_until_complete function is a wrapper around asyncio.run_coroutine_threadsafe that
            handles exceptions and cancellation, and returns the result of the coroutine.

        :param self: Represent the instance of the class
        :param coro: Pass the coroutine to be run in a thread
        :return: The result of the coroutine
        :doc-author: Trelent
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result()
        except asyncio.CancelledError:
            logging.error("Task was cancelled.")
            # Handle task cancellation, if needed
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            # Handle other exceptions

    def run_task_with_loading_popup(self, coro, message="Please wait..."):
        """
        The run_task_with_loading_popup function is a wrapper for asyncio.run_coroutine_threadsafe that displays a loading modal while the coroutine runs.
        
        Used when you need to run an async function call to the exchange and it requires loading and waiting. 

        :param self: Access the class instance
        :param coro: Pass in the coroutine to run
        :param message: Display a message in the loading modal
        :return: A future
        :doc-author: Trelent
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        # Display the loading modal
        create_loading_modal(message)

        def on_task_complete(fut):
            # This function will be called when the future completes
            dpg.delete_item("loading_modal")
            try:
                return fut.result()
            except asyncio.CancelledError:
                logging.error("Task was cancelled.")
                # Handle task cancellation, if needed
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")
                # Handle other exceptions

        # Add the completion callback to the future
        future.add_done_callback(on_task_complete)
        return future.result()

    def stop_task(self, name: str):
        """
        The stop_task function stops a task by name.


        :param self: Represent the instance of the class
        :param name: str: Specify the name of the task to be stopped
        :return: A boolean value
        :doc-author: Trelent
        """
        if name in self.tasks:
            logging.info(f"Stopping task: {name}")
            self.tasks[name].cancel()

    def stop_all_tasks(self):
        """
        The stop_all_tasks function is called when the user clicks on the close button.
        It sets a flag to indicate that all tasks should stop running, and then it cancels
        all of the asyncio tasks in self.tasks.

        :param self: Access the instance of the class
        :return: Nothing
        :doc-author: Trelent
        """
        if self.data.is_running:
            self.data.is_running = False

        if not self.tasks:
            return

        logging.info(f"Stopping all async tasks: {list(self.tasks.keys())}")
        tasks_copy = dict(self.tasks)  # Create a copy of the dictionary
        for task in tasks_copy.values():
            task.cancel()
        self.tasks.clear()

    def is_task_running(self, task_id):
        """Check if a specific task is currently running.
        
        Args:
            task_id (str): The ID of the task to check
            
        Returns:
            bool: True if the task is running, False otherwise
        """
        return task_id in self.tasks
        
    def stop_task(self, task_id):
        """Stop a specific task by its ID.
        
        Args:
            task_id (str): The ID of the task to stop
            
        Returns:
            bool: True if the task was stopped, False if it wasn't found
        """
        if task_id in self.tasks:
            logging.info(f"Stopping task: {task_id}")
            self.tasks[task_id].cancel()
            del self.tasks[task_id]
            return True
        return False
