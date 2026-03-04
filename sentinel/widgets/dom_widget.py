from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
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

from trade_suite.analysis.orderbook_processor import OrderBookProcessor
from trade_suite.core.signals import Signals


LOGGER = logging.getLogger(__name__)


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

        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Tick"))
        self.tick_label = QLabel(f"{self.processor.tick_size:.8g}")
        controls.addWidget(self.tick_label)
        dec_btn = QPushButton("-")
        inc_btn = QPushButton("+")
        dec_btn.clicked.connect(self._decrease_tick)
        inc_btn.clicked.connect(self._increase_tick)
        controls.addWidget(dec_btn)
        controls.addWidget(inc_btn)
        controls.addStretch(1)
        self.spread_label = QLabel("Spread: -")
        controls.addWidget(self.spread_label)
        root.addLayout(controls)

        self.table = QTableWidget(self.levels, 5)
        self.table.setHorizontalHeaderLabels(["Bid Qty", "Bid Cum", "Price", "Ask Cum", "Ask Qty"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        self.setWidget(body)
        self.setMinimumWidth(300)
        self.setMaximumWidth(520)

        self._timer = QTimer(self)
        self._timer.setInterval(max(int(1000 / max(fps, 1)), 16))
        self._timer.timeout.connect(self._render_if_dirty)
        self._timer.start()
        self._apply_table_width_constraints()

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
        LOGGER.info("DOM subscribed: %s/%s", self.exchange, self.symbol)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("DOM unsubscribe failed: %s", exc)
        self._subscribed = False

    def _on_order_book_update(self, exchange: str, orderbook: dict) -> None:
        if exchange != self.exchange or orderbook.get("symbol") != self.symbol:
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

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.last_orderbook:
            return
        self._dirty = False

        processed = self.processor.process_orderbook(
            self.last_orderbook.get("bids", []),
            self.last_orderbook.get("asks", []),
            self._current_mid_price(),
        )
        if not processed:
            return

        bids = processed["bids_processed"][: self.levels]
        asks = processed["asks_processed"][: self.levels]

        for row in range(self.levels):
            bid = bids[row] if row < len(bids) else None
            ask = asks[row] if row < len(asks) else None

            bid_qty = f"{bid[1]:,.4f}" if bid else ""
            bid_cum = f"{bid[2]:,.4f}" if bid else ""
            ask_cum = f"{ask[2]:,.4f}" if ask else ""
            ask_qty = f"{ask[1]:,.4f}" if ask else ""
            price_val = ""
            if bid and ask:
                price_val = f"{(bid[0] + ask[0]) / 2:.2f}"
            elif bid:
                price_val = f"{bid[0]:.2f}"
            elif ask:
                price_val = f"{ask[0]:.2f}"

            self._set_cell(row, 0, bid_qty, color_role="bid")
            self._set_cell(row, 1, bid_cum, color_role="bid")
            self._set_cell(row, 2, price_val, color_role="mid")
            self._set_cell(row, 3, ask_cum, color_role="ask")
            self._set_cell(row, 4, ask_qty, color_role="ask")

        spread = processed["best_ask"] - processed["best_bid"]
        self.spread_label.setText(f"Spread: {spread:.2f}")
        self._apply_table_width_constraints()

    def _set_cell(self, row: int, col: int, text: str, color_role: str = "mid") -> None:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, col, item)
        item.setText(text)
        if color_role == "bid":
            item.setForeground(QColor(53, 190, 130))
        elif color_role == "ask":
            item.setForeground(QColor(230, 92, 104))
        else:
            item.setForeground(QColor(210, 214, 220))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _apply_table_width_constraints(self) -> None:
        self.table.resizeColumnsToContents()
        col_total = sum(self.table.columnWidth(i) for i in range(self.table.columnCount()))
        frame = self.table.frameWidth() * 2
        vheader = self.table.verticalHeader().width()
        scrollbar = self.table.verticalScrollBar().sizeHint().width()
        spacing = 32
        minimum = col_total + frame + vheader + scrollbar + spacing
        self.setMinimumWidth(max(360, minimum))
        self.setMaximumWidth(max(560, minimum + 80))

    def closeEvent(self, event):  # noqa: N802
        self._timer.stop()
        self._unsubscribe()
        self._unregister_handlers()
        super().closeEvent(event)
