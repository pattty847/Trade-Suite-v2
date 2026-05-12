from __future__ import annotations

import logging
from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

_DEFAULT_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "BTC/USDT", "ETH/USDT"]
_DEFAULT_EXCHANGES = ["coinbase", "binance", "kraken"]

from sentinel.analysis.orderbook_processor import OrderBookProcessor
from sentinel.app.theme import Colors, Spacing, pg_label_css
from sentinel.app.widgets import EmptyState
from sentinel.core.signals import Signals


LOGGER = logging.getLogger(__name__)

_AXIS_PEN = pg.mkPen(color=Colors.AXIS_PEN, width=1)
_TICK_PEN = pg.mkPen(color=Colors.TICK_PEN)
_TICK_FONT = QFont()
_TICK_FONT.setStyleHint(QFont.StyleHint.Monospace)
_TICK_FONT.setPointSize(8)
_LABEL_CSS = pg_label_css()

_DATA_FONT = QFont()
_DATA_FONT.setStyleHint(QFont.StyleHint.Monospace)
_DATA_FONT.setPointSize(9)


def _style_pg_plot(plot: pg.PlotWidget) -> None:
    for axis_name in ("left", "right", "top", "bottom"):
        ax = plot.getAxis(axis_name)
        ax.setPen(_AXIS_PEN)
        ax.setTextPen(_TICK_PEN)
        ax.setTickFont(_TICK_FONT)
        ax.setStyle(tickLength=-5)
    plot.getViewBox().setBorder(pg.mkPen(Colors.BORDER_SUB, width=1))


def _step_button(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("role", "step")
    btn.setToolTip(tooltip)
    btn.setFixedWidth(24)
    return btn


def _section_header(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("section-header")
    return label


class OrderbookDockWidget(QDockWidget):
    closed = Signal()

    def __init__(
        self,
        *,
        instance_id: str,
        runtime,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        price_precision: float = 0.01,
        fps: int = 20,
    ) -> None:
        super().__init__(f"Orderbook · {exchange.upper()}  {symbol}")
        self.instance_id = instance_id
        self.exchange = exchange
        self.symbol = symbol
        self.runtime = None
        self._handlers_registered = False
        self._subscribed = False

        self.processor = OrderBookProcessor(price_precision=price_precision)
        self.last_orderbook: dict[str, Any] | None = None
        self._dirty = False
        self._mode = "agg"
        self._bids_bars = None
        self._asks_bars = None

        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(Spacing.L, Spacing.M, Spacing.L, Spacing.M)
        root.setSpacing(Spacing.S)

        root.addWidget(_section_header("Market"))

        # Symbol / exchange selector
        sym_row = QHBoxLayout()
        sym_row.setSpacing(Spacing.M)
        self.exchange_combo = QComboBox()
        self.exchange_combo.setToolTip("Exchange")
        self.exchange_combo.addItems(_DEFAULT_EXCHANGES)
        self._set_combo(self.exchange_combo, exchange)
        self.exchange_combo.setFixedHeight(24)
        self.symbol_combo = QComboBox()
        self.symbol_combo.setToolTip("Symbol")
        self.symbol_combo.addItems(_DEFAULT_SYMBOLS)
        self._set_combo(self.symbol_combo, symbol)
        self.symbol_combo.setFixedHeight(24)
        sym_row.addWidget(self.exchange_combo)
        sym_row.addWidget(self.symbol_combo, 1)
        root.addLayout(sym_row)

        self.exchange_combo.currentTextChanged.connect(self._on_combo_changed)
        self.symbol_combo.currentTextChanged.connect(self._on_combo_changed)

        root.addWidget(_section_header("View"))

        top_row = QHBoxLayout()
        top_row.setSpacing(Spacing.M)
        self.agg_checkbox = QCheckBox("Aggregate")
        self.agg_checkbox.setToolTip("Aggregate levels onto the current tick size")
        self.agg_checkbox.setChecked(self.processor.aggregation_enabled)
        self.agg_checkbox.toggled.connect(self._on_toggle_aggregation)
        top_row.addWidget(self.agg_checkbox)

        spread_lbl = QLabel("Spread %")
        spread_lbl.setProperty("role", "caption")
        top_row.addWidget(spread_lbl)
        self.spread_slider = QSlider()
        self.spread_slider.setOrientation(Qt.Orientation.Horizontal)
        self.spread_slider.setMinimum(1)
        self.spread_slider.setMaximum(200)
        self.spread_slider.setValue(int(self.processor.spread_percentage * 1000))
        self.spread_slider.setToolTip("Visible spread percentage around mid")
        self.spread_slider.valueChanged.connect(self._on_spread_changed)
        top_row.addWidget(self.spread_slider, 1)

        tick_lbl = QLabel("Tick")
        tick_lbl.setProperty("role", "caption")
        top_row.addWidget(tick_lbl)
        self.tick_label = QLabel(f"{self.processor.tick_size:.8g}")
        self.tick_label.setFont(_DATA_FONT)
        self.tick_label.setProperty("role", "value")
        top_row.addWidget(self.tick_label)
        down_btn = _step_button("−", "Smaller tick")
        up_btn = _step_button("+", "Larger tick")
        down_btn.clicked.connect(self._decrease_tick)
        up_btn.clicked.connect(self._increase_tick)
        top_row.addWidget(down_btn)
        top_row.addWidget(up_btn)
        root.addLayout(top_row)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(Spacing.XL)
        self.ratio_label = QLabel("Bid/Ask 1.00")
        self.best_bid_label = QLabel("Bid —")
        self.best_ask_label = QLabel("Ask —")
        self.spread_label = QLabel("Spread —")
        for lbl in (self.ratio_label, self.best_bid_label, self.best_ask_label, self.spread_label):
            lbl.setFont(_DATA_FONT)
            lbl.setProperty("role", "caption")
            stats_row.addWidget(lbl)
        stats_row.addStretch(1)
        root.addLayout(stats_row)

        self.plot = pg.PlotWidget()
        self.plot.setBackground(Colors.BG_CANVAS)
        self.plot.setLabel("right", "Volume", **_LABEL_CSS)
        self.plot.setLabel("bottom", "Price", **_LABEL_CSS)
        self.plot.showAxis("right")
        self.plot.hideAxis("left")
        self.plot.showGrid(x=True, y=True, alpha=Colors.GRID_ALPHA)
        self.plot.addLegend(offset=(10, 10))
        _style_pg_plot(self.plot)

        self._empty_state = EmptyState(
            "WAITING FOR ORDERBOOK",
            f"{exchange.upper()}  {symbol}",
        )
        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self.plot)
        self._stack.setCurrentWidget(self._empty_state)
        root.addWidget(self._stack, 1)

        self.bids_line = self.plot.plot([], [], pen=pg.mkPen((40, 210, 120), width=2), name="Bids")
        self.asks_line = self.plot.plot([], [], pen=pg.mkPen((220, 80, 90), width=2), name="Asks")

        self.setWidget(body)
        self.setMinimumWidth(300)
        self.setMaximumWidth(560)

        interval_ms = max(int(1000 / max(fps, 1)), 16)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(interval_ms)
        self._render_timer.timeout.connect(self._render_if_dirty)
        self._render_timer.start()

        self.set_runtime(runtime)

    def export_definition(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "widget_type": "orderbook",
            "config": {
                "exchange": self.exchange,
                "symbol": self.symbol,
            },
        }

    def change_subscription(self, exchange: str, symbol: str) -> None:
        """Switch to a different exchange/symbol without recreating the widget."""
        if exchange == self.exchange and symbol == self.symbol:
            return
        self._unsubscribe()
        self.exchange = exchange
        self.symbol = symbol
        self.last_orderbook = None
        self._dirty = False
        self._bids_bars = None
        self._asks_bars = None
        self.bids_line.setData([], [])
        self.asks_line.setData([], [])
        self.best_bid_label.setText("Bid —")
        self.best_ask_label.setText("Ask —")
        self.spread_label.setText("Spread —")
        self.ratio_label.setText("Bid/Ask 1.00")
        self.setWindowTitle(f"Orderbook · {exchange.upper()}  {symbol}")
        self._empty_state.set_hint(f"{exchange.upper()}  {symbol}")
        self._stack.setCurrentWidget(self._empty_state)
        self._subscribe()

    def _on_combo_changed(self, _value: str) -> None:
        self.change_subscription(
            self.exchange_combo.currentText(),
            self.symbol_combo.currentText(),
        )

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx < 0:
            combo.addItem(value)
            idx = combo.findText(value)
        combo.setCurrentIndex(idx)

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
        emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
        self._handlers_registered = True

    def _unregister_handlers(self) -> None:
        if not self._handlers_registered or self.runtime is None or self.runtime.core is None:
            return
        emitter = self.runtime.core.emitter
        try:
            emitter.unregister(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
        except Exception as exc:
            LOGGER.debug("Orderbook unregister handler failed: %s", exc)
        self._handlers_registered = False

    def _subscribe(self) -> None:
        if self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        self.runtime.core.subscribe_to_orderbook(
            exchange=self.exchange,
            symbol=self.symbol,
            widget_instance=self,
        )
        self._subscribed = True
        LOGGER.debug("Orderbook subscribed: %s/%s", self.exchange, self.symbol)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("Orderbook unsubscribe failed: %s", exc)
        self._subscribed = False

    def _on_order_book_update(self, exchange: str, orderbook: dict):
        if exchange != self.exchange:
            return
        ob_symbol = orderbook.get("symbol")
        if ob_symbol is not None and ob_symbol != self.symbol:
            return
        self.last_orderbook = orderbook
        self._dirty = True

    def _on_toggle_aggregation(self, checked: bool) -> None:
        if checked != self.processor.aggregation_enabled:
            self.processor.toggle_aggregation()
        self._mode = "agg" if self.processor.aggregation_enabled else "bars"
        self._dirty = True

    def _on_spread_changed(self, value: int) -> None:
        # slider is 1..200 -> 0.001..0.2
        spread = max(value / 1000.0, 0.001)
        self.processor.set_spread_percentage(spread)
        self._dirty = True

    def _increase_tick(self) -> None:
        current_price = self._current_mid_price()
        new_tick = self.processor.increase_tick_size(current_price)
        self.tick_label.setText(f"{new_tick:.8g}")
        self._dirty = True

    def _decrease_tick(self) -> None:
        current_price = self._current_mid_price()
        new_tick = self.processor.decrease_tick_size(current_price)
        self.tick_label.setText(f"{new_tick:.8g}")
        self._dirty = True

    def _current_mid_price(self) -> float | None:
        if not self.last_orderbook:
            return None
        bids = self.last_orderbook.get("bids", [])
        asks = self.last_orderbook.get("asks", [])
        if not bids or not asks:
            return None
        return (bids[0][0] + asks[0][0]) / 2

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.last_orderbook:
            return
        self._dirty = False

        raw_bids = self.last_orderbook.get("bids", [])
        raw_asks = self.last_orderbook.get("asks", [])
        current_price = self._current_mid_price()
        processed = self.processor.process_orderbook(raw_bids, raw_asks, current_price)
        if not processed:
            return

        if self._stack.currentWidget() is not self.plot:
            self._stack.setCurrentWidget(self.plot)

        bids = processed["bids_processed"]
        asks = processed["asks_processed"]
        if self.processor.aggregation_enabled:
            bid_x = [row[0] for row in bids]
            bid_y = [row[2] for row in bids]
            ask_x = [row[0] for row in asks]
            ask_y = [row[2] for row in asks]
            self.bids_line.setData(bid_x, bid_y)
            self.asks_line.setData(ask_x, ask_y)
            self._clear_bars()
        else:
            bid_x = [row[0] for row in bids]
            bid_y = [row[1] for row in bids]
            ask_x = [row[0] for row in asks]
            ask_y = [row[1] for row in asks]
            self.bids_line.setData([], [])
            self.asks_line.setData([], [])
            self._set_bars(bid_x, bid_y, ask_x, ask_y)

        x_min, x_max = processed["x_axis_limits"]
        y_min, y_max = processed["y_axis_limits"]
        self.plot.setXRange(x_min, x_max, padding=0.0)
        self.plot.setYRange(y_min, y_max, padding=0.02)

        best_bid = processed["best_bid"]
        best_ask = processed["best_ask"]
        ratio = processed["bid_ask_ratio"]
        self.ratio_label.setText(f"Bid/Ask {ratio:.2f}")
        self.best_bid_label.setText(f"Bid {best_bid:.2f}")
        self.best_ask_label.setText(f"Ask {best_ask:.2f}")
        self.spread_label.setText(f"Spread {best_ask - best_bid:.2f}")

    def _set_bars(self, bid_x, bid_y, ask_x, ask_y) -> None:
        self._clear_bars()
        self._bids_bars = pg.BarGraphItem(
            x=bid_x,
            height=bid_y,
            width=max(self.processor.tick_size, 1e-9) * 0.85,
            brush=(40, 210, 120, 160),
            pen=pg.mkPen((40, 210, 120), width=1),
        )
        self._asks_bars = pg.BarGraphItem(
            x=ask_x,
            height=ask_y,
            width=max(self.processor.tick_size, 1e-9) * 0.85,
            brush=(220, 80, 90, 160),
            pen=pg.mkPen((220, 80, 90), width=1),
        )
        self.plot.addItem(self._bids_bars)
        self.plot.addItem(self._asks_bars)

    def _clear_bars(self) -> None:
        if self._bids_bars is not None:
            self.plot.removeItem(self._bids_bars)
            self._bids_bars = None
        if self._asks_bars is not None:
            self.plot.removeItem(self._asks_bars)
            self._asks_bars = None

    def closeEvent(self, event):  # noqa: N802
        self.closed.emit()
        self._render_timer.stop()
        self._unsubscribe()
        self._unregister_handlers()
        self._clear_bars()
        super().closeEvent(event)
