from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPicture
from PySide6.QtWidgets import QDockWidget, QSplitter, QVBoxLayout, QWidget

from trade_suite.core.signals import Signals


LOGGER = logging.getLogger(__name__)


class TimestampAxis(pg.AxisItem):
    def __init__(self, orientation: str = "bottom") -> None:
        super().__init__(orientation=orientation)
        self.timestamps: list[float] = []

    def set_timestamps(self, timestamps: list[float]) -> None:
        self.timestamps = timestamps

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        labels: list[str] = []
        for raw in values:
            idx = int(round(raw))
            if idx < 0 or idx >= len(self.timestamps):
                labels.append("")
                continue
            ts = self.timestamps[idx]
            try:
                dt = datetime.fromtimestamp(ts)
                labels.append(dt.strftime("%m-%d %H:%M"))
            except Exception:
                labels.append("")
        return labels


class CandlestickItem(pg.GraphicsObject):
    def __init__(self) -> None:
        super().__init__()
        self._picture = QPicture()
        self._x: list[int] = []
        self._o: list[float] = []
        self._h: list[float] = []
        self._l: list[float] = []
        self._c: list[float] = []
        self._body_factor = 0.55

    def set_data(
        self,
        x: list[int],
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ) -> None:
        self._x = x
        self._o = opens
        self._h = highs
        self._l = lows
        self._c = closes
        self._generate_picture()
        self.update()

    def _generate_picture(self) -> None:
        self._picture = QPicture()
        painter = QPainter(self._picture)
        up_pen = QPen(QColor(86, 230, 160))
        dn_pen = QPen(QColor(245, 110, 125))
        up_brush = QBrush(QColor(35, 200, 110))
        dn_brush = QBrush(QColor(220, 70, 85))

        width = self._auto_body_width()
        half = width * 0.5
        for i, open_, high, low, close in zip(self._x, self._o, self._h, self._l, self._c):
            rising = close >= open_
            top = max(open_, close)
            bottom = min(open_, close)
            height = top - bottom
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(up_brush if rising else dn_brush)
            if height > 0:
                painter.drawRect(QRectF(i - half, bottom, width, height))
            else:
                painter.setPen(up_pen if rising else dn_pen)
                painter.drawLine(QPointF(i - half, bottom), QPointF(i + half, bottom))
                painter.setPen(Qt.PenStyle.NoPen)
            painter.setPen(up_pen if rising else dn_pen)
            painter.drawLine(QPointF(i, low), QPointF(i, high))

        painter.end()

    def _auto_body_width(self) -> float:
        if len(self._x) < 2:
            return self._body_factor
        diffs = [self._x[idx] - self._x[idx - 1] for idx in range(1, len(self._x))]
        min_step = min(d for d in diffs if d > 0) if any(d > 0 for d in diffs) else 1
        return float(min_step) * self._body_factor

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self):
        return self._picture.boundingRect()


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
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.max_points = max_points
        self.show_ema = show_ema
        self.runtime = None
        self._subscribed = False
        self._handlers_registered = False

        self.timestamps: list[float] = []
        self.opens: list[float] = []
        self.highs: list[float] = []
        self.lows: list[float] = []
        self.closes: list[float] = []
        self.volumes: list[float] = []
        self._dirty = False
        self._did_initial_fit = False

        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.price_x_axis = TimestampAxis("bottom")
        self.volume_x_axis = TimestampAxis("bottom")

        self.price_plot = pg.PlotWidget(axisItems={"bottom": self.price_x_axis})
        self.price_plot.setBackground("#060a11")
        self.price_plot.showGrid(x=True, y=True, alpha=0.25)
        self.price_plot.setMouseEnabled(y=True, x=True)
        self.price_plot.setLabel("right", "Price")
        self.price_plot.showAxis("right")
        self.price_plot.hideAxis("left")
        self.price_plot.getAxis("right").setStyle(tickTextOffset=6)

        self.volume_plot = pg.PlotWidget(axisItems={"bottom": self.volume_x_axis})
        self.volume_plot.setBackground("#060a11")
        self.volume_plot.showGrid(x=True, y=True, alpha=0.2)
        self.volume_plot.setMouseEnabled(y=True, x=True)
        self.volume_plot.setLabel("right", "Volume")
        self.volume_plot.showAxis("right")
        self.volume_plot.hideAxis("left")
        self.volume_plot.setXLink(self.price_plot)
        self.price_plot.getViewBox().enableAutoRange(x=False, y=True)
        self.volume_plot.getViewBox().enableAutoRange(x=False, y=True)

        self.candle_item = CandlestickItem()
        self.price_plot.addItem(self.candle_item)
        self.volume_item: pg.BarGraphItem | None = None
        self.ema_item: pg.PlotDataItem | None = None

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.price_plot)
        splitter.addWidget(self.volume_plot)
        splitter.setSizes([700, 220])
        layout.addWidget(splitter)
        self.setWidget(body)

        interval_ms = max(int(1000 / max(fps, 1)), 16)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(interval_ms)
        self._render_timer.timeout.connect(self._render_if_dirty)
        self._render_timer.start()

        self.set_runtime(runtime)

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

    def set_runtime(self, runtime) -> None:
        self.runtime = runtime
        if runtime is None or runtime.core is None:
            return
        self._register_handlers()
        self._subscribe()

    def _register_handlers(self) -> None:
        if self._handlers_registered or self.runtime is None or self.runtime.core is None:
            return
        emitter = self.runtime.core.emitter
        emitter.register(Signals.NEW_CANDLES, self._on_new_candles)
        emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        self._handlers_registered = True

    def _unregister_handlers(self) -> None:
        if not self._handlers_registered or self.runtime is None or self.runtime.core is None:
            return
        emitter = self.runtime.core.emitter
        try:
            emitter.unregister(Signals.NEW_CANDLES, self._on_new_candles)
            emitter.unregister(Signals.UPDATED_CANDLES, self._on_updated_candles)
        except Exception:
            pass
        self._handlers_registered = False

    def _subscribe(self) -> None:
        if self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        self.runtime.core.subscribe_to_candles(
            exchange=self.exchange,
            symbol=self.symbol,
            timeframe=self.timeframe,
            widget_instance=self,
        )
        self._subscribed = True
        LOGGER.info("Chart subscribed: %s/%s/%s", self.exchange, self.symbol, self.timeframe)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("Chart unsubscribe failed: %s", exc)
        self._subscribed = False

    def _on_new_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):
        if exchange != self.exchange or symbol != self.symbol or timeframe != self.timeframe:
            return
        self._replace_from_dataframe(candles)

    def _on_updated_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):
        if exchange != self.exchange or symbol != self.symbol or timeframe != self.timeframe:
            return
        if candles is None or candles.empty:
            return
        self._merge_update(candles)

    def _replace_from_dataframe(self, data: pd.DataFrame) -> None:
        if data is None or data.empty:
            return
        dates = self._normalize_dates_seconds(data["dates"])
        self.timestamps = dates[-self.max_points :]
        self.opens = data["opens"].astype(float).tolist()[-self.max_points :]
        self.highs = data["highs"].astype(float).tolist()[-self.max_points :]
        self.lows = data["lows"].astype(float).tolist()[-self.max_points :]
        self.closes = data["closes"].astype(float).tolist()[-self.max_points :]
        self.volumes = data["volumes"].astype(float).tolist()[-self.max_points :]
        self._did_initial_fit = False
        self._dirty = True

    def _merge_update(self, data: pd.DataFrame) -> None:
        frame = data.reset_index(drop=True)
        if frame.empty:
            return
        row = frame.iloc[-1]
        ts = self._normalize_dates_seconds(pd.Series([row["dates"]]))[0]
        o = float(row["opens"])
        h = float(row["highs"])
        l = float(row["lows"])
        c = float(row["closes"])
        v = float(row["volumes"])

        if self.timestamps and abs(self.timestamps[-1] - ts) < 1e-9:
            self.opens[-1] = o
            self.highs[-1] = h
            self.lows[-1] = l
            self.closes[-1] = c
            self.volumes[-1] = v
        elif not self.timestamps or ts > self.timestamps[-1]:
            self.timestamps.append(ts)
            self.opens.append(o)
            self.highs.append(h)
            self.lows.append(l)
            self.closes.append(c)
            self.volumes.append(v)
            if len(self.timestamps) > self.max_points:
                self.timestamps = self.timestamps[-self.max_points :]
                self.opens = self.opens[-self.max_points :]
                self.highs = self.highs[-self.max_points :]
                self.lows = self.lows[-self.max_points :]
                self.closes = self.closes[-self.max_points :]
                self.volumes = self.volumes[-self.max_points :]
        else:
            return
        self._dirty = True

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.timestamps:
            return
        self._dirty = False

        x = list(range(len(self.timestamps)))
        self.price_x_axis.set_timestamps(self.timestamps)
        self.volume_x_axis.set_timestamps(self.timestamps)
        self.candle_item.set_data(x, self.opens, self.highs, self.lows, self.closes)

        if self.volume_item is not None:
            self.volume_plot.removeItem(self.volume_item)
        brushes = [
            QBrush(QColor(35, 200, 110, 180)) if c >= o else QBrush(QColor(220, 70, 85, 180))
            for o, c in zip(self.opens, self.closes)
        ]
        self.volume_item = pg.BarGraphItem(x=x, height=self.volumes, width=0.8, brushes=brushes)
        self.volume_plot.addItem(self.volume_item)

        if self.show_ema:
            if self.ema_item is not None:
                self.price_plot.removeItem(self.ema_item)
            ema = pd.Series(self.closes).ewm(span=20, adjust=False).mean().tolist()
            self.ema_item = self.price_plot.plot(x=x, y=ema, pen=pg.mkPen(color=(100, 180, 255), width=1.0))

        if x and not self._did_initial_fit:
            window = min(180, max(60, len(x)))
            self.price_plot.setXRange(max(0, x[-1] - window), x[-1] + 2, padding=0.0)
            self._did_initial_fit = True

    @staticmethod
    def _normalize_dates_seconds(series: pd.Series) -> list[float]:
        if pd.api.types.is_datetime64_any_dtype(series):
            numeric = series.astype("int64") // 1_000_000_000
            return numeric.astype(float).tolist()
        numeric = pd.to_numeric(series, errors="coerce").fillna(0)
        if not numeric.empty and float(numeric.max()) > 2_000_000_000:
            numeric = numeric / 1000.0
        return numeric.astype(float).tolist()

    def closeEvent(self, event):  # noqa: N802
        self._render_timer.stop()
        self._unsubscribe()
        self._unregister_handlers()
        super().closeEvent(event)
