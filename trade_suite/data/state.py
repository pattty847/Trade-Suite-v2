import threading

class SignalEmitterTwo:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self, callback):
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback):
        with self._lock:
            self._subscribers.remove(callback)

    def emit(self, *args, **kwargs):
        with self._lock:
            for subscriber in self._subscribers:
                subscriber(*args, **kwargs)

class StateManager:
    def __init__(self):
        self._emitter = SignalEmitterTwo()
        self._state = {}
        self._lock = threading.Lock()

    def subscribe(self, callback):
        self._emitter.subscribe(callback)

    def unsubscribe(self, callback):
        self._emitter.unsubscribe(callback)

    def get_state(self):
        with self._lock:
            return self._state.copy()

    def set_state(self, new_state):
        with self._lock:
            self._state.update(new_state)
            self._emitter.emit(self._state)

if __name__ == "__main__":
    def print_state(state):
        print(state)

    state_manager = StateManager()
    state_manager.subscribe(print_state)

    state_manager.set_state({"foo": "bar"})
    state_manager.set_state({"baz": 42})

    state_manager.unsubscribe(print_state)
    state_manager.set_state({"qux": True})