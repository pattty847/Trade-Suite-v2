from enum import Enum, auto

class Signals(Enum):
    SELECT_EXCHANGE = auto()
    EXCHANGE_SELECTED = auto()
    CREATE_CHART = auto()
    CREATE_CHART_FOR_SYMBOL = auto()
    NEW_TRADE_DATA = auto()

class SignalEmitter:
    def __init__(self) -> None:
        self._callbacks = {}

    def register(self, signal: Signals, callback):
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
        Emit a signal, causing all registered callbacks for that signal to be called.

        Args:
            signal (Signals): The signal to emit.
            *args: Variable length argument list to be passed to the callbacks.
            **kwargs: Arbitrary keyword arguments to be passed to the callbacks.

        Raises:
            ValueError: If the signal is not a member of the Signals enum.
        """
        if not isinstance(signal, Signals):
            raise ValueError("signal must be an instance of Signals enum")

        for callback in self._callbacks.get(signal, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"Error in callback for {signal}: {e}")

    def unregister(self, signal: Signals, callback):
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
