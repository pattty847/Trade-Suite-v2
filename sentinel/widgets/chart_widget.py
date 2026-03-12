from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDockWidget, QVBoxLayout, QWidget

from sentinel.widgets.chart_toolbar import ChartToolbar
from sentinel.widgets.chart_pane import ChartPane


class ChartDockWidget(QDockWidget):
    def __init__(
        self,
        *,
        instance_id: str,
        runtime,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        timeframe: str = "1m",
        max_points: int = 1000,
        fps: int = 15,
        show_ema: bool = False,
        chart_mode: str = "candles",
        show_bubbles: bool = False,
    ) -> None:
        super().__init__(f"Chart - {exchange.upper()} {symbol} ({timeframe})")
        self.instance_id = instance_id
        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self.chart_pane = ChartPane(
            runtime=runtime,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            max_points=max_points,
            fps=fps,
            show_ema=show_ema,
            show_price_axis=True,
        )
        self.chart_pane.set_chart_mode(chart_mode)
        self.chart_pane.set_bubbles_enabled(show_bubbles)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbar = ChartToolbar(
            symbol=symbol,
            timeframe=timeframe,
            mode=chart_mode,
            bubbles_enabled=show_bubbles,
        )
        self.toolbar.symbol_changed.connect(self._on_symbol_changed)
        self.toolbar.timeframe_changed.connect(self._on_timeframe_changed)
        self.toolbar.mode_changed.connect(self._on_mode_changed)
        self.toolbar.bubbles_changed.connect(self._on_bubbles_changed)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.chart_pane, 1)
        self.setWidget(body)

    @property
    def exchange(self) -> str:
        return self.chart_pane.exchange

    @property
    def symbol(self) -> str:
        return self.chart_pane.symbol

    @property
    def timeframe(self) -> str:
        return self.chart_pane.timeframe

    @property
    def max_points(self) -> int:
        return self.chart_pane.max_points

    @property
    def show_ema(self) -> bool:
        return self.chart_pane.show_ema

    @property
    def chart_mode(self) -> str:
        return self.chart_pane.chart_mode()

    @property
    def show_bubbles(self) -> bool:
        return self.chart_pane.bubbles_enabled()

    def export_definition(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "widget_type": "chart",
            "config": {
                "exchange": self.exchange,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "max_points": self.max_points,
                "show_ema": self.show_ema,
                "chart_mode": self.chart_mode,
                "show_bubbles": self.show_bubbles,
            },
        }

    def change_subscription(self, exchange: str, symbol: str, timeframe: str) -> None:
        self.chart_pane.change_subscription(exchange, symbol, timeframe)
        self.toolbar.set_symbol(symbol)
        self.toolbar.set_timeframe(timeframe)
        self.setWindowTitle(f"Chart - {exchange.upper()} {symbol} ({timeframe})")

    def set_runtime(self, runtime) -> None:
        self.chart_pane.set_runtime(runtime)

    def _on_symbol_changed(self, symbol: str) -> None:
        self.change_subscription(self.exchange, symbol, self.timeframe)

    def _on_timeframe_changed(self, timeframe: str) -> None:
        self.change_subscription(self.exchange, self.symbol, timeframe)

    def _on_mode_changed(self, mode: str) -> None:
        self.chart_pane.set_chart_mode(mode)

    def _on_bubbles_changed(self, enabled: bool) -> None:
        self.chart_pane.set_bubbles_enabled(enabled)

    def closeEvent(self, event):  # noqa: N802
        self.chart_pane.shutdown()
        super().closeEvent(event)
