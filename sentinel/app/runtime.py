import asyncio
import logging

from PySide6.QtCore import QObject, Signal

from sentinel.app.signal_bridge import SentinelSignalBridge
from sentinel.core.facade import CoreServicesFacade


LOGGER = logging.getLogger(__name__)


class SentinelRuntime(QObject):
    """Phase 2 runtime coordinator for qasync-driven lifecycle."""

    status_changed = Signal(str)
    runtime_error = Signal(str)
    started = Signal()
    stopped = Signal()

    def __init__(self, loop: asyncio.AbstractEventLoop, exchanges: list[str] | None = None) -> None:
        super().__init__()
        self.loop = loop
        self.exchanges = exchanges or ["coinbase"]
        self.core: CoreServicesFacade | None = None
        self.bridge: SentinelSignalBridge | None = None
        self._started = False
        self._shutting_down = False

    async def start(self) -> None:
        if self._started:
            return

        self.status_changed.emit("Starting core services...")
        self.core = CoreServicesFacade(
            force_public=True,
            task_mode="external",
            loop=self.loop,
        )
        self.bridge = SentinelSignalBridge(self.core.emitter)
        self.bridge.register()
        self.bridge.task_error.connect(self._on_task_error)
        self.bridge.task_success.connect(self._on_task_success)

        try:
            await self.core.start_async(self.exchanges)
        except Exception as exc:
            message = f"Core startup failed: {exc}"
            self.runtime_error.emit(message)
            self.status_changed.emit(message)
            LOGGER.exception(message)
            raise

        self._started = True
        self.status_changed.emit(f"Connected ({', '.join(self.exchanges)})")
        self.started.emit()
        LOGGER.info("Sentinel runtime started.")

    async def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.status_changed.emit("Shutting down...")

        if self.core is not None:
            await self.core.aclose()
            self.core = None

        self._started = False
        self.status_changed.emit("Stopped")
        self.stopped.emit()
        LOGGER.info("Sentinel runtime shutdown complete.")

    def _on_task_error(self, payload: dict) -> None:
        task_name = payload.get("task_name", "unknown_task")
        err = payload.get("error", "unknown_error")
        message = f"Task error: {task_name} ({err})"
        self.runtime_error.emit(message)
        self.status_changed.emit(message)
        LOGGER.error(message)

    def _on_task_success(self, payload: dict) -> None:
        task_name = payload.get("task_name")
        if task_name:
            LOGGER.debug("Task success: %s", task_name)
