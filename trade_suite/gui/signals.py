from enum import Enum, auto
import logging
import queue
import threading
from typing import Callable
import dearpygui.dearpygui as dpg


class Signals(Enum):
    CREATE_EXCHANGE_TAB = auto()
    CREATE_TAB = auto()
    NEW_CANDLES = auto()
    NEW_TRADE = auto()
    ORDER_BOOK_UPDATE = auto()
    ORDERBOOK_VISIBILITY_CHANGED = auto()
    SYMBOL_CHANGED = auto()
    TIMEFRAME_CHANGED = auto()
    TRADE_STAT_UPDATE = auto()
    VIEWPORT_RESIZED = auto()
    UPDATED_CANDLES = auto()


class SignalEmitter:
    def __init__(self) -> None:
        self._callbacks = {}
        self._queue = queue.Queue()
        self._main_thread_id = threading.get_ident()

    def register(self, signal: Signals, callback: Callable):
        """
        Register a callback function for a given signal. The callback will be called when the signal is emitted.

        Args:
            signal (Signals): The signal to register the callback for.
            callback (Callable): The callback function to be called when the signal is emitted.

        Raises:
            ValueError: If the signal is not a member of the Signals enum.
        """
        if not isinstance(signal, Signals):
            raise ValueError("signal must be an instance of Signals enum")

        if signal not in self._callbacks:
            self._callbacks[signal] = []
        self._callbacks[signal].append(callback)

    def emit(self, signal: Signals, *args, **kwargs):
        """
        Emit a signal. If called from the main thread, execute callbacks directly.
        If called from another thread, queue the signal to be processed by the main thread.

        Args:
            signal (Signals): The signal to emit.
            *args: Variable length argument list to be passed to the callbacks.
            **kwargs: Arbitrary keyword arguments to be passed to the callbacks.

        Raises:
            ValueError: If the signal is not a member of the Signals enum.
        """
        if not isinstance(signal, Signals):
            raise ValueError("signal must be an instance of Signals enum")

        if threading.get_ident() == self._main_thread_id:
            self._execute_callbacks(signal, args, kwargs)
        else:
            self._queue.put((signal, args, kwargs))

    def _execute_callbacks(self, signal: Signals, args, kwargs):
        """ Safely executes callbacks for a given signal. """
        callbacks = self._callbacks.get(signal, [])
        logging.debug(f"[SignalQueue] Executing {len(callbacks)} callbacks for {signal.name}")
        for callback in callbacks:
            try:
                logging.debug(f"[SignalQueue] Calling: {callback.__name__} for {signal.name}")
                callback(*args, **kwargs)
            except Exception as e:
                # Log the exception and the callback that caused it
                logging.error(f"Error in callback {callback.__name__} for signal {signal.name}: {e}", exc_info=True)

    def process_signal_queue(self, sender=None, app_data=None, user_data=None):
        """
        Process signals queued from background threads. This should be called
        regularly by the main GUI thread (e.g., via a frame callback).
        The sender, app_data, user_data arguments are ignored but needed for dpg frame callback compatibility.
        """
        # Log entry to this function periodically (not every frame to avoid log spam)
        if dpg.get_frame_count() % 60 == 0:  # Log roughly once per second at 60fps
            logging.debug(f"[SignalQueue] Processing queue at frame {dpg.get_frame_count()}")
        
        processed_count = 0
        while not self._queue.empty():
            try:
                signal, args, kwargs = self._queue.get_nowait()
                logging.debug(f"[SignalQueue] Dequeued signal: {signal.name}")
                processed_count += 1
                self._execute_callbacks(signal, args, kwargs)
            except queue.Empty:
                # Should not happen with the while loop condition, but good practice
                break
            except Exception as e:
                logging.error(f"Error processing signal queue: {e}", exc_info=True)
        
        if processed_count > 0:
            logging.debug(f"[SignalQueue] Processed {processed_count} signals this frame.")

    def unregister(self, signal: Signals, callback: Callable):
        """
        Unregister a callback function from a given signal.

        Args:
            signal (Signals): The signal to unregister the callback from.
            callback (Callable): The callback function to be unregistered.

        Raises:
            ValueError: If the signal is not a member of the Signals enum.
        """
        if not isinstance(signal, Signals):
            raise ValueError("signal must be an instance of Signals enum")

        if signal in self._callbacks:
            self._callbacks[signal].remove(callback)
