from __future__ import annotations

import bisect
import logging
import math
from collections import deque
from typing import Any

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPicture
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from sentinel.analysis.cvd_processor import CandleCVDProcessor
from sentinel.app.theme import Colors, pg_label_css, qcolor
from sentinel.core.signals import Signals


LOGGER = logging.getLogger(__name__)

_AXIS_PEN = pg.mkPen(color=Colors.AXIS_PEN, width=1)
_TICK_PEN = pg.mkPen(color=Colors.TICK_PEN)
_TICK_FONT = QFont("Menlo, Consolas, monospace")
_TICK_FONT.setStyleHint(QFont.StyleHint.Monospace)
_TICK_FONT.setPointSize(8)
_LABEL_CSS = pg_label_css()
_VOL_FRACTION = 0.18
_CVD_ZERO_PEN = pg.mkPen(color=Colors.BORDER_PLOT, width=1, style=Qt.PenStyle.DashLine)
_CROSSHAIR_PEN = pg.mkPen(color=Colors.BORDER_PLOT, width=1, style=Qt.PenStyle.DashLine)

_UP_COLOR = qcolor(Colors.UP)
_DN_COLOR = qcolor(Colors.DOWN)
_UP_HEX = Colors.UP
_DN_HEX = Colors.DOWN

def _fmt_price(value: float) -> str:
    """Format a price with adaptive decimal places based on magnitude."""
    if value == 0:
        return "0"
    abs_v = abs(value)
    if abs_v >= 10_000:
        return f"{value:,.0f}"
    if abs_v >= 1_000:
        return f"{value:,.1f}"
    if abs_v >= 10:
        return f"{value:.2f}"
    if abs_v >= 0.1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def _fmt_vol(value: float) -> str:
    """Format a volume with K/M suffix."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    if value >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}"


_VPVR_N_BINS = 60                                      # price buckets across visible Y range
_VPVR_WIDTH_FRAC = 0.22                                # fraction of visible X span for max bar
_VPVR_VAL_BRUSH = QBrush(QColor(80, 130, 200, 55))    # volume-at-level colour
_VPVR_VAL_PEN = QPen(QColor(80, 130, 200, 80))
_VPVR_POC_BRUSH = QBrush(QColor(255, 186, 0, 120))    # point-of-control highlight
_VPVR_POC_PEN = QPen(QColor(255, 186, 0, 200))


def _style_pg_plot(plot: pg.PlotWidget) -> None:
    for axis_name in ("left", "right", "top", "bottom"):
        ax = plot.getAxis(axis_name)
        ax.setPen(_AXIS_PEN)
        ax.setTextPen(_TICK_PEN)
        ax.setTickFont(_TICK_FONT)
        ax.setStyle(tickLength=-5)
    plot.getViewBox().setBorder(pg.mkPen(Colors.BORDER_SUB, width=1))


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
        self._body_width = max(float(body_width), 1e-3)
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


class VpvrItem(pg.GraphicsObject):
    """Horizontal volume-profile (VPVR) overlay drawn in data-space coordinates.

    Each bin is a translucent horizontal bar anchored to the right edge of the
    visible X range and extending leftward proportionally to its volume share.
    The bin with the highest volume (Point of Control) is highlighted in amber.
    """

    def __init__(self) -> None:
        super().__init__()
        # List of (price_center, volume, is_poc) tuples.
        self._bins: list[tuple[float, float, bool]] = []
        self._x_right: float = 0.0      # right edge anchor (rightmost visible timestamp)
        self._max_bar_w: float = 1.0    # width of the full bar in data coords
        self._bin_h: float = 1.0        # height of each bin in price units
        self._picture = QPicture()

    def set_profile(
        self,
        bins: list[tuple[float, float]],   # (price_center, volume) pairs
        x_right: float,                     # timestamp of the rightmost visible bar
        max_bar_width: float,               # data-coord width for the maximum bar
        bin_height: float,                  # price height of each bin
    ) -> None:
        self._x_right = x_right
        self._max_bar_w = max(max_bar_width, 1e-9)
        self._bin_h = max(bin_height, 1e-9)
        if not bins:
            self._bins = []
        else:
            max_vol = max(v for _, v in bins)
            if max_vol <= 0:
                self._bins = []
            else:
                poc_price = max(bins, key=lambda b: b[1])[0]
                self._bins = [(p, v / max_vol, p == poc_price) for p, v in bins]
        self._generate_picture()
        self.update()

    def _generate_picture(self) -> None:
        self._picture = QPicture()
        if not self._bins:
            return
        painter = QPainter(self._picture)
        half_h = self._bin_h * 0.5
        for price, norm_vol, is_poc in self._bins:
            bar_w = norm_vol * self._max_bar_w
            if bar_w < 1e-12:
                continue
            rect = QRectF(self._x_right - bar_w, price - half_h, bar_w, self._bin_h)
            if is_poc:
                painter.setPen(_VPVR_POC_PEN)
                painter.setBrush(_VPVR_POC_BRUSH)
            else:
                painter.setPen(_VPVR_VAL_PEN)
                painter.setBrush(_VPVR_VAL_BRUSH)
            painter.drawRect(rect)
        painter.end()

    def paint(self, painter, *args) -> None:
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:
        # Return a rect that covers the drawn area — pyqtgraph uses this for
        # scene culling.  We deliberately inflate it a bit so partial redraws
        # do not clip the bars.
        br = self._picture.boundingRect()
        if br.isNull():
            return QRectF()
        return br.adjusted(-1, -1, 1, 1)


class ChartPane(QWidget):
    visible_price_range_changed = Signal(float, float)
    last_price_changed = Signal(float)

    def __init__(
        self,
        *,
        runtime,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        timeframe: str = "1m",
        max_points: int = 1000,
        fps: int = 15,
        show_ema: bool = False,
        show_price_axis: bool = True,
        body_width_fraction: float = 0.72,
    ) -> None:
        super().__init__()
        self.exchange = exchange
        self.symbol = symbol
        self._body_width_fraction = max(0.1, min(0.98, body_width_fraction))
        self.timeframe = timeframe
        self.max_points = max_points
        self.show_ema = show_ema
        self.show_price_axis = show_price_axis
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
        
        self._chart_mode = "candles"
        self._show_bubbles = False
        self._trades_cache = deque(maxlen=1000)
        self._show_cvd = False
        self._cvd_processor = CandleCVDProcessor(timeframe)
        self._cvd_bar_item: pg.BarGraphItem | None = None
        self._show_vpvr = False

        self.price_x_axis = pg.DateAxisItem(orientation="bottom")
        self.price_plot = pg.PlotWidget(axisItems={"bottom": self.price_x_axis})
        self.price_plot.setBackground(Colors.BG_CANVAS)
        self.price_plot.showGrid(x=True, y=True, alpha=Colors.GRID_ALPHA)
        self.price_plot.setMouseEnabled(y=True, x=True)
        _style_pg_plot(self.price_plot)
        self.price_plot.getViewBox().enableAutoRange(x=False, y=False)
        self.price_plot.getViewBox().sigResized.connect(self._update_vol_geometry)
        self.price_plot.getViewBox().sigYRangeChanged.connect(self._on_y_range_changed)
        self.price_plot.getViewBox().sigXRangeChanged.connect(self._on_x_range_changed)

        if self.show_price_axis:
            self.price_plot.setLabel("right", "Price", **_LABEL_CSS)
            self.price_plot.showAxis("right")
            self.price_plot.hideAxis("left")
            self.price_plot.getAxis("right").setStyle(tickTextOffset=6)
        else:
            self.price_plot.hideAxis("right")
            self.price_plot.hideAxis("left")

        self.vb_vol = pg.ViewBox(enableMenu=False)
        self.price_plot.scene().addItem(self.vb_vol)
        self.vb_vol.setXLink(self.price_plot.getViewBox())
        self.vb_vol.setMouseEnabled(x=False, y=False)
        self.vb_vol.setZValue(self.price_plot.getViewBox().zValue() - 1)

        self._v_line = pg.InfiniteLine(angle=90, movable=False, pen=_CROSSHAIR_PEN)
        self._h_line = pg.InfiniteLine(angle=0, movable=False, pen=_CROSSHAIR_PEN)
        self._v_line.hide()
        self._h_line.hide()
        self.price_plot.addItem(self._v_line, ignoreBounds=True)
        self.price_plot.addItem(self._h_line, ignoreBounds=True)

        self._price_line: pg.InfiniteLine | None = None
        self._price_line_up: bool | None = None
        self._current_candle_width: float = 60.0
        self._last_price_line_value: float | None = None

        self.candle_item = CandlestickItem()
        self.ha_item = CandlestickItem()
        self.line_item = pg.PlotDataItem(pen=pg.mkPen(color="#2196f3", width=1.5))

        # Equity-mode items (pg.BarGraphItem bodies + paired-segment wicks).
        # Set when load_equity_bars() is called; cleared in clear_data().
        self._eq_wicks_up: pg.PlotDataItem | None = None
        self._eq_wicks_dn: pg.PlotDataItem | None = None
        self._eq_body_up: pg.BarGraphItem | None = None
        self._eq_body_dn: pg.BarGraphItem | None = None

        # Bubbles plot overlay
        self.bubbles_item = pg.ScatterPlotItem(
            size=10, 
            pen=pg.mkPen(None), 
            brush=pg.mkBrush(255, 255, 255, 120),
            hoverable=True
        )
        self.bubbles_item.setZValue(10)
        
        # VPVR overlay — added before candles so it renders behind them.
        self._vpvr_item = VpvrItem()
        self._vpvr_item.hide()
        self._vpvr_item.setZValue(-1)
        self.price_plot.addItem(self._vpvr_item)

        self.price_plot.addItem(self.candle_item)
        self.price_plot.addItem(self.ha_item)
        self.price_plot.addItem(self.line_item)
        self.price_plot.addItem(self.bubbles_item)
        
        self.volume_item: pg.BarGraphItem | None = None
        self.ema_item: pg.PlotDataItem | None = None

        self.cvd_x_axis = pg.DateAxisItem(orientation="bottom")
        self.cvd_plot = pg.PlotWidget(axisItems={"bottom": self.cvd_x_axis})
        self.cvd_plot.setBackground(Colors.BG_CANVAS)
        self.cvd_plot.showGrid(x=True, y=True, alpha=Colors.GRID_ALPHA)
        self.cvd_plot.setMouseEnabled(y=False, x=True)
        _style_pg_plot(self.cvd_plot)
        self.cvd_plot.setXLink(self.price_plot)
        self.cvd_plot.hideAxis("left")
        self.cvd_plot.showAxis("right")
        self.cvd_plot.getAxis("right").setStyle(tickTextOffset=6)
        self.cvd_plot.setLabel("right", "CVD", **_LABEL_CSS)
        self.cvd_plot.setMaximumHeight(140)
        self.cvd_plot.setMinimumHeight(80)
        self._cvd_zero_line = pg.InfiniteLine(
            angle=0, pos=0, movable=False, pen=_CVD_ZERO_PEN
        )
        self.cvd_plot.addItem(self._cvd_zero_line)
        self.cvd_plot.hide()

        self._pane_splitter = QSplitter(Qt.Orientation.Vertical)
        self._pane_splitter.setHandleWidth(2)
        self._pane_splitter.setChildrenCollapsible(True)
        self._pane_splitter.addWidget(self.price_plot)
        self._pane_splitter.addWidget(self.cvd_plot)
        self._pane_splitter.setCollapsible(0, False)
        self._pane_splitter.setCollapsible(1, True)
        self._pane_splitter.setStretchFactor(0, 1)
        self._pane_splitter.setStretchFactor(1, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._pane_splitter)

        mono = QFont()
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self._ohlcv_label = QLabel("", self)
        self._ohlcv_label.setFont(mono)
        self._ohlcv_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; background: transparent; padding: 2px 8px;"
        )
        self._ohlcv_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ohlcv_label.move(8, 4)
        self._ohlcv_label.hide()

        self._price_pill = QLabel("", self)
        self._price_pill.setFont(mono)
        self._price_pill.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._price_pill.hide()

        self._mouse_proxy = pg.SignalProxy(
            self.price_plot.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )

        QTimer.singleShot(0, self._update_vol_geometry)

        interval_ms = max(int(1000 / max(fps, 1)), 16)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(interval_ms)
        self._render_timer.timeout.connect(self._render_if_dirty)
        self._render_timer.start()

        self.set_runtime(runtime)

    def change_subscription(self, exchange: str, symbol: str, timeframe: str) -> None:
        if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:
            return
        self._unsubscribe()
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self._cvd_processor.set_timeframe(timeframe)
        self.clear_data()
        self._subscribe()
        LOGGER.debug("Chart pane resubscribed: %s/%s/%s", exchange, symbol, timeframe)

    def clear_data(self) -> None:
        self.timestamps.clear()
        self.opens.clear()
        self.highs.clear()
        self.lows.clear()
        self.closes.clear()
        self.volumes.clear()
        self._did_initial_fit = False
        self._dirty = False
        self.candle_item.set_data([], [], [], [], [], body_width=1.0)
        self.ha_item.set_data([], [], [], [], [], body_width=1.0)
        self.line_item.setData([], [])
        self.bubbles_item.clear()
        self._trades_cache.clear()
        self._cvd_processor.reset()
        if self._cvd_bar_item is not None:
            self.cvd_plot.removeItem(self._cvd_bar_item)
            self._cvd_bar_item = None

        for _attr in ("_eq_wicks_up", "_eq_wicks_dn", "_eq_body_up", "_eq_body_dn"):
            _item = getattr(self, _attr, None)
            if _item is not None:
                try:
                    self.price_plot.removeItem(_item)
                except Exception:
                    pass
                setattr(self, _attr, None)
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
            self._last_price_line_value = None
        self._price_pill.hide()
        self._ohlcv_label.hide()
        self._v_line.hide()
        self._h_line.hide()

    def load_from_arrays(
        self,
        x: list[float],
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[float],
    ) -> None:
        """Replace chart data from pre-computed arrays (e.g. CandleChartPayload)."""
        n = min(len(x), self.max_points)
        self.timestamps = list(x[-n:])
        self.opens = list(opens[-n:])
        self.highs = list(highs[-n:])
        self.lows = list(lows[-n:])
        self.closes = list(closes[-n:])
        self.volumes = list(volumes[-n:])
        self._did_initial_fit = False
        self._dirty = True

    def load_equity_bars(
        self,
        x: list[int],
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[float],
        *,
        body_fraction: float = 0.6,
    ) -> None:
        """Render equity OHLCV using pg.BarGraphItem bodies + paired-segment wicks.

        Uses pyqtgraph's native BarGraphItem (same renderer as volume bars) so
        widths are handled by the library and always have correct spacing.
        Does NOT set _dirty — the render timer is bypassed entirely for equity.
        """
        n = min(len(x), self.max_points)
        self.timestamps = list(x[-n:])
        self.opens = list(opens[-n:])
        self.highs = list(highs[-n:])
        self.lows = list(lows[-n:])
        self.closes = list(closes[-n:])
        self.volumes = list(volumes[-n:])
        self._did_initial_fit = False
        self._dirty = False  # equity renders here, not through the timer

        xs = self.timestamps
        os_ = self.opens
        hs = self.highs
        ls = self.lows
        cs = self.closes
        vs = self.volumes
        nn = len(xs)

        # -- Clear existing equity and standard candle items --
        for _attr in ("_eq_wicks_up", "_eq_wicks_dn", "_eq_body_up", "_eq_body_dn"):
            _it = getattr(self, _attr, None)
            if _it is not None:
                try:
                    self.price_plot.removeItem(_it)
                except Exception:
                    pass
                setattr(self, _attr, None)
        self.candle_item.set_data([], [], [], [], [], body_width=1.0)
        self.ha_item.set_data([], [], [], [], [], body_width=1.0)
        self.line_item.setData([], [])

        # -- Split bars by direction --
        up = [i for i in range(nn) if cs[i] >= os_[i]]
        dn = [i for i in range(nn) if cs[i] < os_[i]]

        # -- Wicks (full low→high, body painted on top covers the middle) --
        def _wick_arrays(indices):
            wx, wy = [], []
            for i in indices:
                wx += [xs[i], xs[i]]
                wy += [ls[i], hs[i]]
            return wx, wy

        upwx, upwy = _wick_arrays(up)
        dnwx, dnwy = _wick_arrays(dn)

        self._eq_wicks_up = pg.PlotDataItem(
            x=upwx, y=upwy, connect="pairs",
            pen=pg.mkPen(_UP_HEX, width=1),
        )
        self._eq_wicks_dn = pg.PlotDataItem(
            x=dnwx, y=dnwy, connect="pairs",
            pen=pg.mkPen(_DN_HEX, width=1),
        )
        self.price_plot.addItem(self._eq_wicks_up)
        self.price_plot.addItem(self._eq_wicks_dn)

        # -- Bodies (BarGraphItem: library handles the width automatically) --
        def _body_arrays(indices):
            bx = [xs[i] for i in indices]
            by0 = [min(os_[i], cs[i]) for i in indices]
            by1 = [max(os_[i], cs[i]) for i in indices]
            return bx, by0, by1

        upbx, upby0, upby1 = _body_arrays(up)
        dnbx, dnby0, dnby1 = _body_arrays(dn)

        self._eq_body_up = pg.BarGraphItem(
            x=upbx, y0=upby0, y1=upby1,
            width=body_fraction,
            brush=QBrush(_UP_COLOR), pen=pg.mkPen(None),
        )
        self._eq_body_dn = pg.BarGraphItem(
            x=dnbx, y0=dnby0, y1=dnby1,
            width=body_fraction,
            brush=QBrush(_DN_COLOR), pen=pg.mkPen(None),
        )
        self.price_plot.addItem(self._eq_body_up)
        self.price_plot.addItem(self._eq_body_dn)

        # -- Volume --
        if self.volume_item is not None:
            self.vb_vol.removeItem(self.volume_item)
        brushes = [
            QBrush(QColor(38, 166, 154, 140)) if cs[i] >= os_[i]
            else QBrush(QColor(239, 83, 80, 140))
            for i in range(nn)
        ]
        self.volume_item = pg.BarGraphItem(
            x=xs, height=vs,
            width=body_fraction,
            brushes=brushes, pen=pg.mkPen(None),
        )
        self.vb_vol.addItem(self.volume_item)
        self.vb_vol.enableAutoRange(pg.ViewBox.YAxis, True)

        # -- Price line & initial fit --
        self._update_price_line()
        self._fit_initial_view()
        self._did_initial_fit = True

    def set_chart_mode(self, mode: str) -> None:
        normalized = (mode or "").strip().lower()
        if normalized not in {"candles", "line", "heikin ashi"}:
            normalized = "candles"
        self._chart_mode = normalized
        self._dirty = True

    def chart_mode(self) -> str:
        return self._chart_mode

    def set_bubbles_enabled(self, enabled: bool) -> None:
        self._show_bubbles = bool(enabled)
        self._dirty = True

    def bubbles_enabled(self) -> bool:
        return self._show_bubbles

    def set_cvd_enabled(self, enabled: bool) -> None:
        self._show_cvd = bool(enabled)
        if self._show_cvd:
            self.cvd_plot.show()
            total = self._pane_splitter.height()
            cvd_h = max(100, min(160, total // 5))
            self._pane_splitter.setSizes([total - cvd_h, cvd_h])
        else:
            self.cvd_plot.hide()
            self._pane_splitter.setSizes([self._pane_splitter.height(), 0])
        self._dirty = True

    def cvd_enabled(self) -> bool:
        return self._show_cvd

    def set_vpvr_enabled(self, enabled: bool) -> None:
        self._show_vpvr = bool(enabled)
        if self._show_vpvr:
            self._vpvr_item.show()
            self._render_vpvr()
        else:
            self._vpvr_item.hide()
            self._vpvr_item.set_profile([], 0.0, 1.0, 1.0)

    def vpvr_enabled(self) -> bool:
        return self._show_vpvr

    def cvd_stats(self) -> dict[str, float | None]:
        """Return summary CVD stats for the current session."""
        if not self._show_cvd:
            return {"session_cvd": None, "bar_delta": None, "total_buy": None, "total_sell": None}
        _ts, deltas, cumulative = self._cvd_processor.get_series()
        session_cvd = cumulative[-1] if cumulative else 0.0
        bar_delta = deltas[-1] if deltas else 0.0
        total_buy = sum(b[0] for b in self._cvd_processor._buckets.values())
        total_sell = sum(b[1] for b in self._cvd_processor._buckets.values())
        return {
            "session_cvd": session_cvd,
            "bar_delta": bar_delta,
            "total_buy": total_buy,
            "total_sell": total_sell,
        }

    def set_ema_enabled(self, enabled: bool) -> None:
        self.show_ema = bool(enabled)
        if not enabled and self.ema_item is not None:
            self.price_plot.removeItem(self.ema_item)
            self.ema_item = None
        self._dirty = True

    def ema_enabled(self) -> bool:
        return self.show_ema

    def set_price_axis_visible(self, visible: bool) -> None:
        """Show or hide the right-hand price Y-axis at runtime.

        Call with ``visible=False`` when the OB ladder is shown (it acts as
        the visual Y-axis) and ``visible=True`` when the ladder is hidden so
        the chart has its own price scale.
        """
        self.show_price_axis = visible
        if visible:
            self.price_plot.setLabel("right", "Price", **_LABEL_CSS)
            self.price_plot.showAxis("right")
            self.price_plot.hideAxis("left")
            self.price_plot.getAxis("right").setStyle(tickTextOffset=6)
        else:
            self.price_plot.hideAxis("right")
            self.price_plot.hideAxis("left")

    def set_runtime(self, runtime) -> None:
        self.runtime = runtime
        if runtime is None or runtime.core is None:
            return
        self._register_handlers()
        self._subscribe()

    def visible_price_range(self) -> tuple[float, float]:
        y_min, y_max = self.price_plot.getViewBox().viewRange()[1]
        return float(y_min), float(y_max)

    def current_last_price(self) -> float | None:
        if not self.closes:
            return None
        return float(self.closes[-1])

    def _register_handlers(self) -> None:
        if self._handlers_registered or self.runtime is None or self.runtime.core is None:
            return
        emitter = self.runtime.core.emitter
        emitter.register(Signals.NEW_CANDLES, self._on_new_candles)
        emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        emitter.register(Signals.NEW_TRADE, self._on_new_trade)
        self._handlers_registered = True

    def _unregister_handlers(self) -> None:
        if not self._handlers_registered or self.runtime is None or self.runtime.core is None:
            return
        emitter = self.runtime.core.emitter
        try:
            emitter.unregister(Signals.NEW_CANDLES, self._on_new_candles)
            emitter.unregister(Signals.UPDATED_CANDLES, self._on_updated_candles)
            emitter.unregister(Signals.NEW_TRADE, self._on_new_trade)
        except Exception as exc:
            LOGGER.debug("Chart pane unregister handler failed: %s", exc)
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
        self.runtime.core.subscribe_to_trades(
            exchange=self.exchange,
            symbol=self.symbol,
            widget_instance=self,
        )
        self._subscribed = True
        LOGGER.debug("Chart pane subscribed: %s/%s/%s", self.exchange, self.symbol, self.timeframe)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("Chart pane unsubscribe failed: %s", exc)
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

    def _on_new_trade(self, exchange: str, trade_data: dict) -> None:
        if exchange != self.exchange or trade_data.get("symbol") != self.symbol:
            return
        self._trades_cache.append(trade_data)
        self._cvd_processor.add_trade(trade_data)
        if self._show_bubbles or self._show_cvd:
            self._dirty = True

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

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.timestamps:
            return
        self._dirty = False

        x = self.timestamps
        candle_width = self._infer_candle_width_seconds()
        self._current_candle_width = candle_width
        
        self.candle_item.hide()
        self.ha_item.hide()
        self.line_item.hide()

        if self._chart_mode == "candles":
            self.candle_item.show()
            self.candle_item.set_data(
                x, self.opens, self.highs, self.lows, self.closes, body_width=candle_width * self._body_width_fraction
            )
        elif self._chart_mode == "line":
            self.line_item.show()
            self.line_item.setData(x, self.closes)
        elif self._chart_mode == "heikin ashi":
            self.ha_item.show()
            ha_opens, ha_highs, ha_lows, ha_closes = [], [], [], []
            for i in range(len(self.closes)):
                ha_c = (self.opens[i] + self.highs[i] + self.lows[i] + self.closes[i]) / 4.0
                if i == 0:
                    ha_o = (self.opens[i] + self.closes[i]) / 2.0
                else:
                    ha_o = (ha_opens[-1] + ha_closes[-1]) / 2.0
                ha_h = max(self.highs[i], ha_o, ha_c)
                ha_l = min(self.lows[i], ha_o, ha_c)
                ha_opens.append(ha_o)
                ha_highs.append(ha_h)
                ha_lows.append(ha_l)
                ha_closes.append(ha_c)
            self.ha_item.set_data(
                x, ha_opens, ha_highs, ha_lows, ha_closes, body_width=candle_width * self._body_width_fraction
            )
            
        if self._show_bubbles and self._trades_cache:
            spots = []
            # Calculate dynamic sizing based on max amount in cache
            max_amt = max(
                (float(t.get("amount", 0.0)) for t in self._trades_cache if t.get("amount") is not None),
                default=0.01,
            )
            for trade in self._trades_cache:
                amt = float(trade.get("amount", 0.0) or 0.0)
                price = float(trade.get("price", 0.0) or 0.0)
                ts = float(trade.get("timestamp", 0) or 0) / 1000.0  # Assumes ms timestamps
                
                # Scale radius non-linearly for extreme outliers, bounded between 8px and 45px
                ratio = math.sqrt(amt / max_amt) if max_amt > 0 else 0
                size = 8 + (37 * ratio)
                
                side = trade.get("side", "")
                if side == "buy":
                    brush = pg.mkBrush(38, 166, 154, 180) # Buy Green
                    pen = pg.mkPen(26, 115, 106, 200)
                else:
                    brush = pg.mkBrush(239, 83, 80, 180)  # Sell Red
                    pen = pg.mkPen(182, 60, 58, 200)
                    
                spots.append({
                    "pos": (ts, price),
                    "size": size,
                    "brush": brush,
                    "pen": pen,
                    "data": trade
                })
            
            self.bubbles_item.show()
            self.bubbles_item.setData(spots)
        else:
            self.bubbles_item.hide()
            self.bubbles_item.clear()
            
        self._update_price_line()

        vol_brushes = [
            QBrush(QColor(38, 166, 154, 140)) if c >= o else QBrush(QColor(239, 83, 80, 140))
            for o, c in zip(self.opens, self.closes)
        ]
        vol_width = candle_width * self._body_width_fraction
        if self.volume_item is None:
            self.volume_item = pg.BarGraphItem(
                x=x, height=self.volumes, width=vol_width, brushes=vol_brushes, pen=pg.mkPen(None),
            )
            self.vb_vol.addItem(self.volume_item)
        else:
            self.volume_item.setOpts(x=x, height=self.volumes, width=vol_width, brushes=vol_brushes)
        self.vb_vol.enableAutoRange(pg.ViewBox.YAxis, True)

        if self.show_ema:
            ema = pd.Series(self.closes).ewm(span=20, adjust=False).mean().tolist()
            if self.ema_item is None:
                self.ema_item = self.price_plot.plot(x=x, y=ema, pen=pg.mkPen(color=(100, 180, 255), width=1.0))
            else:
                self.ema_item.setData(x=x, y=ema)

        if self._show_cvd:
            self._render_cvd()

        if self._show_vpvr:
            self._render_vpvr()

        if x and not self._did_initial_fit:
            self._fit_initial_view()
            self._did_initial_fit = True

    def _render_cvd(self) -> None:
        ts, deltas, _cumulative = self._cvd_processor.get_series()
        if not ts:
            return

        candle_width = self._current_candle_width * self._body_width_fraction
        brushes = [
            QBrush(QColor(38, 166, 154, 200)) if d >= 0
            else QBrush(QColor(239, 83, 80, 200))
            for d in deltas
        ]

        if self._cvd_bar_item is None:
            self._cvd_bar_item = pg.BarGraphItem(
                x=ts, height=deltas, width=candle_width, brushes=brushes, pen=pg.mkPen(None),
            )
            self.cvd_plot.addItem(self._cvd_bar_item)
        else:
            self._cvd_bar_item.setOpts(x=ts, height=deltas, width=candle_width, brushes=brushes)
        self.cvd_plot.getViewBox().enableAutoRange(pg.ViewBox.YAxis, True)

    def _render_vpvr(self) -> None:
        """Compute and draw the Volume Profile Visible Range overlay."""
        if not self.timestamps or not self.volumes:
            return

        vb = self.price_plot.getViewBox()
        x_lo, x_hi = vb.viewRange()[0]
        y_lo, y_hi = vb.viewRange()[1]
        price_span = max(y_hi - y_lo, 1e-9)
        x_span = max(x_hi - x_lo, 1e-9)

        # Collect candle indices visible in the current X window.
        lo_idx = bisect.bisect_left(self.timestamps, x_lo)
        hi_idx = bisect.bisect_right(self.timestamps, x_hi)
        if lo_idx >= hi_idx:
            self._vpvr_item.set_profile([], x_hi, 1.0, 1.0)
            return

        # Distribute each candle's volume into price bins.
        bin_h = price_span / _VPVR_N_BINS
        vol_bins = [0.0] * _VPVR_N_BINS

        for i in range(lo_idx, hi_idx):
            lo = self.lows[i]
            hi_p = self.highs[i]
            vol = self.volumes[i]
            candle_span = max(hi_p - lo, bin_h * 0.1)

            # First and last bin indices this candle touches.
            b_lo = max(0, int((lo - y_lo) / bin_h))
            b_hi = min(_VPVR_N_BINS - 1, int((hi_p - y_lo) / bin_h))

            for b in range(b_lo, b_hi + 1):
                bin_lo = y_lo + b * bin_h
                bin_hi_p = bin_lo + bin_h
                overlap = min(hi_p, bin_hi_p) - max(lo, bin_lo)
                if overlap > 0:
                    vol_bins[b] += vol * (overlap / candle_span)

        # Build (center, volume) pairs for non-empty bins.
        bins = [
            (y_lo + (b + 0.5) * bin_h, vol_bins[b])
            for b in range(_VPVR_N_BINS)
            if vol_bins[b] > 0
        ]

        max_bar_width = x_span * _VPVR_WIDTH_FRAC
        self._vpvr_item.set_profile(bins, x_hi, max_bar_width, bin_h)

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

    def _update_vol_geometry(self) -> None:
        geom = self.price_plot.getViewBox().sceneBoundingRect()
        if geom.height() == 0:
            return
        vol_h = geom.height() * _VOL_FRACTION
        self.vb_vol.setGeometry(geom.x(), geom.y() + geom.height() - vol_h, geom.width(), vol_h)
        self._reposition_price_pill()

    def _update_price_line(self) -> None:
        if not self.closes:
            return
        price = self.closes[-1]
        is_up = len(self.closes) < 2 or price >= self.closes[-2]
        hex_color = _UP_HEX if is_up else _DN_HEX

        if is_up != self._price_line_up:
            if self._price_line is not None:
                self.price_plot.removeItem(self._price_line)
            price_line_kwargs: dict[str, Any] = {
                "angle": 0,
                "movable": False,
                "pen": pg.mkPen(hex_color, width=1, style=Qt.PenStyle.DashLine),
            }
            if self.show_price_axis:
                price_line_kwargs["label"] = "{value:.2f}"
                price_line_kwargs["labelOpts"] = {
                    "position": 1.0,
                    "color": "#ffffff",
                    "fill": pg.mkBrush(hex_color),
                }
            self._price_line = pg.InfiniteLine(**price_line_kwargs)
            self._price_line.setZValue(30)
            self.price_plot.addItem(self._price_line, ignoreBounds=True)
            self._price_line_up = is_up

        self._price_line.setPos(price)
        if self._last_price_line_value is None or not math.isclose(
            self._last_price_line_value,
            float(price),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            # Bubble updates can leave the graphics scene partially stale until another
            # viewport change invalidates the region. Force a scene refresh when the
            # close line moves so dashed segments do not ghost.
            self.price_plot.viewport().update()
            self.price_plot.scene().update()
            self._last_price_line_value = float(price)
        self._update_price_pill(price=price, hex_color=hex_color)
        self.last_price_changed.emit(float(price))

    def _update_price_pill(self, *, price: float, hex_color: str) -> None:
        if self.show_price_axis:
            self._price_pill.hide()
            return
        self._price_pill.setText(_fmt_price(price))
        self._price_pill.setStyleSheet(
            f"color: #ffffff; background: {hex_color}; "
            f"padding: 2px 6px; border: 1px solid {Colors.BG_CANVAS};"
        )
        self._price_pill.adjustSize()
        self._reposition_price_pill()
        self._price_pill.show()

    def _reposition_price_pill(self) -> None:
        if self._price_pill.isHidden():
            return
        vb = self.price_plot.getViewBox()
        geom = vb.sceneBoundingRect()
        if geom.height() == 0 or self._price_line is None:
            return
        y_scene = vb.mapViewToScene(QPointF(0.0, float(self._price_line.value()))).y()
        y_widget = self.price_plot.mapFromScene(QPointF(geom.right(), y_scene)).y()
        x = self.width() - self._price_pill.width() - 6
        y = int(y_widget - (self._price_pill.height() / 2))
        y = max(4, min(self.height() - self._price_pill.height() - 4, y))
        self._price_pill.move(max(4, x), y)

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

        if abs(x - self.timestamps[idx]) > self._current_candle_width * 0.5:
            self._v_line.hide()
            self._ohlcv_label.hide()
            return

        self._v_line.show()
        self._v_line.setPos(self.timestamps[idx])

        o, h, l, c, v = (
            self.opens[idx],
            self.highs[idx],
            self.lows[idx],
            self.closes[idx],
            self.volumes[idx],
        )
        delta = c - o
        pct = (delta / o * 100) if o != 0 else 0.0
        color = _UP_HEX if c >= o else _DN_HEX

        sign = "+" if delta >= 0 else ""
        self._ohlcv_label.setText(
            f"O {_fmt_price(o)}  H {_fmt_price(h)}  L {_fmt_price(l)}  C {_fmt_price(c)}  "
            f"{sign}{_fmt_price(delta)} ({pct:+.2f}%)  Vol: {_fmt_vol(v)}"
        )
        self._ohlcv_label.setStyleSheet(f"color: {color}; background: transparent; padding: 2px 8px;")
        self._ohlcv_label.adjustSize()
        self._ohlcv_label.show()

    def _on_y_range_changed(self, _vb, y_range) -> None:
        self._reposition_price_pill()
        self.visible_price_range_changed.emit(float(y_range[0]), float(y_range[1]))
        if self._show_vpvr:
            self._render_vpvr()

    def _on_x_range_changed(self, _vb, _x_range) -> None:
        if self._show_vpvr:
            self._render_vpvr()

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

    def shutdown(self) -> None:
        self._render_timer.stop()
        self._unsubscribe()
        self._unregister_handlers()

    def closeEvent(self, event):  # noqa: N802
        self.shutdown()
        super().closeEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._reposition_price_pill()


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
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return max(amount * multipliers.get(unit, 60), 1)
