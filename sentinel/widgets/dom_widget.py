from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sentinel.analysis.orderbook_processor import OrderBookProcessor
from sentinel.core.signals import Signals


LOGGER = logging.getLogger(__name__)

_MONO_FONT = QFont()
_MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
_MONO_FONT.setPointSize(10)

_LABEL_FONT = QFont()
_LABEL_FONT.setStyleHint(QFont.StyleHint.Monospace)
_LABEL_FONT.setPointSize(9)

_MID_FONT = QFont(_MONO_FONT)
_MID_FONT.setBold(True)

_EPSILON = 1e-9


class DomDockWidget(QDockWidget):
    def __init__(
        self,
        *,
        instance_id: str,
        runtime,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        levels: int = 16,
        price_precision: float = 0.01,
        fps: int = 15,
    ) -> None:
        super().__init__(f"DOM - {exchange.upper()} {symbol}")
        self.instance_id = instance_id
        self.exchange = exchange
        self.symbol = symbol
        self.levels = levels
        self.runtime = None
        self._handlers_registered = False
        self._subscribed = False

        self.processor = OrderBookProcessor(price_precision=price_precision)
        self.processor.aggregation_enabled = True
        self.last_orderbook: dict[str, Any] | None = None
        self._dirty = False
        self._show_cumulative = True
        self._cell_cache: dict[tuple[int, int], tuple[str, str, str]] = {}

        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Tick"))
        self.tick_label = QLabel(f"{self.processor.tick_size:.8g}")
        self.tick_label.setFont(_LABEL_FONT)
        controls.addWidget(self.tick_label)
        dec_btn = QPushButton("-")
        inc_btn = QPushButton("+")
        dec_btn.setFixedWidth(26)
        inc_btn.setFixedWidth(26)
        dec_btn.clicked.connect(self._decrease_tick)
        inc_btn.clicked.connect(self._increase_tick)
        controls.addWidget(dec_btn)
        controls.addWidget(inc_btn)
        self.cumulative_checkbox = QCheckBox("Cumulative")
        self.cumulative_checkbox.setChecked(True)
        self.cumulative_checkbox.toggled.connect(self._on_toggle_cumulative)
        controls.addWidget(self.cumulative_checkbox)
        controls.addStretch(1)
        self.spread_label = QLabel("Spread: -")
        self.spread_label.setFont(_LABEL_FONT)
        controls.addWidget(self.spread_label)
        root.addLayout(controls)

        self.table = QTableWidget((self.levels * 2) + 1, 5)
        self.table.setHorizontalHeaderLabels(["Bid Cum", "Bid Qty", "Price", "Ask Qty", "Ask Cum"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(_MONO_FONT)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setShowGrid(False)
        root.addWidget(self.table, 1)

        self.setWidget(body)
        self.setMinimumWidth(300)
        self.setMaximumWidth(520)

        self._timer = QTimer(self)
        self._timer.setInterval(max(int(1000 / max(fps, 1)), 16))
        self._timer.timeout.connect(self._render_if_dirty)
        self._timer.start()
        self._apply_headers()

        self.set_runtime(runtime)

    def export_definition(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "widget_type": "dom",
            "config": {
                "exchange": self.exchange,
                "symbol": self.symbol,
                "levels": self.levels,
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
        self.runtime.core.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
        self._handlers_registered = True

    def _unregister_handlers(self) -> None:
        if not self._handlers_registered or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.emitter.unregister(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
        except Exception:
            pass
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
        LOGGER.debug("DOM subscribed: %s/%s", self.exchange, self.symbol)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("DOM unsubscribe failed: %s", exc)
        self._subscribed = False

    def _on_order_book_update(self, exchange: str, orderbook: dict) -> None:
        if exchange != self.exchange:
            return
        # Stream is per-symbol; if orderbook includes symbol, filter by it
        ob_symbol = orderbook.get("symbol")
        if ob_symbol is not None and ob_symbol != self.symbol:
            return
        self.last_orderbook = orderbook
        self._dirty = True

    def _current_mid_price(self) -> float | None:
        if not self.last_orderbook:
            return None
        bids = self.last_orderbook.get("bids", [])
        asks = self.last_orderbook.get("asks", [])
        if not bids or not asks:
            return None
        return (bids[0][0] + asks[0][0]) / 2

    def _increase_tick(self) -> None:
        new_tick = self.processor.increase_tick_size(self._current_mid_price())
        self.tick_label.setText(f"{new_tick:.8g}")
        self._dirty = True

    def _decrease_tick(self) -> None:
        new_tick = self.processor.decrease_tick_size(self._current_mid_price())
        self.tick_label.setText(f"{new_tick:.8g}")
        self._dirty = True

    def _on_toggle_cumulative(self, checked: bool) -> None:
        self._show_cumulative = checked
        self._apply_headers()
        self._dirty = True

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.last_orderbook:
            return
        self._dirty = False

        processed = self.processor.build_dom_ladder(
            self.last_orderbook.get("bids", []),
            self.last_orderbook.get("asks", []),
            self.levels,
            self._current_mid_price(),
        )
        if not processed:
            return

        rows = processed["rows"]
        for row_index, row in enumerate(rows):
            kind = row["kind"]
            has_bid_liquidity = row["bid_qty"] > _EPSILON
            has_ask_liquidity = row["ask_qty"] > _EPSILON
            bid_qty = self._format_quantity(row["bid_qty"]) if has_bid_liquidity else ""
            bid_cum = (
                self._format_quantity(row["bid_cum"])
                if has_bid_liquidity and self._show_cumulative
                else ""
            )
            ask_cum = (
                self._format_quantity(row["ask_cum"])
                if has_ask_liquidity and self._show_cumulative
                else ""
            )
            ask_qty = self._format_quantity(row["ask_qty"]) if has_ask_liquidity else ""
            price_val = f"{row['price']:.2f}" if kind != "mid" else f"{row['price']:.2f} MID"

            self._set_cell(row_index, 0, bid_cum, kind=kind, role="bid_cum", magnitude=row["bid_cum"])
            self._set_cell(row_index, 1, bid_qty, kind=kind, role="bid_qty", magnitude=row["bid_qty"])
            self._set_cell(row_index, 2, price_val, kind=kind, role="price", magnitude=0.0)
            self._set_cell(row_index, 3, ask_qty, kind=kind, role="ask_qty", magnitude=row["ask_qty"])
            self._set_cell(row_index, 4, ask_cum, kind=kind, role="ask_cum", magnitude=row["ask_cum"])

        spread = processed["best_ask"] - processed["best_bid"]
        self.spread_label.setText(f"Spread: {spread:.2f}")

        # Clear any extra rows if the ladder size changes in the future.
        for row_index in range(len(rows), self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self._set_cell(row_index, col, "", kind="empty", role="empty", magnitude=0.0)

    def _set_cell(self, row: int, col: int, text: str, *, kind: str, role: str, magnitude: float) -> None:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, col, item)
        fg, bg = self._cell_palette(kind=kind, role=role, magnitude=magnitude)
        cache_key = (row, col)
        state = (text, fg.name(QColor.NameFormat.HexArgb), bg.name(QColor.NameFormat.HexArgb))
        if self._cell_cache.get(cache_key) == state:
            return
        self._cell_cache[cache_key] = state

        item.setText(text)
        item.setForeground(fg)
        item.setBackground(bg)
        item.setFont(_MID_FONT if kind == "mid" else _MONO_FONT)
        if role == "price":
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        elif role.startswith("ask"):
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _cell_palette(self, *, kind: str, role: str, magnitude: float) -> tuple[QColor, QColor]:
        if kind == "mid":
            if role == "price":
                return QColor(248, 250, 252), QColor(74, 84, 96, 220)
            return QColor(238, 242, 247), QColor(74, 84, 96, 220)
        if kind == "ask":
            alpha = min(140, 24 + int(magnitude * 180))
            if role == "price":
                return QColor(215, 219, 224), QColor(78, 18, 24, 20)
            return QColor(230, 92, 104), QColor(120, 24, 36, alpha)
        if kind == "bid":
            alpha = min(140, 24 + int(magnitude * 180))
            if role == "price":
                return QColor(215, 219, 224), QColor(18, 56, 38, 20)
            return QColor(53, 190, 130), QColor(24, 94, 58, alpha)
        return QColor(160, 168, 176), QColor(0, 0, 0, 0)

    def _apply_headers(self) -> None:
        headers = ["Bid Cum", "Bid Qty", "Price", "Ask Qty", "Ask Cum"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnHidden(0, not self._show_cumulative)
        self.table.setColumnHidden(4, not self._show_cumulative)
        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            if self.table.isColumnHidden(col):
                continue
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

    def _format_quantity(self, value: float) -> str:
        if value <= _EPSILON:
            return ""
        if value < 0.0001:
            return "<0.0001"
        return f"{value:,.4f}"

    def resizeEvent(self, event):  # noqa: N802
        self._apply_headers()
        super().resizeEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self._timer.stop()
        self._unsubscribe()
        self._unregister_handlers()
        super().closeEvent(event)
