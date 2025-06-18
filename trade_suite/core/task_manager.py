import asyncio
import logging
import threading
from typing import Any, Dict, List, Set, Tuple, TYPE_CHECKING
from collections import defaultdict

from .data.candle_factory import CandleFactory
from .data.sec_api import SECDataFetcher
from .signals import Signals

from ..gui.stream_subscription import StreamSubscription

from ..gui.utils import (
    calculate_since,
    create_timed_popup,
)

if TYPE_CHECKING:
    from .data.data_source import Data


class TaskManager:
    def __init__(self, data: "Data", sec_fetcher: SECDataFetcher):
        self.data = data
        self.sec_fetcher = sec_fetcher
        self.tasks: Dict[str, asyncio.Task] = {}
        self.loop: asyncio.AbstractEventLoop = None
        self.thread: threading.Thread = None
        self.running = True

        # Centralized factory storage (keyed by (exchange, symbol, timeframe))
        self.candle_factories: Dict[Tuple[str, str, str], CandleFactory] = {}

        # Reference counting and subscription tracking
        self.stream_subscriptions: Dict[str, StreamSubscription] = {}
        self.factory_ref_counts: Dict[Tuple[str, str, str], int] = defaultdict(int)
        # Maps widget instance to a set of resource keys (stream or factory) it requires
        self.widget_subscriptions: Dict[Any, Set[str | Tuple[str, str, str]]] = (
            defaultdict(set)
        )

        # In-memory mapping of resource key to the widgets subscribed to it
        self.resource_to_widgets: Dict[
            str | Tuple[str, str, str], Set[Any]
        ] = defaultdict(set)

        # Lock for thread synchronization (primarily for accessing shared resources like factories/counts)
        self.lock = threading.Lock()

        # Event used to signal when the asyncio loop has been created
        self.loop_ready = threading.Event()

        # TaskManager always runs its own event loop in a separate thread.
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.loop_ready.wait() # Wait for the loop to be initialized

        # Now that the asyncio loop is ready, inform Data so it can emit
        # signals thread-safely without the intermediate queue.
        try:
            self.data.set_ui_loop(self.loop)
        except AttributeError:
            # Data class may not yet have the helper if running older version.
            logging.warning(
                "Data object lacks set_ui_loop – direct emit optimisation disabled."
            )

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
        self.loop_ready.set()

        # Run the event loop (no longer schedules a separate data-queue consumer)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

        logging.info("TaskManager event loop has stopped.")

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
        if task:  # Only store if task creation was successful
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
                return result, None  # Return result and no error
            except asyncio.CancelledError:
                logging.info(f"Task '{name}' was cancelled.")
                raise  # Re-raise CancelledError so asyncio handles it properly
            except Exception as e:
                logging.error(f"Error in task '{name}': {e}", exc_info=True)
                return None, e  # Return no result and the error

        task = asyncio.run_coroutine_threadsafe(wrapped_coro(), self.loop)
        return task

    def _get_resource_keys(
        self, requirements: dict
    ) -> List[str | Tuple[str, str, str]]:
        """Helper to determine resource keys from widget requirements."""
        keys = []
        req_type = requirements.get("type")
        exchange = requirements.get("exchange")
        symbol = requirements.get("symbol")
        timeframe = requirements.get("timeframe")

        if not exchange or not symbol:
            logging.warning(
                f"Missing exchange or symbol in requirements: {requirements}"
            )
            return keys

        if req_type == "candles":
            if not timeframe:
                logging.warning(
                    f"Missing timeframe for candles requirement: {requirements}"
                )
                return keys
            # Candles require a factory and the underlying trade stream
            factory_key = (exchange, symbol, timeframe)
            trade_stream_key = f"trades_{exchange}_{symbol}"
            keys.append(factory_key)
            keys.append(trade_stream_key)
        elif req_type == "trades":
            trade_stream_key = f"trades_{exchange}_{symbol}"
            keys.append(trade_stream_key)
        elif req_type == "orderbook":
            orderbook_stream_key = f"orderbook_{exchange}_{symbol}"
            keys.append(orderbook_stream_key)
        elif req_type == "ticker":
            ticker_stream_key = f"ticker_{exchange}_{symbol}"
            keys.append(ticker_stream_key)
        else:
            logging.warning(f"Unknown requirement type: {req_type}")

        return keys

    def subscribe(self, widget, requirements: dict):
        """
        Subscribes a widget to data based on requirements.
        Manages resource reference counting and starts/creates resources if needed.
        """
        with self.lock:  # Ensure thread safety when modifying counts/factories/tasks
            resource_keys = self._get_resource_keys(requirements)
            if not resource_keys:
                logging.error(
                    f"Could not determine resources for widget {widget} with requirements {requirements}"
                )
                return

            widget_id = id(widget)
            logging.info(
                f"Subscribing widget {widget_id} with requirements {requirements}. Resources: {resource_keys}"
            )
            self.widget_subscriptions[widget_id].update(resource_keys)

            for key in resource_keys:
                # Map the resource back to the widget instance
                self.resource_to_widgets[key].add(widget)

                if isinstance(key, tuple):  # Factory key
                    if self.factory_ref_counts.get(key, 0) == 0:
                        # First subscription for this factory, create it and fetch initial data
                        self._create_candle_factory_if_needed(key)
                    self.factory_ref_counts[key] += 1
                
                elif isinstance(key, str):  # Stream key
                    if key not in self.stream_subscriptions:
                        # First subscription for this stream, start it
                        self._start_stream_if_needed(key)

    def _create_candle_factory_if_needed(self, factory_key: Tuple[str, str, str]):
        """Creates and initializes a CandleFactory."""
        if factory_key in self.candle_factories:
            logging.warning(f"Attempted to create already existing CandleFactory for {factory_key}")
            return

        exchange, symbol, timeframe = factory_key
        logging.info(f"Creating new CandleFactory for key: {factory_key}")
        
        candle_factory = CandleFactory(
            exchange=exchange,
            symbol=symbol,
            timeframe_str=timeframe,
            emitter=self.data.emitter,
            task_manager=self,
            data=self.data,
        )
        self.candle_factories[factory_key] = candle_factory
        
        # Asynchronously fetch initial candles
        fetch_coro = self._fetch_initial_candles_for_factory(exchange, symbol, timeframe)
        self.start_task(f"initial_candles_{exchange}_{symbol}_{timeframe}", fetch_coro)

    def _start_stream_if_needed(self, stream_key: str):
        """Starts a data stream coroutine."""
        if stream_key in self.stream_subscriptions:
            logging.warning(f"Attempted to start already running stream for {stream_key}")
            return

        stop_event = asyncio.Event()
        coro = None
        if stream_key.startswith("trades_"):
            _, exchange, symbol = stream_key.split("_")
            coro = self._get_watch_trades_coro(exchange, symbol, stop_event)
        elif stream_key.startswith("orderbook_"):
            _, exchange, symbol = stream_key.split("_")
            coro = self._get_watch_orderbook_coro(exchange, symbol, stop_event)
        # Add other stream types here...

        if coro:
            logging.info(f"Starting new stream task for key: {stream_key}")
            task = asyncio.run_coroutine_threadsafe(coro, self.loop)
            # Store the task in the main tasks dictionary
            self.tasks[stream_key] = task
            # Store the subscription object with just the stop event
            self.stream_subscriptions[stream_key] = StreamSubscription(stop_event=stop_event)
        else:
            logging.warning(f"No coroutine found for stream key: {stream_key}")

    def unsubscribe(self, widget):
        """
        Unsubscribes a widget, decrements resource reference counts,
        and stops/cleans up resources if no longer needed.
        """
        with self.lock:
            widget_id = id(widget)
            if widget_id not in self.widget_subscriptions:
                logging.warning(f"Attempted to unsubscribe a widget ({widget_id}) that was not subscribed.")
                return

            logging.info(f"Unsubscribing widget {widget_id}")
            resource_keys = self.widget_subscriptions.pop(widget_id, set())

            for key in resource_keys:
                # Remove widget from the resource's set of subscribers
                if key in self.resource_to_widgets:
                    self.resource_to_widgets[key].discard(widget)

                if isinstance(key, tuple):  # Factory key
                    self.factory_ref_counts[key] -= 1
                    logging.debug(f"Factory ref count for {key} decremented to {self.factory_ref_counts[key]}")
                    if self.factory_ref_counts[key] == 0:
                        logging.info(f"Reference count for factory {key} is zero. Removing factory.")
                        del self.candle_factories[key]
                        del self.factory_ref_counts[key]
                
                elif isinstance(key, str):  # Stream key
                    # If no more widgets are listening to this resource, stop the stream
                    if not self.resource_to_widgets.get(key):
                        self._stop_stream(key)

    def _stop_stream(self, stream_key: str):
        """Stops a stream and cleans up its resources."""
        logging.info(f"Stopping stream for key: {stream_key}")
        subscription = self.stream_subscriptions.pop(stream_key, None)
        if subscription:
            self.loop.call_soon_threadsafe(subscription.stop_event.set)
            # The task will be cancelled within the coroutine, but we also remove it from our tracking
            self.tasks.pop(stream_key, None)
            
        # Also clean up the resource_to_widgets entry
        if stream_key in self.resource_to_widgets:
            del self.resource_to_widgets[stream_key]

    def _get_watch_trades_coro(self, exchange: str, symbol: str, stop_event: asyncio.Event):
        """Returns the coroutine for watching trades, passing the stop event."""
        async def wrapped_watch_trades():
            try:
                # The data source's watch method handles the loop and stop event
                await self.data.watch_trades(exchange=exchange, symbol=symbol, stop_event=stop_event)
            except Exception as e:
                logging.error(f"Error in watch_trades task for {exchange}/{symbol}: {e}", exc_info=True)
        return wrapped_watch_trades()

    def _get_watch_orderbook_coro(self, exchange: str, symbol: str, stop_event: asyncio.Event):
        """Returns the coroutine for watching orderbook, passing the stop event."""
        async def wrapped_watch_orderbook():
            try:
                # The data source's watch method handles the loop and stop event
                await self.data.watch_orderbook(exchange=exchange, symbol=symbol, stop_event=stop_event)
            except Exception as e:
                logging.error(f"Error in watch_orderbook task for {exchange}/{symbol}: {e}", exc_info=True)
        return wrapped_watch_orderbook()

    async def _fetch_initial_candles_for_factory(
        self, exchange: str, symbol: str, timeframe: str
    ):
        """Fetches initial candles and puts them onto the data queue."""
        logging.info(f"Fetching initial candles for {exchange}/{symbol}/{timeframe}")

        # Get the actual CCXT exchange object from Data
        ccxt_exchange = self.data.exchange_list.get(exchange)
        if not ccxt_exchange:
            logging.error(
                f"CCXT exchange object not found for '{exchange}' in TaskManager. Cannot fetch initial candles."
            )
            return

        try:
            # Determine 'since' based on timeframe, similar to old logic
            since = calculate_since(ccxt_exchange, timeframe, num_candles=1000)

            # Fetch candles using data source method (assuming it's adapted or suitable)
            # Assuming fetch_candles now returns the dataframe directly
            # And does NOT interact with the queue or signals itself.
            candles_dict = await self.data.fetch_candles(  # Renamed to candles_dict
                exchanges=[exchange],
                symbols=[symbol],
                timeframes=[timeframe],
                since=since,
                write_to_db=False,  # Or based on config
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
                logging.error(
                    f"Could not find CandleFactory instance for {factory_key} to set initial data."
                )

            if candles_df is not None and not candles_df.empty:
                logging.info(
                    f"Fetched {len(candles_df)} initial candles for {exchange}/{symbol}/{timeframe}. Putting onto queue."
                )
                # Emit directly instead of queuing
                self._update_ui_with_candles(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=candles_df,
                )
            else:
                logging.warning(
                    f"No initial candles returned for {exchange}/{symbol}/{timeframe}."
                )

        except Exception as e:
            logging.error(
                f"Error fetching initial candles for {exchange}/{symbol}/{timeframe}: {e}",
                exc_info=True,
            )

    def run_task_until_complete(self, coro):
        """
        The run_task_until_complete function runs a coroutine until it completes.
        It creates a future and runs it in the event loop, blocking the calling
        thread until the result is available.

        :param self: Access the class instance
        :param coro: Specify the coroutine to run
        :return: The result of the coroutine
        """
        if threading.current_thread() is self.thread:
            # If we are already in the event loop's thread, we can't block.
            # This is an advanced case, but good to handle.
            # Consider if this should raise an error instead.
            logging.warning("run_task_until_complete called from within the event loop thread. This can cause deadlocks.")
            task = self.loop.create_task(coro)
            return task # Return the task, can't await it here.

        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        # This blocks the calling thread (e.g., the main GUI thread)
        # until the coroutine is done executing in the event loop thread.
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

        # Log start of task to avoid blocking UI thread with prints
        logging.info(f"Loading: {message}")

        def on_task_complete(fut):
            # This function will be called when the future completes
            try:
                # Get the result of the future
                result = fut.result()
                logging.info(f"Loading complete: {message}")
                return result
            except Exception as e:
                # Log the error
                logging.error(f"Error in task: {e}")
                create_timed_popup(str(e), 5)
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

        # Clear all stream subscriptions first
        with self.lock:
            stream_keys = list(self.stream_subscriptions.keys())
            logging.info(f"Clearing {len(stream_keys)} stream events.")
            for key in stream_keys:
                sub = self.stream_subscriptions.pop(key, None)
                if sub:
                    sub.stop_event.set()
            # Clear reference counts

            # Clear factory references as well, assuming widgets are gone
            factory_keys = list(self.candle_factories.keys())
            logging.info(f"Cleaning up {len(factory_keys)} candle factories.")
            for key in factory_keys:
                factory = self.candle_factories.pop(key, None)
                if factory:
                    factory.cleanup()
            self.factory_ref_counts.clear()
            self.widget_subscriptions.clear()  # Clear subscriptions

        # Cancel all asyncio tasks
        task_names = list(self.tasks.keys())
        logging.info(f"Requesting cancellation for {len(task_names)} tasks.")
        for name in task_names:
            self.stop_task(name)  # Uses the modified stop_task which just cancels

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
            logging.info(
                f"Completion callback for task '{name}', but it's no longer tracked or replaced. Ignoring."
            )
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
                    self.stream_subscriptions.pop(name, None)
            else:
                # If not cancelled, check for exceptions
                exception = task_future.exception()
                if exception:
                    logging.error(
                        f"Task '{name}' completed with error: {exception}",
                        exc_info=exception,
                    )
                    # Perform any error handling specific to the task type if needed
                    # e.g., maybe try restarting the stream after a delay?
                    # TODO: Implement specific error handling based on task name/type
                else:
                    # Task completed successfully
                    task_future.result()
                    logging.info(f"Task '{name}' completed successfully.")
                    # Process result if necessary (though many background tasks might not return meaningful results)
                    # logging.debug(f"Task '{name}' result: {result}")

        except Exception as e:
            # Catch any unexpected error during the callback itself
            logging.error(
                f"Error in _on_task_complete for task '{name}': {e}", exc_info=True
            )
        finally:
            # Ensure event is removed if task finishes naturally (not cancelled) or errors out
            with self.lock:
                self.stream_subscriptions.pop(name, None)

    def cleanup(self):
        """
        Cleans up resources when the application is shutting down.
        Stops all tasks, closes async resources, and closes the event loop thread.
        """
        logging.info("TaskManager cleanup initiated.")
        self.running = False

        # Stop all running tasks and clear subscriptions
        self.stop_all_tasks()

        # --- Close async resources BEFORE stopping the loop ---
        if self.loop and self.loop.is_running() and self.sec_fetcher:
            try:
                logging.info("Closing SECDataFetcher resources...")
                close_coro = self.sec_fetcher.close()
                future = asyncio.run_coroutine_threadsafe(close_coro, self.loop)
                future.result(timeout=5)
                logging.info("SECDataFetcher resources closed.")
            except asyncio.TimeoutError:
                logging.error("Timeout waiting for SECDataFetcher to close.")
            except Exception as e:
                logging.error(f"Error closing SECDataFetcher: {e}", exc_info=True)
        
        # Stop the event loop itself
        if self.loop and self.loop.is_running():
            logging.info("Stopping event loop...")
            self.loop.call_soon_threadsafe(self.loop.stop)

        # Wait for the event loop thread to finish
        if self.thread and self.thread.is_alive():
            logging.info("Waiting for event loop thread to join...")
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logging.warning("Event loop thread did not join cleanly.")

        logging.info("TaskManager cleanup complete.")

    async def stop_all_tasks_async(self):
        """The async part of stopping all tasks. Cancels and gathers them."""
        logging.info("Stopping all tasks asynchronously...")
        # Your existing logic to cancel tasks, but now it's a native coroutine
        # This simplifies things as you don't need run_coroutine_threadsafe here

        # Stop stream tasks
        stream_keys_to_stop = list(self.stream_subscriptions.keys())
        for key in stream_keys_to_stop:
            if key in self.tasks and not self.tasks[key].done():
                logging.info(f"Stopping stream task for key {key} async.")
                self.tasks[key].cancel()
                try:
                    await self.tasks[key]
                except asyncio.CancelledError:
                    pass # Expected
        
        # Cleanup factories
        factory_keys_to_clean = list(self.candle_factories.keys())
        for key in factory_keys_to_clean:
            factory = self.candle_factories.get(key)
            if factory:
                factory.cleanup()
        
        self.tasks.clear()
        self.candle_factories.clear()
        self.stream_subscriptions.clear()
        self.factory_ref_counts.clear()
        self.widget_subscriptions.clear()

        logging.info("All async tasks have been requested to stop.")

    def is_stream_running(self, stream_id: str) -> bool:
        """Checks if a stream task is running and its event is set."""
        with self.lock:
            sub = self.stream_subscriptions.get(stream_id)
            # A stream is running if it has a subscription object
            # and that object's ref_count > 0
            if sub and sub.ref_count > 0:
                is_subscribed = True

        task_running = self.tasks.get(stream_id) is not None and not self.tasks[stream_id].done()
        return task_running and is_subscribed
