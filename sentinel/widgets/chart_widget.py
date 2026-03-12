from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDockWidget

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
        self.setWidget(self.chart_pane)

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
            },
        }

    def change_subscription(self, exchange: str, symbol: str, timeframe: str) -> None:
        self.chart_pane.change_subscription(exchange, symbol, timeframe)
        self.setWindowTitle(f"Chart - {exchange.upper()} {symbol} ({timeframe})")

    def set_runtime(self, runtime) -> None:
        self.chart_pane.set_runtime(runtime)

    def closeEvent(self, event):  # noqa: N802
        self.chart_pane.shutdown()
        super().closeEvent(event)
