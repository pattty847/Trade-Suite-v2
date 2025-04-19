import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Callable, Set, Tuple
import time
from collections import defaultdict
import pandas as pd

import dearpygui.dearpygui as dpg

from trade_suite.data.data_source import Data
from trade_suite.gui.signals import Signals
from trade_suite.gui.utils import calculate_since, create_loading_modal, create_timed_popup
from trade_suite.data.candle_factory import CandleFactory


class TaskManager:
    def __init__(self, data: Data):
        self.data = data
        self.tasks: Dict[str, asyncio.Task] = {}
        self.visible_tab = None
        self.loop: asyncio.AbstractEventLoop = None
        self.thread: threading.Thread = None
        self.running = True
        
        # Centralized factory storage (keyed by (exchange, symbol, timeframe))
        self.candle_factories: Dict[Tuple[str, str, str], CandleFactory] = {}
        
        # Reference counting and subscription tracking
        self.stream_ref_counts: Dict[str, int] = defaultdict(int)
        self.factory_ref_counts: Dict[Tuple[str, str, str], int] = defaultdict(int)
        # Maps widget instance to a set of resource keys (stream or factory) it requires
        self.widget_subscriptions: Dict[Any, Set[str | Tuple[str, str, str]]] = defaultdict(set)
        
        # Add a queue for thread-safe communication
        self.data_queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # Lock for thread synchronization (primarily for accessing shared resources like factories/counts)
        self.lock = threading.Lock()
        
        # Start the event loop in a separate thread
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        
        # Wait for the loop to be initialized
        while self.loop is None:
            time.sleep(0.01)

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
        """Process items from the data queue"""
        while self.running:
            try:
                # Block until an item is available or a timeout occurs
                data = await asyncio.wait_for(self.data_queue.get(), timeout=1.0)
                if data:
                    data_type = data.get("type")
                    if data_type == "candles":
                        # Extract candle data including symbol and timeframe
                        exchange = data.get("exchange")
                        symbol = data.get("symbol")
                        timeframe = data.get("timeframe")
                        candles = data.get("candles")
                        # Update UI with candle data using keywords, no tab
                        self._update_ui_with_candles(
                            exchange=exchange,
                            symbol=symbol,
                            timeframe=timeframe,
                            candles=candles
                        )
                    elif data_type == "trades":
                        # Extract trade data
                        exchange = data.get("exchange")
                        trade_data = data.get("trades") # Assuming 'trades' is the single trade dict
                        # Update UI with trade data using keywords, no tab
                        self._update_ui_with_trades(exchange=exchange, trade_data=trade_data)
                    elif data_type == "orderbook":
                        # Extract orderbook data
                        exchange = data.get("exchange")
                        orderbook = data.get("orderbook")
                        # Update UI with orderbook data using keywords
                        self._update_ui_with_orderbook(exchange=exchange, orderbook=orderbook)

                    self.data_queue.task_done()
            except asyncio.TimeoutError:
                # No item received within the timeout, continue loop
                continue
            except Exception as e:
                logging.error(f"Error processing data queue: {e}")

    def _update_ui_with_candles(self, exchange, symbol, timeframe, candles):
        """Thread-safe method to update UI with initial/bulk candles data"""
        logging.debug(f"TaskManager emitting NEW_CANDLES for {exchange}/{symbol}/{timeframe}")
        self.data.emitter.emit(
            Signals.NEW_CANDLES,
            exchange=exchange,
            symbol=symbol,     # Added symbol
            timeframe=timeframe, # Added timeframe
            candles=candles
        )

    def _update_ui_with_trades(self, exchange, trade_data):
        """Thread-safe method to update UI with trades data"""
        self.data.emitter.emit(Signals.NEW_TRADE, exchange=exchange, trade_data=trade_data)

    def _update_ui_with_orderbook(self, exchange, orderbook):
        """Thread-safe method to update UI with orderbook data"""
        self.data.emitter.emit(Signals.ORDER_BOOK_UPDATE, exchange=exchange, orderbook=orderbook)

    def start_task(self, name: str, coro):
        """
        Starts a new task in the event loop if it's not already running.
        Handles task creation, storage, and completion callback setup.
        Does NOT stop existing task with the same name anymore. Check before calling if restart is needed.
        """
        task = self.create_task(name, coro)
        if task: # Only store if task creation was successful
            self.tasks[name] = task
        else:
             logging.warning(f"Failed to create or schedule task '{name}'")

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

        task = asyncio.run_coroutine_threadsafe(wrapped_coro(), self.loop)
        return task

    def _get_resource_keys(self, requirements: dict) -> List[str | Tuple[str, str, str]]:
        """Helper to determine resource keys from widget requirements."""
        keys = []
        req_type = requirements.get("type")
        exchange = requirements.get("exchange")
        symbol = requirements.get("symbol")
        timeframe = requirements.get("timeframe")

        if not exchange or not symbol:
            logging.warning(f"Missing exchange or symbol in requirements: {requirements}")
            return keys

        if req_type == 'candles':
            if not timeframe:
                 logging.warning(f"Missing timeframe for candles requirement: {requirements}")
                 return keys
            # Candles require a factory and the underlying trade stream
            factory_key = (exchange, symbol, timeframe)
            trade_stream_key = f"trades_{exchange}_{symbol}"
            keys.append(factory_key)
            keys.append(trade_stream_key)
        elif req_type == 'trades':
            trade_stream_key = f"trades_{exchange}_{symbol}"
            keys.append(trade_stream_key)
        elif req_type == 'orderbook':
            orderbook_stream_key = f"orderbook_{exchange}_{symbol}"
            keys.append(orderbook_stream_key)
        else:
            logging.warning(f"Unknown requirement type: {req_type}")

        return keys

    def subscribe(self, widget, requirements: dict):
        """
        Subscribes a widget to data based on requirements.
        Manages resource reference counting and starts/creates resources if needed.
        """
        with self.lock: # Ensure thread safety when modifying counts/factories/tasks
            resource_keys = self._get_resource_keys(requirements)
            if not resource_keys:
                logging.error(f"Could not determine resources for widget {widget} with requirements {requirements}")
                return

            widget_id = id(widget) # Use widget id as key for simplicity
            logging.info(f"Subscribing widget {widget_id} with requirements {requirements}. Resources: {resource_keys}")
            self.widget_subscriptions[widget_id].update(resource_keys)

            needs_initial_candles = False
            initial_candle_details = {}

            for key in resource_keys:
                if isinstance(key, tuple): # Factory key (exchange, symbol, timeframe)
                    exchange, symbol, timeframe = key
                    self.factory_ref_counts[key] += 1
                    logging.debug(f"Factory ref count for {key} incremented to {self.factory_ref_counts[key]}")
                    if self.factory_ref_counts[key] == 1:
                        # Create CandleFactory if it doesn't exist
                        if key not in self.candle_factories:
                            logging.info(f"Creating new CandleFactory for key: {key}")
                            # Ensure required arguments are passed
                            ccxt_exchange = self.data.exchange_list.get(exchange)
                            if not ccxt_exchange:
                                logging.error(f"CCXT exchange object not found for '{exchange}' in TaskManager. Cannot fetch initial candles.")
                                return
                            candle_factory = CandleFactory(
                                exchange=exchange,
                                symbol=symbol, # Added symbol to constructor if needed
                                timeframe_str=timeframe,
                                emitter=self.data.emitter,
                                task_manager=self, # Pass the TaskManager instance
                                data=self.data # Pass the Data instance
                            )
                            self.candle_factories[key] = candle_factory
                            # Mark that initial candles are needed for this new factory
                            needs_initial_candles = True
                            initial_candle_details = {'exchange': exchange, 'symbol': symbol, 'timeframe': timeframe}
                            logging.info(f"CandleFactory created and stored for {key}.")
                        else:
                            logging.info(f"CandleFactory already exists for {key}")
                
                elif isinstance(key, str): # Stream key
                    self.stream_ref_counts[key] += 1
                    logging.debug(f"Stream ref count for {key} incremented to {self.stream_ref_counts[key]}")
                    if self.stream_ref_counts[key] == 1:
                        logging.info(f"Starting stream for key: {key}")
                        # Determine stream type and start
                        if key.startswith("trades_"):
                            _, exch, sym = key.split("_", 2)
                            coro = self._get_watch_trades_coro(exch, sym)
                            if coro:
                                self.start_task(key, coro)
                            else:
                                logging.error(f"Could not create trade stream coroutine for {key}")
                                self.stream_ref_counts[key] -= 1 # Rollback count
                                self.widget_subscriptions[widget_id].remove(key) # Remove from widget sub

                        elif key.startswith("orderbook_"):
                             _, exch, sym = key.split("_", 2)
                             coro = self._get_watch_orderbook_coro(exch, sym)
                             if coro:
                                 self.start_task(key, coro)
                             else:
                                 logging.error(f"Could not create orderbook stream coroutine for {key}")
                                 self.stream_ref_counts[key] -= 1 # Rollback count
                                 self.widget_subscriptions[widget_id].remove(key) # Remove from widget sub
            
            # Trigger initial candle fetch outside the loop if a new factory was created
            if needs_initial_candles and initial_candle_details:
                 logging.info(f"Triggering initial candle fetch for {initial_candle_details}")
                 # Use run_coroutine_threadsafe as this might be called from UI thread
                 asyncio.run_coroutine_threadsafe(
                     self._fetch_initial_candles_for_factory(**initial_candle_details),
                     self.loop
                 )

    def unsubscribe(self, widget):
        """
        Unsubscribes a widget, decrementing resource counts and cleaning up if necessary.
        """
        with self.lock: # Ensure thread safety
            widget_id = id(widget)
            if widget_id not in self.widget_subscriptions:
                 logging.warning(f"Widget {widget_id} not found in subscriptions during unsubscribe.")
                 return

            resource_keys = self.widget_subscriptions.pop(widget_id)
            logging.info(f"Unsubscribing widget {widget_id}. Resources: {resource_keys}")

            for key in resource_keys:
                if isinstance(key, tuple): # Factory key
                    if key in self.factory_ref_counts:
                        self.factory_ref_counts[key] -= 1
                        logging.debug(f"Factory ref count for {key} decremented to {self.factory_ref_counts[key]}")
                        if self.factory_ref_counts[key] == 0:
                             logging.info(f"Reference count is 0. Deleting CandleFactory for key: {key}")
                             if key in self.candle_factories:
                                 # Add potential cleanup logic for the factory itself if needed
                                 del self.candle_factories[key]
                                 logging.info(f"CandleFactory deleted for {key}.")
                             del self.factory_ref_counts[key] # Remove from counts dict
                    else:
                         logging.warning(f"Factory key {key} not found in ref counts during unsubscribe.")

                elif isinstance(key, str): # Stream key
                    if key in self.stream_ref_counts:
                        self.stream_ref_counts[key] -= 1
                        logging.debug(f"Stream ref count for {key} decremented to {self.stream_ref_counts[key]}")
                        if self.stream_ref_counts[key] == 0:
                             logging.info(f"Reference count is 0. Stopping stream task: {key}")
                             self.stop_task(key) # Stop the stream task
                             del self.stream_ref_counts[key] # Remove from counts dict
                    else:
                         logging.warning(f"Stream key {key} not found in ref counts during unsubscribe.")

    # Helper methods to create stream coroutines
    def _get_watch_trades_coro(self, exchange: str, symbol: str):
        """Returns the coroutine for watching trades."""
        async def wrapped_watch_trades():
            try:
                # Assumes watch_trades puts data on the queue internally now, or handles signals
                # Removed tab parameter
                await self.data.watch_trades(
                    exchange=exchange, symbol=symbol, track_stats=True
                )
            except asyncio.CancelledError:
                 logging.info(f"Trade stream task trades_{exchange}_{symbol} cancelled.")
                 raise # Re-raise
            except Exception as e:
                 logging.error(f"Error in trade stream {exchange}/{symbol}: {e}", exc_info=True)
        return wrapped_watch_trades() # Return the coroutine object itself

    def _get_watch_orderbook_coro(self, exchange: str, symbol: str):
        """Returns the coroutine for watching orderbook."""
        async def wrapped_watch_orderbook():
            try:
                # Assumes watch_orderbook puts data on the queue internally now
                # Removed tab parameter
                await self.data.watch_orderbook(
                    exchange=exchange,
                    symbol=symbol,
                )
            except asyncio.CancelledError:
                 logging.info(f"Orderbook stream task orderbook_{exchange}_{symbol} cancelled.")
                 raise # Re-raise
            except Exception as e:
                 logging.error(f"Error in orderbook stream {exchange}/{symbol}: {e}", exc_info=True)
        return wrapped_watch_orderbook() # Return the coroutine object itself

    async def _fetch_initial_candles_for_factory(self, exchange: str, symbol: str, timeframe: str):
        """Fetches initial candles and puts them onto the data queue."""
        logging.info(f"Fetching initial candles for {exchange}/{symbol}/{timeframe}")
        
        # Get the actual CCXT exchange object from Data
        ccxt_exchange = self.data.exchange_list.get(exchange)
        if not ccxt_exchange:
             logging.error(f"CCXT exchange object not found for '{exchange}' in TaskManager. Cannot fetch initial candles.")
             return
             
        try:
            # Determine 'since' based on timeframe, similar to old logic
            since = calculate_since(ccxt_exchange, timeframe, num_candles=1000) 
            
            # Fetch candles using data source method (assuming it's adapted or suitable)
            # Assuming fetch_candles now returns the dataframe directly
            # And does NOT interact with the queue or signals itself.
            candles_dict = await self.data.fetch_candles( # Renamed to candles_dict
                 exchanges=[exchange],
                 symbols=[symbol],
                 timeframes=[timeframe],
                 since=since,
                 write_to_db=False # Or based on config
            )

            # Extract the relevant DataFrame using the expected key structure
            cache_key = f"{exchange}_{symbol.replace('/', '-')}_{timeframe}"
            candles_df = candles_dict.get(exchange, {}).get(cache_key)

            # Seed the corresponding CandleFactory with this initial data
            factory_key = (exchange, symbol, timeframe)
            factory_instance = self.candle_factories.get(factory_key)
            if factory_instance:
                factory_instance.set_initial_data(candles_df)
            else:
                logging.error(f"Could not find CandleFactory instance for {factory_key} to set initial data.")

            if candles_df is not None and not candles_df.empty:
                 logging.info(f"Fetched {len(candles_df)} initial candles for {exchange}/{symbol}/{timeframe}. Putting onto queue.")
                 # Put data onto the queue for _process_data_queue to handle
                 await self.data_queue.put({
                     "type": "candles",
                     "exchange": exchange,
                     "symbol": symbol,
                     "timeframe": timeframe,
                     "candles": candles_df
                 })
            else:
                 logging.warning(f"No initial candles returned for {exchange}/{symbol}/{timeframe}.")

        except Exception as e:
            logging.error(f"Error fetching initial candles for {exchange}/{symbol}/{timeframe}: {e}", exc_info=True)

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
        Stops a task by name.
        """
        task = self.tasks.pop(name, None)
        if task:
            logging.info(f"Stopping task: {name}")
            try:
                 # Cancel the task using the correct method for threadsafe coroutines
                 # task.cancel() # This might be for tasks created directly in the loop
                 # For tasks started with run_coroutine_threadsafe, cancellation needs care
                 # Often, it's better to signal the coroutine internally to stop.
                 # If direct cancellation is supported by the Future:
                 if hasattr(task, 'cancel'):
                      task.cancel()
                      logging.info(f"Cancellation requested for task: {name}")
                 else:
                     logging.warning(f"Task {name} future object does not support direct cancellation.")
                 # We might need to wait briefly or check task status after cancellation attempt
            except Exception as e:
                logging.error(f"Error cancelling task {name}: {e}", exc_info=True)
        else:
            logging.warning(f"Task {name} not found for stopping.")

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
        
        # Ensure CandleFactories are also cleaned up if necessary? Or handled by unsubscribe?
        self.candle_factories.clear()
        self.factory_ref_counts.clear()
        self.stream_ref_counts.clear()
        self.widget_subscriptions.clear()
        logging.info("All tasks stopped and resources cleared.")

    def is_task_running(self, task_id):
        """
        Checks if a task exists and is not done.
        """
        task = self.tasks.get(task_id)
        return task is not None and not task.done()

    def _on_task_complete(self, name, task_future):
        """
        Callback executed when a task started via create_task (asyncio.create_task) finishes.
        NOTE: This might need adjustment if tasks are primarily managed via run_coroutine_threadsafe.
        Futures returned by run_coroutine_threadsafe might need different handling.
        """
        # Ensure this callback is running in the context of the event loop thread
        # If called from another thread, marshalling might be needed.

        # Remove the task from the dictionary regardless of outcome
        # Use pop with default to avoid KeyError if already removed or stopped
        self.tasks.pop(name, None)

        try:
            # Check if the future raised an exception
            exception = task_future.exception()
            if exception:
                # Log specific cancellation error differently
                if isinstance(exception, asyncio.CancelledError):
                     logging.info(f"Task '{name}' was cancelled successfully.")
                else:
                     logging.error(f"Task '{name}' completed with error: {exception}", exc_info=exception)
            else:
                # Task completed successfully
                result = task_future.result() # Get result if needed (often None for streams)
                logging.info(f"Task '{name}' completed successfully.") # Result: {result}") # Avoid logging large results

        except asyncio.InvalidStateError:
             # This can happen if the future was cancelled and we check exception() too early
             logging.warning(f"Task '{name}' completion checked in invalid state (likely cancelled).")
        except Exception as e:
            # Catch any other unexpected errors during callback execution
             logging.error(f"Error in _on_task_complete for task '{name}': {e}", exc_info=True)

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
        """Checks if a stream task is currently running."""
        return self.is_task_running(stream_id)
