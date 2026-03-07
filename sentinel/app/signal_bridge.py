import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from sentinel.core.signals import Signals


LOGGER = logging.getLogger(__name__)


class SentinelSignalBridge(QObject):
    """Qt signal bridge for non-hot-path runtime events."""

    task_success = Signal(dict)
    task_error = Signal(dict)
    widget_closed = Signal(dict)
    status = Signal(str)

    def __init__(self, emitter) -> None:
        super().__init__()
        self.emitter = emitter
        self._registered = False

    def register(self) -> None:
        if self._registered:
            return
        self.emitter.register(Signals.TASK_SUCCESS, self._on_task_success)
        self.emitter.register(Signals.TASK_ERROR, self._on_task_error)
        self.emitter.register(Signals.WIDGET_CLOSED, self._on_widget_closed)
        self._registered = True
        LOGGER.debug("SentinelSignalBridge registered non-hot-path callbacks.")

    def _on_task_success(self, **kwargs: Any) -> None:
        self.task_success.emit(dict(kwargs))

    def _on_task_error(self, **kwargs: Any) -> None:
        self.task_error.emit(dict(kwargs))

    def _on_widget_closed(self, **kwargs: Any) -> None:
        self.widget_closed.emit(dict(kwargs))
