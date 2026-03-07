from __future__ import annotations

import bisect
import logging
from typing import Any

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPicture
from PySide6.QtWidgets import QDockWidget, QLabel, QVBoxLayout, QWidget

from sentinel.core.signals import Signals


LOGGER = logging.getLogger(__name__)

_AXIS_PEN = pg.mkPen(color="#1e2d3f", width=1)
_TICK_PEN = pg.mkPen(color="#546d8a")
_TICK_FONT = QFont("Menlo, Consolas, monospace")
_TICK_FONT.setStyleHint(QFont.StyleHint.Monospace)
_TICK_FONT.setPointSize(8)
_LABEL_CSS = {"color": "#3f5a76", "font-size": "10pt"}

# Volume overlay: fraction of price-plot height reserved for bars
_VOL_FRACTION = 0.18
_CROSSHAIR_PEN = pg.mkPen(color="#2a4060", width=1, style=Qt.PenStyle.DashLine)

# Muted TV-style palette
_UP_COLOR = QColor(38, 166, 154)      # teal-green
_DN_COLOR = QColor(239, 83, 80)       # muted red
_UP_HEX = "#26a69a"
_DN_HEX = "#ef5350"


def _style_pg_plot(plot: pg.PlotWidget) -> None:
    """Apply consistent dark-theme styling to a pyqtgraph PlotWidget."""
    for axis_name in ("left", "right", "top", "bottom"):
        ax = plot.getAxis(axis_name)
        ax.setPen(_AXIS_PEN)
        ax.setTextPen(_TICK_PEN)
        ax.setTickFont(_TICK_FONT)
        ax.setStyle(tickLength=-5)
    plot.getViewBox().setBorder(pg.mkPen("#1a2535", width=1))


class CandlestickItem(pg.GraphicsObject):
    def __init__(self) -> None:
        super().__init__()
        self._picture = QPicture()
        self._x: list[float] = []
        self._o: list[float] = []
        self._h: list[float] = []
        self._l: list[float] = []
        self._c: list[float] = []
        self._body_width = 1.0

    def set_data(
        self,
        x: list[float],
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        *,
        body_width: float,
    ) -> None:
        self._x = x
        self._o = opens
        self._h = highs
        self._l = lows
        self._c = closes
        self._body_width = max(float(body_width), 1.0)
        self._generate_picture()
        self.update()

    def _generate_picture(self) -> None:
        self._picture = QPicture()
        painter = QPainter(self._picture)
        up_pen = QPen(_UP_COLOR)
        dn_pen = QPen(_DN_COLOR)
        up_pen.setWidthF(1.0)
        dn_pen.setWidthF(1.0)
        up_brush = QBrush(_UP_COLOR)
        dn_brush = QBrush(_DN_COLOR)
        no_pen = QPen(Qt.PenStyle.NoPen)

        width = self._body_width
        half = width * 0.5
        for i, open_, high, low, close in zip(self._x, self._o, self._h, self._l, self._c):
            rising = close >= open_
            top = max(open_, close)
            bottom = min(open_, close)
            painter.setPen(up_pen if rising else dn_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(i, low), QPointF(i, high))
            painter.setPen(no_pen)
            painter.setBrush(up_brush if rising else dn_brush)
            height = top - bottom
            if height > 0:
                painter.drawRect(QRectF(i - half, bottom, width, height))
            else:
                painter.drawRect(QRectF(i - half, bottom, width, 1.0))
        painter.end()

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
        )

        # ── Price plot ────────────────────────────────────────────────────────
        self.price_x_axis = pg.DateAxisItem(orientation="bottom")
        self.price_plot = pg.PlotWidget(axisItems={"bottom": self.price_x_axis})
        self.price_plot.setBackground("#060a11")
        self.price_plot.showGrid(x=True, y=True, alpha=0.15)
        self.price_plot.setMouseEnabled(y=True, x=True)
        self.price_plot.setLabel("right", "Price", **_LABEL_CSS)
        self.price_plot.showAxis("right")
        self.price_plot.hideAxis("left")
        self.price_plot.getAxis("right").setStyle(tickTextOffset=6)
        _style_pg_plot(self.price_plot)
        self.price_plot.getViewBox().enableAutoRange(x=False, y=False)

        # ── Volume overlay ViewBox (bottom ~18% of price plot area) ──────────
        self.vb_vol = pg.ViewBox(enableMenu=False)
        self.price_plot.scene().addItem(self.vb_vol)
        self.vb_vol.setXLink(self.price_plot.getViewBox())
        self.vb_vol.setMouseEnabled(x=False, y=False)
        # Keep below the price ViewBox so it doesn't intercept mouse events
        self.vb_vol.setZValue(self.price_plot.getViewBox().zValue() - 1)
        self.price_plot.getViewBox().sigResized.connect(self._update_vol_geometry)

        # ── Crosshair ─────────────────────────────────────────────────────────
        self._v_line = pg.InfiniteLine(angle=90, movable=False, pen=_CROSSHAIR_PEN)
        self._h_line = pg.InfiniteLine(angle=0, movable=False, pen=_CROSSHAIR_PEN)
        self._v_line.hide()
        self._h_line.hide()
        self.price_plot.addItem(self._v_line, ignoreBounds=True)
        self.price_plot.addItem(self._h_line, ignoreBounds=True)

        # ── Floating current-price tag (right axis) ───────────────────────────
        self._price_line: pg.InfiniteLine | None = None
        self._price_line_up: bool | None = None   # tracks direction for color changes
        self._current_candle_width: float = 60.0

        # ── Data items ────────────────────────────────────────────────────────
        self.candle_item = CandlestickItem()
        self.price_plot.addItem(self.candle_item)
        self.volume_item: pg.BarGraphItem | None = None
        self.ema_item: pg.PlotDataItem | None = None

        # ── Layout ────────────────────────────────────────────────────────────
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.price_plot)
        self.setWidget(body)

        # ── OHLCV overlay label (top-left, transparent, mouse-passthrough) ────
        _mono = QFont()
        _mono.setStyleHint(QFont.StyleHint.Monospace)
        _mono.setPointSize(9)
        self._ohlcv_label = QLabel("", body)
        self._ohlcv_label.setFont(_mono)
        self._ohlcv_label.setStyleSheet("color: #5a7a9a; background: transparent; padding: 2px 8px;")
        self._ohlcv_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ohlcv_label.move(8, 4)
        self._ohlcv_label.hide()

        # ── Mouse proxy for hover/crosshair ──────────────────────────────────
        self._mouse_proxy = pg.SignalProxy(
            self.price_plot.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )

        # Defer volume geometry until scene is fully laid out
        QTimer.singleShot(0, self._update_vol_geometry)

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

    # ── Volume geometry ───────────────────────────────────────────────────────

    def _update_vol_geometry(self) -> None:
        geom = self.price_plot.getViewBox().sceneBoundingRect()
        if geom.height() == 0:
            return
        vol_h = geom.height() * _VOL_FRACTION
        self.vb_vol.setGeometry(
            geom.x(),
            geom.y() + geom.height() - vol_h,
            geom.width(),
            vol_h,
        )

    # ── Current-price floating tag ────────────────────────────────────────────

    def _update_price_line(self) -> None:
        if not self.closes:
            return
        price = self.closes[-1]
        is_up = len(self.closes) < 2 or price >= self.closes[-2]
        hex_color = _UP_HEX if is_up else _DN_HEX

        if is_up != self._price_line_up:
            # Recreate with new color when direction flips
            if self._price_line is not None:
                self.price_plot.removeItem(self._price_line)
            self._price_line = pg.InfiniteLine(
                angle=0, movable=False,
                pen=pg.mkPen(hex_color, width=1, style=Qt.PenStyle.DashLine),
                label="{value:.2f}",
                labelOpts={"position": 1.0, "color": "#ffffff", "fill": pg.mkBrush(hex_color)},
            )
            self.price_plot.addItem(self._price_line, ignoreBounds=True)
            self._price_line_up = is_up

        self._price_line.setPos(price)

    # ── Mouse hover / crosshair ───────────────────────────────────────────────

    def _on_mouse_moved(self, evt) -> None:
        pos = evt[0]
        if not self.price_plot.sceneBoundingRect().contains(pos):
            self._v_line.hide()
            self._h_line.hide()
            self._ohlcv_label.hide()
            return

        self._h_line.show()

        vb = self.price_plot.getViewBox()
        mp = vb.mapSceneToView(pos)
        self._h_line.setPos(mp.y())

        if not self.timestamps:
            return

        x = mp.x()
        idx = bisect.bisect_left(self.timestamps, x)
        if idx >= len(self.timestamps):
            idx = len(self.timestamps) - 1
        elif idx > 0 and (x - self.timestamps[idx - 1]) < (self.timestamps[idx] - x):
            idx -= 1

        # Only show vertical snap + OHLCV when inside a candle's column
        if abs(x - self.timestamps[idx]) > self._current_candle_width * 0.5:
            self._v_line.hide()
            self._ohlcv_label.hide()
            return

        self._v_line.show()
        self._v_line.setPos(self.timestamps[idx])

        o, h, l, c, v = (
            self.opens[idx], self.highs[idx], self.lows[idx],
            self.closes[idx], self.volumes[idx],
        )
        delta = c - o
        pct = (delta / o * 100) if o != 0 else 0.0
        color = _UP_HEX if c >= o else _DN_HEX

        self._ohlcv_label.setText(
            f"O {o:.2f}  H {h:.2f}  L {l:.2f}  C {c:.2f}  "
            f"{delta:+.2f} ({pct:+.2f}%)  Vol: {v:.0f}"
        )
        self._ohlcv_label.setStyleSheet(
            f"color: {color}; background: transparent; padding: 2px 8px;"
        )
        self._ohlcv_label.adjustSize()
        self._ohlcv_label.show()

    # ── Subscription management ───────────────────────────────────────────────

    def change_subscription(self, exchange: str, symbol: str, timeframe: str) -> None:
        """Switch to a different exchange/symbol/timeframe without recreating the widget."""
        if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:
            return
        self._unsubscribe()
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.setWindowTitle(f"Chart - {exchange.upper()} {symbol} ({timeframe})")

        # Clear data
        self.timestamps.clear()
        self.opens.clear()
        self.highs.clear()
        self.lows.clear()
        self.closes.clear()
        self.volumes.clear()
        self._did_initial_fit = False
        self._dirty = False

        # Clear rendered items
        self.candle_item.set_data([], [], [], [], [], body_width=1.0)
        if self.volume_item is not None:
            self.vb_vol.removeItem(self.volume_item)
            self.volume_item = None
        if self.ema_item is not None:
            self.price_plot.removeItem(self.ema_item)
            self.ema_item = None
        if self._price_line is not None:
            self.price_plot.removeItem(self._price_line)
            self._price_line = None
            self._price_line_up = None

        self._ohlcv_label.hide()
        self._v_line.hide()
        self._h_line.hide()

        self._subscribe()
        LOGGER.debug("Chart resubscribed: %s/%s/%s", exchange, symbol, timeframe)

    # ── Runtime wiring ────────────────────────────────────────────────────────

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
        LOGGER.debug("Chart subscribed: %s/%s/%s", self.exchange, self.symbol, self.timeframe)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("Chart unsubscribe failed: %s", exc)
        self._subscribed = False

    # ── Data ingestion ────────────────────────────────────────────────────────

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
        df = pd.DataFrame({
            "dates": dates,
            "opens": data["opens"].astype(float).tolist(),
            "highs": data["highs"].astype(float).tolist(),
            "lows": data["lows"].astype(float).tolist(),
            "closes": data["closes"].astype(float).tolist(),
            "volumes": data["volumes"].astype(float).tolist(),
        })
        df = df.drop_duplicates(subset=["dates"], keep="last").sort_values("dates")
        n = min(len(df), self.max_points)
        tail = df.tail(n)
        self.timestamps = tail["dates"].astype(float).tolist()
        self.opens = tail["opens"].tolist()
        self.highs = tail["highs"].tolist()
        self.lows = tail["lows"].tolist()
        self.closes = tail["closes"].tolist()
        self.volumes = tail["volumes"].tolist()
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

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.timestamps:
            return
        self._dirty = False

        x = self.timestamps
        candle_width = self._infer_candle_width_seconds()
        self._current_candle_width = candle_width
        self.candle_item.set_data(
            x, self.opens, self.highs, self.lows, self.closes,
            body_width=candle_width * 0.72,
        )
        self._update_price_line()

        # Volume bars in the overlay ViewBox — explicit pen=None to suppress
        # pyqtgraph's default foreground pen overriding the per-bar brush colors.
        if self.volume_item is not None:
            self.vb_vol.removeItem(self.volume_item)
        brushes = [
            QBrush(QColor(38, 166, 154, 140)) if c >= o else QBrush(QColor(239, 83, 80, 140))
            for o, c in zip(self.opens, self.closes)
        ]
        self.volume_item = pg.BarGraphItem(
            x=x,
            height=self.volumes,
            width=candle_width * 0.72,
            brushes=brushes,
            pen=pg.mkPen(None),
        )
        self.vb_vol.addItem(self.volume_item)
        self.vb_vol.enableAutoRange(pg.ViewBox.YAxis, True)

        if self.show_ema:
            if self.ema_item is not None:
                self.price_plot.removeItem(self.ema_item)
            ema = pd.Series(self.closes).ewm(span=20, adjust=False).mean().tolist()
            self.ema_item = self.price_plot.plot(x=x, y=ema, pen=pg.mkPen(color=(100, 180, 255), width=1.0))

        if x and not self._did_initial_fit:
            self._fit_initial_view()
            self._did_initial_fit = True

    def _fit_initial_view(self) -> None:
        if not self.timestamps:
            return
        candle_span = self._infer_candle_width_seconds()
        window_count = min(180, max(60, len(self.timestamps)))
        start_idx = max(0, len(self.timestamps) - window_count)
        visible_timestamps = self.timestamps[start_idx:]
        visible_highs = self.highs[start_idx:]
        visible_lows = self.lows[start_idx:]
        if not visible_timestamps or not visible_highs or not visible_lows:
            return

        x_min = visible_timestamps[0] - candle_span
        x_max = visible_timestamps[-1] + (2.0 * candle_span)
        price_min = min(visible_lows)
        price_max = max(visible_highs)
        price_pad = max((price_max - price_min) * 0.05, 1e-9)

        self.price_plot.setXRange(x_min, x_max, padding=0.0)
        self.price_plot.setYRange(price_min - price_pad, price_max + price_pad, padding=0.0)
        self._update_vol_geometry()

    def _infer_candle_width_seconds(self) -> float:
        if len(self.timestamps) >= 2:
            diffs = [
                float(self.timestamps[idx] - self.timestamps[idx - 1])
                for idx in range(1, len(self.timestamps))
                if self.timestamps[idx] > self.timestamps[idx - 1]
            ]
            if diffs:
                return max(min(diffs), 1.0)
        return float(_timeframe_to_seconds(self.timeframe))

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


def _timeframe_to_seconds(value: str) -> int:
    raw = (value or "").strip().lower()
    if not raw:
        return 60
    unit = raw[-1]
    try:
        amount = int(raw[:-1]) if unit.isalpha() else int(raw)
    except ValueError:
        return 60
    if not unit.isalpha():
        return max(amount * 60, 1)
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }
    return max(amount * multipliers.get(unit, 60), 1)
