from __future__ import annotations

from datetime import datetime, timezone as dt_tz
from typing import Any

import pyqtgraph as pg
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sentinel.market.cache.memory_cache import InMemoryCacheStore
from sentinel.market.providers.yfinance_provider import YFinanceEquityProvider
from sentinel.market.query import Timeframe
from sentinel.market.services.equities_service import EquitiesService
from sentinel.market.viewmodels.equity_chart_viewmodel import EquityChartViewModel
from sentinel.widgets.chart_pane import ChartPane


_DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "SPY", "QQQ"]

_TF_MAP: dict[str, Timeframe] = {
    "1m":  Timeframe.M1,
    "5m":  Timeframe.M5,
    "15m": Timeframe.M15,
    "1h":  Timeframe.H1,
    "1d":  Timeframe.D1,
}

_DAYS_MAP: dict[str, int] = {
    "30d": 30,
    "90d": 90,
    "180d": 180,
    "365d": 365,
}

# yfinance intraday limits: 1m→7d, 5m/15m→60d, 1h→730d
_TF_MAX_DAYS: dict[str, int] = {
    "1m":  7,
    "5m":  60,
    "15m": 60,
    "1h":  730,
    "1d":  3650,
}

_TICK_FONT = QFont()
_TICK_FONT.setStyleHint(QFont.StyleHint.Monospace)
_TICK_FONT.setPointSize(8)


def _date_label(ts: float, timeframe: str) -> str:
    """Convert a Unix timestamp to a human-readable tick label for a given timeframe."""
    dt = datetime.fromtimestamp(ts, tz=dt_tz.utc)
    if timeframe == "1d":
        return dt.strftime("%b %d")
    if timeframe in ("1h", "15m", "5m"):
        return dt.strftime("%m/%d %H:%M")
    # 1m
    return dt.strftime("%H:%M")


class _EquityDateAxisItem(pg.AxisItem):
    """X-axis that maps integer bar indices to human-readable date labels.

    Equity data has gaps for weekends and holidays. Plotting raw Unix timestamps
    creates visual voids between Friday close and Monday open, making daily
    charts look sparse. This axis displays bars at evenly-spaced integer positions
    (0, 1, 2, …) while labelling ticks with the actual trading-session dates.
    """

    def __init__(self) -> None:
        super().__init__(orientation="bottom")
        self._index_to_label: dict[int, str] = {}
        # Match the styling applied by _style_pg_plot
        self.setPen(pg.mkPen(color="#1e2d3f", width=1))
        self.setTextPen(pg.mkPen(color="#546d8a"))
        self.setTickFont(_TICK_FONT)
        self.setStyle(tickLength=-5)

    def set_index_map(self, index_to_label: dict[int, str]) -> None:
        self._index_to_label = index_to_label

    def tickStrings(self, values: list, scale: float, spacing: float) -> list[str]:  # noqa: N802
        result = []
        for v in values:
            idx = int(round(v))
            result.append(self._index_to_label.get(idx, ""))
        return result


class EquityChartDockWidget(QDockWidget):
    closed = Signal()

    def __init__(
        self,
        *,
        instance_id: str,
        symbol: str = "AAPL",
        timeframe: str = "1d",
        days: str = "30d",
        chart_mode: str = "candles",
    ) -> None:
        super().__init__(f"Equity — {symbol} ({timeframe})")
        self.instance_id = instance_id
        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._symbol = symbol.strip().upper()
        self._timeframe_str = timeframe

        # --- Service stack (self-contained, no runtime required) ---
        provider = YFinanceEquityProvider()
        service = EquitiesService(
            provider=provider,
            bar_cache=InMemoryCacheStore(),
            quote_cache=InMemoryCacheStore(),
        )
        self._viewmodel = EquityChartViewModel(service, parent=self)
        self._viewmodel.payload_ready.connect(self._on_payload_ready)
        self._viewmodel.loading_changed.connect(self._on_loading_changed)
        self._viewmodel.error_changed.connect(self._on_error_changed)

        # --- ChartPane (runtime=None → no live crypto subscriptions) ---
        self.chart_pane = ChartPane(
            runtime=None,
            exchange="equity",
            symbol=self._symbol,
            timeframe=timeframe,
            show_price_axis=True,
            body_width_fraction=0.6,
        )
        self.chart_pane.set_chart_mode(chart_mode)

        # --- Swap the DateAxisItem for our index-based axis ---
        # ChartPane hardcodes pg.DateAxisItem; equity data must use integer
        # bar indices to eliminate weekend / holiday gaps.
        self._date_axis = _EquityDateAxisItem()
        self.chart_pane.price_plot.getPlotItem().setAxisItems({"bottom": self._date_axis})

        # --- Toolbar ---
        toolbar = self._build_toolbar(symbol=symbol, timeframe=timeframe, days=days, mode=chart_mode)

        # --- Loading overlay (absolute-positioned label over chart_pane) ---
        self._loading_label = QLabel("Loading…", self.chart_pane)
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(
            "color: #8fb3ff; background: rgba(6,10,17,180); font-size: 13px;"
        )
        self._loading_label.hide()
        self._loading_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # --- Assemble body ---
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self.chart_pane, 1)
        self.setWidget(body)

        # Defer initial load until the qasync event loop is running
        QTimer.singleShot(0, self._reload)

    # ------------------------------------------------------------------
    # Toolbar construction
    # ------------------------------------------------------------------

    def _build_toolbar(
        self, *, symbol: str, timeframe: str, days: str, mode: str
    ) -> QWidget:
        bar = QWidget()
        bar.setObjectName("chart-toolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        _ic = "#6a85a8"

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.finance", color=_ic).pixmap(16, 16))
        layout.addWidget(icon_label)

        self._symbol_combo = QComboBox()
        self._symbol_combo.setEditable(True)
        self._symbol_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._symbol_combo.addItems(_DEFAULT_SYMBOLS)
        self._set_combo(self._symbol_combo, symbol.upper())
        # Only reload on dropdown selection or explicit Return — not on every keystroke.
        self._symbol_combo.activated.connect(self._on_toolbar_changed)
        self._symbol_combo.lineEdit().returnPressed.connect(self._on_toolbar_changed)
        layout.addWidget(self._symbol_combo)

        self._timeframe_combo = QComboBox()
        self._timeframe_combo.addItems(list(_TF_MAP.keys()))
        self._set_combo(self._timeframe_combo, timeframe)
        self._timeframe_combo.currentTextChanged.connect(self._on_timeframe_changed)
        layout.addWidget(self._timeframe_combo)

        self._days_combo = QComboBox()
        self._days_combo.addItems(list(_DAYS_MAP.keys()))
        self._set_combo(self._days_combo, days)
        self._days_combo.currentTextChanged.connect(self._on_toolbar_changed)
        layout.addWidget(self._days_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Candles", "Line", "Heikin Ashi"])
        self._mode_combo.setItemIcon(0, qta.icon("mdi6.chart-box-outline", color=_ic))
        self._mode_combo.setItemIcon(1, qta.icon("mdi6.chart-line", color=_ic))
        self._mode_combo.setItemIcon(2, qta.icon("mdi6.chart-areaspline", color=_ic))
        self._set_combo(self._mode_combo, mode.title())
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #ef5350; font-size: 11px; padding: 0 4px;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._context_label = QLabel(f"{symbol.upper()} · {timeframe}")
        self._context_label.setStyleSheet("color: #6a85a8; font-size: 11px;")
        layout.addWidget(self._context_label)

        return bar

    # ------------------------------------------------------------------
    # Toolbar slots
    # ------------------------------------------------------------------

    def _on_toolbar_changed(self, _: str = "") -> None:
        self._reload()

    def _on_timeframe_changed(self, tf: str) -> None:
        # Clamp the days combo to what yfinance supports for this interval
        max_days = _TF_MAX_DAYS.get(tf, 3650)
        current_days = _DAYS_MAP.get(self._days_combo.currentText(), 30)
        if current_days > max_days:
            best = max(
                (label for label, d in _DAYS_MAP.items() if d <= max_days),
                key=lambda label: _DAYS_MAP[label],
                default="30d",
            )
            self._days_combo.blockSignals(True)
            self._set_combo(self._days_combo, best)
            self._days_combo.blockSignals(False)
        self._reload()

    def _on_mode_changed(self, mode: str) -> None:
        self.chart_pane.set_chart_mode(mode.lower())

    # ------------------------------------------------------------------
    # ViewModel signal handlers
    # ------------------------------------------------------------------

    def _on_payload_ready(self, payload) -> None:
        n = len(payload.x)
        if n == 0:
            return

        # Convert raw Unix timestamps → contiguous integer bar indices so that
        # weekend / holiday gaps do not appear as empty space on the x-axis.
        indices = list(range(n))
        tf = self._timeframe_combo.currentText()
        index_to_label: dict[int, str] = {
            i: _date_label(float(ts), tf) for i, ts in enumerate(payload.x)
        }
        self._date_axis.set_index_map(index_to_label)

        # Use pg.BarGraphItem rendering (library handles widths — no manual calc).
        self.chart_pane.load_equity_bars(
            x=indices,
            opens=list(payload.opens),
            highs=list(payload.highs),
            lows=list(payload.lows),
            closes=list(payload.closes),
            volumes=list(payload.volumes),
            body_fraction=0.6,
        )
        self.setWindowTitle(f"Equity — {self._symbol} ({self._timeframe_str})")
        self._context_label.setText(f"{self._symbol} · {self._timeframe_str}")

    def _on_loading_changed(self, loading: bool) -> None:
        self._loading_label.setVisible(loading)
        if loading:
            self._loading_label.resize(self.chart_pane.size())

    def _on_error_changed(self, error: str) -> None:
        self._error_label.setText(error)
        self._error_label.setVisible(bool(error))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        sym = self._symbol_combo.currentText().strip().upper()
        tf_str = self._timeframe_combo.currentText()
        tf = _TF_MAP.get(tf_str, Timeframe.D1)
        days = _DAYS_MAP.get(self._days_combo.currentText(), 30)

        self._symbol = sym
        self._timeframe_str = tf_str

        self._error_label.hide()
        self.chart_pane.clear_data()
        self._viewmodel.request_symbol(sym, tf, days=days)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value, Qt.MatchFlag.MatchFixedString)
        if idx < 0:
            combo.addItem(value)
            idx = combo.findText(value, Qt.MatchFlag.MatchFixedString)
        combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Registry / persistence interface
    # ------------------------------------------------------------------

    def set_runtime(self, runtime) -> None:
        pass  # equities widget owns its data stack; runtime not needed

    def export_definition(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "widget_type": "equity_chart",
            "config": {
                "symbol": self._symbol,
                "timeframe": self._timeframe_combo.currentText(),
                "days": self._days_combo.currentText(),
                "chart_mode": self._mode_combo.currentText().lower(),
            },
        }

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._loading_label.isHidden():
            self._loading_label.resize(self.chart_pane.size())

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        self.chart_pane.shutdown()
        super().closeEvent(event)
