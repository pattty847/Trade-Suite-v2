from enum import Enum, auto
import logging
import queue
import threading
from typing import Callable
from collections import deque
from functools import partial
import asyncio
import inspect


class Signals(Enum):
    # ── Live market data ────────────────────────────────────────────
    # NEW_CANDLES      → (exchange: str, symbol: str, timeframe: str, candles: DataFrame)
    # UPDATED_CANDLES  → same shape as NEW_CANDLES (last bar updated)
    # NEW_TRADE        → (exchange: str, trade: dict)   ccxt trade dict
    # ORDER_BOOK_UPDATE→ (exchange: str, orderbook: dict)  {bids, asks, symbol}
    # NEW_TICKER_DATA  → (exchange: str, symbol: str, ticker: dict)
    # TRADE_STAT_UPDATE→ (exchange: str, symbol: str, stats: dict)
    NEW_CANDLES = auto()
    UPDATED_CANDLES = auto()
    NEW_TRADE = auto()
    ORDER_BOOK_UPDATE = auto()
    NEW_TICKER_DATA = auto()
    TRADE_STAT_UPDATE = auto()

    # ── Widget / task lifecycle ──────────────────────────────────────
    # WIDGET_CLOSED → (widget_id: str)
    # TASK_SUCCESS  → (task_name: str, result: Any)
    # TASK_ERROR    → (task_name: str, error: Exception)
    WIDGET_CLOSED = auto()
    TASK_SUCCESS = auto()
    TASK_ERROR = auto()

    # ── Reserved / future use ────────────────────────────────────────
    # Kept for forward compatibility; not yet wired to any widget.
    CREATE_EXCHANGE_TAB = auto()
    CREATE_TAB = auto()
    NEW_CHART_REQUESTED = auto()
    NEW_ORDERBOOK_REQUESTED = auto()
    NEW_TRADING_PANEL_REQUESTED = auto()
    NEW_PRICE_LEVEL_REQUESTED = auto()
    ORDERBOOK_VISIBILITY_CHANGED = auto()
    SYMBOL_CHANGED = auto()
    TIMEFRAME_CHANGED = auto()
    VIEWPORT_RESIZED = auto()
    FETCH_OHLCV = auto()
    SEC_FILINGS_UPDATE = auto()
    SEC_INSIDER_TX_UPDATE = auto()
    SEC_FINANCIALS_UPDATE = auto()
    SEC_DATA_FETCH_ERROR = auto()
    NEW_SEC_FILING_VIEWER_REQUESTED = auto()


class SignalEmitter:
    def __init__(self) -> None:
        self._callbacks = {}
        self._queue = queue.Queue()
        self._main_thread_id = threading.get_ident()
        self.loop: asyncio.AbstractEventLoop = None

        # --- Object pool for small payload dictionaries to reduce GC churn ---
        # We keep a fixed-size deque; when we need a fresh dict we try to re-use one
        # instead of allocating a brand-new object.  The pool size is kept modest
        # (1024) so memory usage stays predictable even during heavy bursts.
        self._pool: "deque[dict]" = deque(maxlen=1024)

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the asyncio event loop for scheduling async callbacks."""
        self.loop = loop

    # ------------------------------------------------------------------
    # Public helpers for borrowing & recycling small payload dicts
    # ------------------------------------------------------------------
    def borrow_payload(self) -> dict:
        """Borrow a pre-allocated dict from the internal pool (or create one).

        Intended for high-frequency emitters that wish to avoid creating a new
        small dictionary on every call.  Always remember to *recycle* the dict
        once the signal has been processed to keep the pool effective.
        """
        try:
            payload = self._pool.pop()
            payload.clear()  # ensure stale keys are gone
            return payload
        except IndexError:
            return {}

    def recycle_payload(self, payload: dict):
        """Return a payload dict to the pool for re-use."""
        if isinstance(payload, dict):
            payload.clear()
            self._pool.append(payload)

    # ------------------------------------------------------------------
    # Thread-safe emission helper – avoids the queue polling model when a
    # reference to the main-thread asyncio loop is available.
    # ------------------------------------------------------------------
    def emit_threadsafe(self, loop, signal: Signals, *args, **kwargs):
        """Emit *signal* from a background thread using *loop.call_soon_threadsafe*.

        The *loop* argument should be the *main-thread* asyncio event loop.  If
        called from that same thread we simply fall back to the regular emit.
        """
        if threading.get_ident() == self._main_thread_id:
            self.emit(signal, *args, **kwargs)
        else:
            # We capture *signal*, *args* and *kwargs* by value here so they are
            # safe to use once scheduled on the other thread.  Since
            # ``call_soon_threadsafe`` only forwards *positional* arguments to
            # the callback we must wrap the call to preserve keyword args.
            loop.call_soon_threadsafe(partial(self.emit, signal, *args, **kwargs))

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
        """Safely execute all callbacks registered for *signal*."""
        callbacks = self._callbacks.get(signal, [])
        logging.debug("[SignalQueue] Executing %d callbacks for %s", len(callbacks), signal.name)
        for callback in callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    if self.loop:
                        asyncio.run_coroutine_threadsafe(callback(*args, **kwargs), self.loop)
                    else:
                        logging.warning(
                            "Async callback %s for signal %s has no event loop. Call set_loop() first.",
                            callback.__name__,
                            signal.name,
                        )
                else:
                    logging.debug("[SignalQueue] Calling %s for %s", callback.__name__, signal.name)
                    callback(*args, **kwargs)
            except Exception as exc:
                logging.error(
                    "Error in callback %s for signal %s: %s",
                    callback.__name__,
                    signal.name,
                    exc,
                    exc_info=True,
                )

    def process_signal_queue(self) -> int:
        """Drain the cross-thread signal queue on the main GUI thread.

        Returns the number of signals processed.  Call this periodically
        from any Qt timer or event handler running on the main thread.
        """
        processed_count = 0
        while not self._queue.empty():
            try:
                signal, args, kwargs = self._queue.get_nowait()
                logging.debug("[SignalQueue] Dequeued signal: %s", signal.name)
                processed_count += 1
                self._execute_callbacks(signal, args, kwargs)
            except queue.Empty:
                break
            except Exception as exc:
                logging.error("Error processing signal queue: %s", exc, exc_info=True)
        return processed_count
    

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
