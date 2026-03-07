import logging
import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from sentinel import __version__
from sentinel.app.main_window import SentinelMainWindow
from sentinel.app.runtime import SentinelRuntime


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
    )


async def _run_app(app: QApplication, runtime: SentinelRuntime, window: SentinelMainWindow) -> int:
    quit_event = asyncio.Event()
    app.aboutToQuit.connect(quit_event.set)

    await runtime.start()
    await quit_event.wait()
    await runtime.shutdown()
    return 0


def main() -> int:
    _setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Sentinel")
    app.setApplicationVersion(__version__)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    runtime = SentinelRuntime(loop=loop, exchanges=["coinbase"])
    window = SentinelMainWindow(app_version=__version__, runtime=runtime)
    window.show()

    with loop:
        return loop.run_until_complete(_run_app(app, runtime, window))


if __name__ == "__main__":
    raise SystemExit(main())
