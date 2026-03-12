import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow

from sentinel.widgets.chart_widget import ChartDockWidget
from sentinel.widgets.chart_orderflow_widget import ChartOrderflowDockWidget
from sentinel.widgets.dom_widget import DomDockWidget
from sentinel.widgets.orderbook_widget import OrderbookDockWidget


LOGGER = logging.getLogger(__name__)

CONFIG_DIR = Path("config")
USER_WIDGETS_PATH = CONFIG_DIR / "user_widgets_qt.json"
FACTORY_WIDGETS_PATH = CONFIG_DIR / "factory_widgets_qt.json"

DEFAULT_WIDGETS: list[dict[str, Any]] = [
    {
        "instance_id": "chart_coinbase_btcusd_1m",
        "widget_type": "chart",
        "config": {"exchange": "coinbase", "symbol": "BTC/USD", "timeframe": "1m"},
    },
    {
        "instance_id": "dom_coinbase_btcusd",
        "widget_type": "dom",
        "config": {"exchange": "coinbase", "symbol": "BTC/USD", "levels": 16},
    },
    {
        "instance_id": "orderbook_coinbase_btcusd_depth",
        "widget_type": "orderbook",
        "config": {"exchange": "coinbase", "symbol": "BTC/USD"},
    },
]


class WidgetRegistry:
    def __init__(self, window: QMainWindow) -> None:
        self.window = window
        self.runtime = None
        self.docks: dict[str, QDockWidget] = {}
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def clear(self) -> None:
        for dock in list(self.docks.values()):
            try:
                dock.close()
            except Exception:
                pass
            self.window.removeDockWidget(dock)
            dock.deleteLater()
        self.docks.clear()

    def attach_runtime(self, runtime) -> None:
        self.runtime = runtime
        for dock in self.docks.values():
            setter = getattr(dock, "set_runtime", None)
            if callable(setter):
                setter(runtime)

    def add_placeholder(
        self,
        title: str,
        *,
        instance_id: str | None = None,
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea,
    ) -> str:
        if instance_id is None:
            instance_id = f"placeholder_{uuid4().hex[:8]}"

        if instance_id in self.docks:
            return instance_id

        dock = QDockWidget(title, self.window)
        dock.setObjectName(f"dock:{instance_id}")
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        label = QLabel(f"{title}\n\nPhase 1 placeholder", dock)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dock.setWidget(label)

        self.window.addDockWidget(area, dock)
        self.docks[instance_id] = dock
        return instance_id

    def add_chart(
        self,
        *,
        instance_id: str | None = None,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        timeframe: str = "1m",
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea,
    ) -> str:
        if instance_id is None:
            instance_id = f"chart_{uuid4().hex[:8]}"
        if instance_id in self.docks:
            return instance_id

        dock = ChartDockWidget(
            instance_id=instance_id,
            runtime=self.runtime,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
        )
        self.window.addDockWidget(area, dock)
        self.docks[instance_id] = dock
        return instance_id

    def add_chart_orderflow(
        self,
        *,
        instance_id: str | None = None,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        timeframe: str = "1m",
        tick_size: float = 0.01,
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea,
    ) -> str:
        if instance_id is None:
            instance_id = f"chart_orderflow_{uuid4().hex[:8]}"
        if instance_id in self.docks:
            return instance_id

        dock = ChartOrderflowDockWidget(
            instance_id=instance_id,
            runtime=self.runtime,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            price_precision=tick_size,
        )
        self.window.addDockWidget(area, dock)
        self.docks[instance_id] = dock
        return instance_id

    def add_orderbook(
        self,
        *,
        instance_id: str | None = None,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea,
    ) -> str:
        if instance_id is None:
            instance_id = f"orderbook_{uuid4().hex[:8]}"
        if instance_id in self.docks:
            return instance_id

        dock = OrderbookDockWidget(
            instance_id=instance_id,
            runtime=self.runtime,
            exchange=exchange,
            symbol=symbol,
        )
        self.window.addDockWidget(area, dock)
        self.docks[instance_id] = dock
        return instance_id

    def add_dom(
        self,
        *,
        instance_id: str | None = None,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        levels: int = 16,
        area: Qt.DockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea,
    ) -> str:
        if instance_id is None:
            instance_id = f"dom_{uuid4().hex[:8]}"
        if instance_id in self.docks:
            return instance_id

        dock = DomDockWidget(
            instance_id=instance_id,
            runtime=self.runtime,
            exchange=exchange,
            symbol=symbol,
            levels=levels,
        )
        self.window.addDockWidget(area, dock)
        self.docks[instance_id] = dock
        return instance_id

    def remove(self, instance_id: str) -> None:
        dock = self.docks.pop(instance_id, None)
        if dock is None:
            return
        self.window.removeDockWidget(dock)
        dock.deleteLater()

    def load_or_create_defaults(self) -> None:
        defs = self._load_definitions(USER_WIDGETS_PATH)
        if defs is None:
            defs = self._load_definitions(FACTORY_WIDGETS_PATH)
        if defs is None:
            defs = DEFAULT_WIDGETS

        for item in defs:
            config = item.get("config", {})
            widget_type = item.get("widget_type")
            instance_id = str(item["instance_id"])

            if widget_type == "chart":
                self.add_chart(
                    instance_id=instance_id,
                    exchange=str(config.get("exchange", "coinbase")),
                    symbol=str(config.get("symbol", "BTC/USD")),
                    timeframe=str(config.get("timeframe", "1m")),
                )
                continue
            if widget_type == "chart_orderflow":
                self.add_chart_orderflow(
                    instance_id=instance_id,
                    exchange=str(config.get("exchange", "coinbase")),
                    symbol=str(config.get("symbol", "BTC/USD")),
                    timeframe=str(config.get("timeframe", "1m")),
                    tick_size=float(config.get("tick_size", 0.01)),
                )
                continue
            if widget_type == "orderbook":
                self.add_orderbook(
                    instance_id=instance_id,
                    exchange=str(config.get("exchange", "coinbase")),
                    symbol=str(config.get("symbol", "BTC/USD")),
                )
                continue
            if widget_type == "dom":
                self.add_dom(
                    instance_id=instance_id,
                    exchange=str(config.get("exchange", "coinbase")),
                    symbol=str(config.get("symbol", "BTC/USD")),
                    levels=int(config.get("levels", 16)),
                )
                continue

            self.add_placeholder(
                title=str(config.get("title", "Placeholder")),
                instance_id=instance_id,
            )

        if not any(
            isinstance(dock, (ChartDockWidget, ChartOrderflowDockWidget))
            for dock in self.docks.values()
        ):
            LOGGER.warning(
                "Widget definitions did not include a chart; injecting default chart widget."
            )
            chart_instance_id = "chart_coinbase_btcusd_1m"
            if chart_instance_id in self.docks:
                chart_instance_id = None
            self.add_chart(
                instance_id=chart_instance_id,
                exchange="coinbase",
                symbol="BTC/USD",
                timeframe="1m",
            )

    def save_user_definitions(self) -> None:
        payload = []
        for instance_id, dock in self.docks.items():
            exporter = getattr(dock, "export_definition", None)
            if callable(exporter):
                payload.append(exporter())
                continue
            payload.append(
                {
                    "instance_id": instance_id,
                    "widget_type": "placeholder",
                    "config": {"title": dock.windowTitle()},
                }
            )
        USER_WIDGETS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOGGER.debug("Saved widget definitions to %s", USER_WIDGETS_PATH)

    def reset_user_definitions(self) -> None:
        if USER_WIDGETS_PATH.exists():
            USER_WIDGETS_PATH.unlink()
            LOGGER.info("Removed user widget definitions: %s", USER_WIDGETS_PATH)

    @staticmethod
    def _load_definitions(path: Path) -> list[dict[str, Any]] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return None
            return data
        except Exception as exc:
            LOGGER.warning("Failed reading widget definitions from %s: %s", path, exc)
            return None
