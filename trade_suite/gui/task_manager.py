import asyncio
import logging
import threading
from typing import Dict, List, Any, Callable, Set, Tuple
import time
from collections import defaultdict
import pandas as pd

import dearpygui.dearpygui as dpg

from trade_suite.data.data_source import Data
from trade_suite.gui.signals import Signals
from trade_suite.gui.utils import calculate_since, create_loading_modal, create_timed_popup
from trade_suite.data.candle_factory import CandleFactory
from trade_suite.data.sec_api import SECDataFetcher


class TaskManager:
    def __init__(self, data: Data, sec_fetcher: SECDataFetcher):
        self.data = data
        self.sec_fetcher = sec_fetcher
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
        
        # Stream stop events
        self.stream_events: Dict[str, asyncio.Event] = {}
        
        # Lock for thread synchronization (primarily for accessing shared resources like factories/counts)
        self.lock = threading.Lock()
        
        # Start the event loop in a separate thread
        self.thread = threading.Thread(target=self.run_loop, daemon=False) #
        self.thread.start()
        
        # Wait for the loop to be initialized
        while self.loop is None:
            time.sleep(0.01)

        # Now that the asyncio loop is ready, inform Data so it can emit
        # signals thread-safely without the intermediate queue.
        try:
            self.data.set_ui_loop(self.loop)
        except AttributeError:
            # Data class may not yet have the helper if running older version.
            logging.warning("Data object lacks set_ui_loop – direct emit optimisation disabled.")

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
        
        # Run the event loop (no longer schedules a separate data-queue consumer)
        self.loop.run_forever()

    # ---------------- Deprecated Queue API ----------------------
    # The internal asyncio.Queue and its consumer have been removed in favour of
    # emitting signals directly from worker tasks (via SignalEmitter) to the
    # main-thread GUI.  The following stub remains only to avoid import errors
    # if any legacy code calls TaskManager._process_data_queue.
    async def _process_data_queue(self):
        logging.warning("_process_data_queue is deprecated and no longer used.")
        await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # Direct emit helpers (used by worker tasks) – they forward the data to
    # the GUI thread via SignalEmitter.  Keeping them as small wrappers keeps
    # caller code changes minimal.
    # ------------------------------------------------------------------
    def _update_ui_with_candles(self, exchange, symbol, timeframe, candles):
        logging.debug(
            f"TaskManager emitting NEW_CANDLES for {exchange}/{symbol}/{timeframe}"
        )
        self.data.emitter.emit(
            Signals.NEW_CANDLES,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

    def _update_ui_with_trades(self, exchange, trade_data):
        self.data.emitter.emit(
            Signals.NEW_TRADE, exchange=exchange, trade_data=trade_data
        )

    def _update_ui_with_orderbook(self, exchange, orderbook):
        self.data.emitter.emit(
            Signals.ORDER_BOOK_UPDATE, exchange=exchange, orderbook=orderbook
        )

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
                            logging.debug(f"Creating new CandleFactory for key: {key}")
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
                        # Start the stream task if it's the first subscriber
                        if key not in self.tasks or self.tasks[key].done():
                            logging.info(f"Starting new stream task for key: {key}")
                            coro = None
                            # Create and set the event for this stream
                            stop_event = asyncio.Event()
                            stop_event.set()
                            self.stream_events[key] = stop_event
                            
                            # Determine which watch function to call based on the key
                            if key.startswith("trades_"):
                                _, exchange, symbol = key.split("_", 2)
                                coro = self._get_watch_trades_coro(exchange, symbol, stop_event) # Pass event
                            elif key.startswith("orderbook_"):
                                _, exchange, symbol = key.split("_", 2)
                                coro = self._get_watch_orderbook_coro(exchange, symbol, stop_event) # Pass event
                            # Add other stream types here if needed
                            
                            if coro:
                                self.start_task(key, coro)
                            else:
                                logging.warning(f"Could not determine coroutine for stream key: {key}")
                                # Clean up event if task isn't started
                                if key in self.stream_events:
                                    del self.stream_events[key]
                                stop_event.clear() # Ensure it's not left dangling
                                self.stream_ref_counts[key] -= 1 # Decrement count back
                        else:
                             logging.info(f"Stream task {key} is already running.")

            # After potentially creating a new CandleFactory, fetch initial candles
            if needs_initial_candles and initial_candle_details:
                # Run fetching in the background, do not block subscription
                self.run_task_until_complete(
                    self._fetch_initial_candles_for_factory(**initial_candle_details),
                )

    def unsubscribe(self, widget):
        """
        Unsubscribes a widget, decrements resource reference counts,
        and stops/cleans up resources if no longer needed.
        """
        with self.lock:
            widget_id = id(widget)
            if widget_id not in self.widget_subscriptions:
                logging.warning(f"Widget {widget_id} not found in subscriptions.")
                return

            resource_keys = self.widget_subscriptions.pop(widget_id)
            logging.info(f"Unsubscribing widget {widget_id}. Resources: {resource_keys}")

            for key in resource_keys:
                if isinstance(key, tuple): # Factory key
                    if key in self.factory_ref_counts:
                        self.factory_ref_counts[key] -= 1
                        logging.debug(f"Factory ref count for {key} decremented to {self.factory_ref_counts[key]}")
                        if self.factory_ref_counts[key] == 0:
                            logging.info(f"Removing CandleFactory for key {key} as ref count is zero.")
                            del self.factory_ref_counts[key]
                            # Remove the factory instance itself
                            if key in self.candle_factories:
                                # Clean up factory resources if necessary (e.g., unregister listeners)
                                factory = self.candle_factories[key]
                                factory.cleanup()
                                del self.candle_factories[key]
                            else:
                                logging.warning(f"Factory {key} not found in candle_factories dict during cleanup.")
                    else:
                         logging.warning(f"Factory key {key} not found in ref counts during unsubscribe.")

                elif isinstance(key, str): # Stream key
                    if key in self.stream_ref_counts:
                        self.stream_ref_counts[key] -= 1
                        logging.debug(f"Stream ref count for {key} decremented to {self.stream_ref_counts[key]}")
                        if self.stream_ref_counts[key] == 0:
                            logging.info(f"Stopping stream task for key {key} as ref count is zero.")
                            del self.stream_ref_counts[key]
                            # Clear the event first to signal the loop to stop
                            stop_event = self.stream_events.pop(key, None)
                            if stop_event:
                                stop_event.clear()
                            # Then cancel the task
                            self.stop_task(key) # stop_task now only cancels future
                    else:
                         logging.warning(f"Stream key {key} not found in ref counts during unsubscribe.")

    def _get_watch_trades_coro(self, exchange: str, symbol: str, stop_event: asyncio.Event):
        """Returns the coroutine for watching trades, passing the stop event."""
        async def wrapped_watch_trades():
            try:
                await self.data.watch_trades(exchange=exchange, symbol=symbol, stop_event=stop_event)
            except Exception as e:
                # Log specifics about the stream that failed
                logging.error(f"Error in watch_trades task for {exchange}/{symbol}: {e}", exc_info=True)
                # Optionally, attempt recovery or notify user
        return wrapped_watch_trades()

    def _get_watch_orderbook_coro(self, exchange: str, symbol: str, stop_event: asyncio.Event):
        """Returns the coroutine for watching orderbook, passing the stop event."""
        async def wrapped_watch_orderbook():
            try:
                await self.data.watch_orderbook(exchange=exchange, symbol=symbol, stop_event=stop_event)
            except Exception as e:
                # Log specifics about the stream that failed
                logging.error(f"Error in watch_orderbook task for {exchange}/{symbol}: {e}", exc_info=True)
                # Optionally, attempt recovery or notify user
        return wrapped_watch_orderbook()

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
                 # Emit directly instead of queuing
                 self._update_ui_with_candles(
                     exchange=exchange,
                     symbol=symbol,
                     timeframe=timeframe,
                     candles=candles_df,
                 )
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
        Stops a specific task by name by cancelling its Future.
        Relies on unsubscribe to clear the associated event for streams.
        """
        task_future = self.tasks.pop(name, None)
        if task_future:
            if not task_future.done():
                # Schedule cancellation in the event loop thread
                self.loop.call_soon_threadsafe(task_future.cancel)
                logging.info(f"Cancellation requested for task '{name}'.")
                # Note: Cancellation is requested, but the task might take time to actually stop.
                # We don't explicitly wait here to avoid blocking.
                # Consider adding a mechanism to await cancellation if needed.
            else:
                logging.info(f"Task '{name}' was already done, removed reference.")
                # Optionally handle results/exceptions if needed via task_future.result()
        else:
            logging.warning(f"Task '{name}' not found or already stopped.")

    def stop_all_tasks(self):
        """
        Stops all running tasks managed by the TaskManager.
        Clears stream events first.
        """
        logging.info("Stopping all tasks...")
        
        # Clear all stream events first
        with self.lock:
            stream_keys = list(self.stream_events.keys())
            logging.info(f"Clearing {len(stream_keys)} stream events.")
            for key in stream_keys:
                event = self.stream_events.pop(key, None)
                if event:
                    event.clear()
            self.stream_ref_counts.clear()

            # Clear factory references as well, assuming widgets are gone
            factory_keys = list(self.candle_factories.keys())
            logging.info(f"Cleaning up {len(factory_keys)} candle factories.")
            for key in factory_keys:
                 factory = self.candle_factories.pop(key, None)
                 if factory:
                     factory.cleanup()
            self.factory_ref_counts.clear()
            self.widget_subscriptions.clear() # Clear subscriptions

        # Cancel all asyncio tasks
        task_names = list(self.tasks.keys())
        logging.info(f"Requesting cancellation for {len(task_names)} tasks.")
        for name in task_names:
            self.stop_task(name) # Uses the modified stop_task which just cancels
            
        # Give tasks a moment to process cancellation if needed
        # This is a simple approach; more robust handling might involve `asyncio.gather`
        # with return_exceptions=True on the task futures, but that adds complexity
        # time.sleep(0.1) # Avoid blocking sleep if possible

        logging.info("All tasks stop requested.")

    def is_task_running(self, task_id):
        """Check if a task with the given ID is currently running (not done)."""
        task_future = self.tasks.get(task_id)
        return task_future is not None and not task_future.done()

    def _on_task_complete(self, name, task_future):
        """
        Callback function executed when an asyncio task completes.
        Handles results, errors, and potentially task cleanup.
        """
        if name not in self.tasks or self.tasks[name] != task_future:
            # Task might have been stopped and removed manually before completion
            logging.info(f"Completion callback for task '{name}', but it's no longer tracked or replaced. Ignoring.")
            return

        # Remove the task from the active dictionary as it's now complete
        # We keep the future object for inspection below
        del self.tasks[name] 

        try:
            # Check if the task was cancelled
            if task_future.cancelled():
                logging.info(f"Task '{name}' completed: Cancelled.")
                # Event should have been cleared by stop_task/unsubscribe
                # Remove event just in case it wasn't cleaned up properly elsewhere
                with self.lock:
                    if name in self.stream_events:
                        logging.warning(f"Task '{name}' cancelled, but stream event was still present. Cleaning up.")
                        del self.stream_events[name]
            else:
                # If not cancelled, check for exceptions
                exception = task_future.exception()
                if exception:
                    logging.error(f"Task '{name}' completed with error: {exception}", exc_info=exception)
                    # Perform any error handling specific to the task type if needed
                    # e.g., maybe try restarting the stream after a delay?
                    # TODO: Implement specific error handling based on task name/type
                else:
                    # Task completed successfully
                    result = task_future.result()
                    logging.info(f"Task '{name}' completed successfully.")
                    # Process result if necessary (though many background tasks might not return meaningful results)
                    # logging.debug(f"Task '{name}' result: {result}")

        except Exception as e:
            # Catch any unexpected error during the callback itself
            logging.error(f"Error in _on_task_complete for task '{name}': {e}", exc_info=True)
        finally:
            # Ensure event is removed if task finishes naturally (not cancelled) or errors out
            with self.lock:
                 if name in self.stream_events: 
                    logging.warning(f"Task '{name}' finished (error/success), but stream event was still present. Cleaning up.")
                    del self.stream_events[name]

    def cleanup(self):
        """
        Cleans up resources when the application is shutting down.
        Stops all tasks, closes async resources, and closes the event loop thread.
        """
        self.running = False # Signal processing loops to stop
        
        # Stop the data processing queue loop
        # await self.data_queue.join() # Wait for queue to empty (might block shutdown)
        # TODO: Consider a timeout for joining the queue or just cancel the processor task

        self.stop_all_tasks() # Ensure all tasks are stopped and events cleared
        
        # --- Close async resources BEFORE stopping the loop --- 
        if self.loop and self.loop.is_running() and self.sec_fetcher:
            try:
                logging.info("Closing SECDataFetcher resources...")
                close_coro = self.sec_fetcher.close()
                future = asyncio.run_coroutine_threadsafe(close_coro, self.loop)
                # Wait for the close operation to complete, with a timeout
                future.result(timeout=5) 
                logging.info("SECDataFetcher resources closed.")
            except asyncio.TimeoutError:
                logging.error("Timeout waiting for SECDataFetcher to close.")
            except Exception as e:
                logging.error(f"Error closing SECDataFetcher: {e}", exc_info=True)
        # Add other async resource cleanup here if needed
        # --- End async resource cleanup ---

        # No thread-pool executor anymore – left here for backward-compat documentation

        if self.loop and self.loop.is_running():
            logging.info("Stopping event loop...")
            # Use call_soon_threadsafe to stop the loop from the current thread
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        if self.thread and self.thread.is_alive():
            logging.info("Waiting for event loop thread to join...")
            self.thread.join(timeout=2) # Wait for the thread to finish
            if self.thread.is_alive():
                logging.warning("Event loop thread did not join cleanly.")

        logging.info("TaskManager cleanup complete.")

    def is_stream_running(self, stream_id: str) -> bool:
        """Checks if a stream task is running and its event is set."""
        task_running = self.is_task_running(stream_id)
        event_set = False
        with self.lock:
            event = self.stream_events.get(stream_id)
            if event:
                event_set = event.is_set()
        return task_running and event_set
