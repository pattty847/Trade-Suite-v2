import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Callable
import time

import dearpygui.dearpygui as dpg

from trade_suite.data.data_source import Data
from trade_suite.gui.signals import Signals
from trade_suite.gui.utils import calculate_since, create_loading_modal, create_timed_popup

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
        self.data = data
        self.tasks = {}
        self.tabs = {}
        self.visible_tab = None
        self.loop = None
        self.thread = None
        self.running = True
        
        # Add a queue for thread-safe communication
        self.data_queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # Lock for thread synchronization
        self.lock = threading.Lock()
        
        # Start the event loop in a separate thread
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        
        # Wait for the loop to be initialized
        while self.loop is None:
            time.sleep(0.01)

    def set_visable_tab(self, sender, app_data, user_data):
        """
        The set_visable_tab function is used to set the currently visible tab.
        This is used to determine which tab's data should be displayed.

        :param self: Access the class instance
        :param sender: Identify the sender of the signal
        :param app_data: Pass data from the application
        :param user_data: Pass user-specific data
        :return: None
        :doc-author: Trelent
        """
        self.visible_tab = app_data

    def run_loop(self):
        """
        The run_loop function is the main event loop for the task manager.
        It runs in a separate thread and handles all async operations.

        :param self: Access the class instance
        :return: None
        :doc-author: Trelent
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Start the data processing task
        self.loop.create_task(self._process_data_queue())
        
        # Run the event loop
        self.loop.run_forever()

    async def _process_data_queue(self):
        """
        Process data from the queue in a thread-safe manner.
        This ensures that data is properly synchronized between threads.
        """
        while self.running:
            try:
                # Get data from the queue with a timeout
                data = await asyncio.wait_for(self.data_queue.get(), timeout=0.1)
                
                # Process the data based on its type
                if data.get('type') == 'candles':
                    # Use the executor to safely update the UI
                    await self.loop.run_in_executor(
                        self.executor, 
                        self._update_ui_with_candles, 
                        data.get('tab'), 
                        data.get('exchange'), 
                        data.get('candles')
                    )
                elif data.get('type') == 'trades':
                    await self.loop.run_in_executor(
                        self.executor, 
                        self._update_ui_with_trades, 
                        data.get('tab'), 
                        data.get('exchange'), 
                        data.get('trades')
                    )
                elif data.get('type') == 'orderbook':
                    await self.loop.run_in_executor(
                        self.executor, 
                        self._update_ui_with_orderbook, 
                        data.get('tab'), 
                        data.get('exchange'), 
                        data.get('orderbook')
                    )
                
                # Mark the task as done
                self.data_queue.task_done()
            except asyncio.TimeoutError:
                # No data in the queue, continue
                continue
            except Exception as e:
                logging.error(f"Error processing data queue: {e}")

    def _update_ui_with_candles(self, tab, exchange, candles):
        """Thread-safe method to update UI with candles data"""
        with self.lock:
            # Emit the signal to update the UI
            self.data.emitter.emit(Signals.NEW_CANDLES, tab, exchange, candles)

    def _update_ui_with_trades(self, tab, exchange, trades):
        """Thread-safe method to update UI with trades data"""
        with self.lock:
            # Emit the signal to update the UI
            self.data.emitter.emit(Signals.NEW_TRADE, tab, exchange, trades)

    def _update_ui_with_orderbook(self, tab, exchange, orderbook):
        """Thread-safe method to update UI with orderbook data"""
        with self.lock:
            # Emit the signal to update the UI
            self.data.emitter.emit(Signals.NEW_ORDERBOOK, tab, exchange, orderbook)

    def start_task(self, name: str, coro):
        """
        The start_task function is used to start a new task in the event loop.
        It creates a task and stores it in the tasks dictionary.

        :param self: Access the class instance
        :param name: Identify the task
        :param coro: Specify the coroutine to run
        :return: None
        :doc-author: Trelent
        """
        if name in self.tasks:
            self.stop_task(name)

        task = self.create_task(name, coro)
        self.tasks[name] = task

    def create_task(self, name: str, coro):
        """
        The create_task function creates a new task in the event loop.
        It also sets up a callback to handle task completion.

        :param self: Access the class instance
        :param name: Identify the task
        :param coro: Specify the coroutine to run
        :return: The task object
        :doc-author: Trelent
        """
        # Wrap the coroutine to catch exceptions and store results
        async def wrapped_coro():
            try:
                result = await coro
                return result, None # Return result and no error
            except asyncio.CancelledError:
                logging.info(f"Task '{name}' was cancelled.")
                raise # Re-raise CancelledError so asyncio handles it properly
            except Exception as e:
                logging.error(f"Error in task '{name}': {e}", exc_info=True)
                return None, e # Return no result and the error

        task = self.loop.create_task(wrapped_coro())
        task.add_done_callback(lambda t: self._on_task_complete(name, t))
        return task

    def start_stream_for_chart(self, tab, exchange, symbol, timeframe):
        """
        The start_stream_for_chart function starts the data streams for a chart.
        It starts the trades and orderbook streams for the specified exchange and symbol.

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

        # This will emit the candles to listeners and return a future
        candles_future = self._get_candles_for_market(
            tab, exchange, symbol, timeframe
        ) 
        
        # Task ID for trades stream (usually specific to the chart/tab)
        trades_task = f"trades_{exchange}_{symbol}_{tab}"
        # Task ID for the shared orderbook stream (generic)
        orderbook_task = f"orderbook_{exchange}_{symbol}"

        # Create wrapped coroutines that use the queue for thread-safe communication
        async def wrapped_watch_trades():
            try:
                # The watch_trades method already has its own while loop
                await self.data.watch_trades(
                    tab=tab, exchange=exchange, symbol=symbol, track_stats=True
                )
            except Exception as e:
                logging.error(f"Error in trades stream: {e}")

        async def wrapped_watch_orderbook():
            try:
                # The watch_orderbook method already has its own while loop
                await self.data.watch_orderbook(
                    tab=tab,
                    exchange=exchange,
                    symbol=symbol,
                )
            except Exception as e:
                logging.error(f"Error in orderbook stream: {e}")
        
        # Modified: Only start trade and orderbook streams after candles are fetched
        def start_streams_after_candles(fut):
            try:
                # Get the result of the future to ensure candles have been fetched
                fut.result()
                logging.info(f"Candles loaded. Starting trade and orderbook streams for {symbol} on {exchange}.")
                
                # Now start the trade and orderbook streams
                self.start_task(
                    trades_task,
                    coro=wrapped_watch_trades(),
                )
                
                # Start orderbook task using the GENERIC ID
                # It might already be running if another widget requested it,
                # start_task handles overwriting/cancelling the old one if necessary,
                # but ideally we check is_stream_running first.
                # For simplicity here, we rely on start_task idempotency.
                # A more robust solution might check first.
                if not self.is_stream_running(orderbook_task):
                    logging.info(f"Starting shared orderbook stream: {orderbook_task}")
                    self.start_task(
                        orderbook_task,
                        coro=wrapped_watch_orderbook(),
                    )
                else:
                    logging.info(f"Shared orderbook stream {orderbook_task} already running.")
                
                # Add BOTH task IDs to the tab's tracking list
                self.tabs[tab] = [trades_task, orderbook_task]
            except Exception as e:
                logging.error(f"Error starting streams after candles: {e}")
        
        # Add the callback to start streams only after candles are fetched
        candles_future.add_done_callback(start_streams_after_candles)

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

        # Use a simpler approach that doesn't cause GIL issues
        print(f"Fetching candles for {exchange} {symbol} {timeframe}...")
        
        # Create a future to run the coroutine
        future = asyncio.run_coroutine_threadsafe(
            self._fetch_candles_with_queue(
                tab=tab,
                exchanges=[exchange],
                symbols=[symbol],
                timeframes=[timeframe],
                since=since,
                write_to_db=False,
            ),
            self.loop
        )
        
        # Add a callback to handle task completion
        def on_task_complete(fut):
            try:
                # Get the result of the future
                result = fut.result()
                print(f"Candles fetched for {exchange} {symbol} {timeframe}")
                return result
            except Exception as e:
                # Log the error
                logging.error(f"Error fetching candles: {e}")
                print(f"Error fetching candles: {e}")
                # Re-raise the exception
                raise
        
        # Add a callback to handle task completion
        future.add_done_callback(on_task_complete)
        
        # Return the future
        return future

    async def _fetch_candles_with_queue(self, tab, exchanges, symbols, timeframes, since, write_to_db=False):
        """
        Fetch candles and put them in the queue for thread-safe processing
        """
        candles = await self.data.fetch_candles(
            tab=tab,
            exchanges=exchanges,
            symbols=symbols,
            timeframes=timeframes,
            since=since,
            write_to_db=write_to_db,
        )
        
        # Put the candles data in the queue
        await self.data_queue.put({
            'type': 'candles',
            'tab': tab,
            'exchange': exchanges[0],
            'candles': candles
        })
        
        return candles

    def run_task_until_complete(self, coro):
        """
        The run_task_until_complete function runs a coroutine until it completes.
        It creates a future and runs it in the event loop.

        :param self: Access the class instance
        :param coro: Specify the coroutine to run
        :return: The result of the coroutine
        :doc-author: Trelent
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def run_task_with_loading_popup(self, coro, message="Please wait..."):
        """
        The run_task_with_loading_popup function runs a coroutine with a loading popup.
        It creates a future and runs it in the event loop, showing a loading popup while it runs.

        :param self: Access the class instance
        :param coro: Specify the coroutine to run
        :param message: Display a message in the loading popup
        :return: The result of the coroutine
        :doc-author: Trelent
        """
        # Create a future to run the coroutine
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        
        # Use a simple approach to show a loading message without creating a modal
        # This avoids GIL issues by not using DearPyGUI in a non-main thread
        print(f"Loading: {message}")
        
        def on_task_complete(fut):
            # This function will be called when the future completes
            try:
                # Get the result of the future
                result = fut.result()
                print(f"Loading complete: {message}")
                return result
            except Exception as e:
                # Log the error
                logging.error(f"Error in task: {e}")
                print(f"Error: {e}")
                # Re-raise the exception
                raise
        
        # Add a callback to handle task completion
        future.add_done_callback(on_task_complete)
        
        # Return the future
        return future

    def stop_task(self, name: str):
        """
        The stop_task function stops a task by name.
        It cancels the task and removes it from the tasks dictionary.

        :param self: Access the class instance
        :param name: Identify the task to stop
        :return: None
        :doc-author: Trelent
        """
        if name in self.tasks:
            self.tasks[name].cancel()
            del self.tasks[name]

    def stop_all_tasks(self):
        """
        The stop_all_tasks function stops all tasks.
        It cancels all tasks and clears the tasks dictionary.

        :param self: Access the class instance
        :return: None
        :doc-author: Trelent
        """
        for name in list(self.tasks.keys()):
            self.stop_task(name)

    def is_task_running(self, task_id):
        """
        The is_task_running function checks if a task is running.
        It returns True if the task is running, False otherwise.

        :param self: Access the class instance
        :param task_id: Identify the task to check
        :return: True if the task is running, False otherwise
        :doc-author: Trelent
        """
        return task_id in self.tasks and not self.tasks[task_id].done()

    def _on_task_complete(self, name, task):
        """
        The _on_task_complete function is called when a task completes.
        It removes the task from the tasks dictionary.

        :param self: Access the class instance
        :param name: Identify the task
        :param task: The task object
        :return: None
        :doc-author: Trelent
        """
        if name in self.tasks:
            del self.tasks[name]

        # Emit signals based on task outcome
        try:
            result, error = task.result() # Unpack result from wrapped_coro
            if task.cancelled():
                # Don't emit signal if cancelled explicitly
                logging.debug(f"Task '{name}' completion handled (cancelled).")
            elif error:
                 # Emit TASK_ERROR signal
                 self.data.emitter.emit(Signals.TASK_ERROR, task_name=name, error=error)
                 logging.debug(f"Emitted TASK_ERROR for '{name}'. Error: {error}")
            else:
                 # Emit TASK_SUCCESS signal
                 self.data.emitter.emit(Signals.TASK_SUCCESS, task_name=name, result=result)
                 logging.debug(f"Emitted TASK_SUCCESS for '{name}'. Result type: {type(result)}")
        except asyncio.CancelledError:
            logging.debug(f"Task '{name}' completion handled (cancelled exception caught).")
        except Exception as e:
            # Catch potential errors retrieving result (though wrapped_coro should prevent most)
            logging.error(f"Error processing task completion for '{name}': {e}", exc_info=True)
            self.data.emitter.emit(Signals.TASK_ERROR, task_name=name, error=e)

    def cleanup(self):
        """
        Clean up resources when the application is closing.
        This method should be called when the application is shutting down.
        """
        # Stop all tasks
        self.stop_all_tasks()
        
        # Set running to False to stop the data queue processing
        self.running = False
        
        # Shutdown the executor
        self.executor.shutdown(wait=True)
        
        # Stop the event loop
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        # Wait for the thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            
        logging.info("TaskManager cleanup completed")

    def is_stream_running(self, stream_id: str) -> bool:
        """Check if a task with the given ID is currently running."""
        return stream_id in self.tasks and not self.tasks[stream_id].done()
