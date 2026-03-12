from __future__ import annotations

import logging
import math
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from sentinel.analysis.orderbook_processor import OrderBookProcessor
from sentinel.core.signals import Signals
from sentinel.widgets.chart_pane import ChartPane


LOGGER = logging.getLogger(__name__)

_MONO_FONT = QFont()
_MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
_MONO_FONT.setPointSize(10)

_HEADER_FONT = QFont(_MONO_FONT)
_HEADER_FONT.setPointSize(9)
_HEADER_FONT.setBold(True)

_MID_FONT = QFont(_MONO_FONT)
_MID_FONT.setBold(True)

_GRID_PEN = QPen(QColor("#162231"))
_MID_BG = QColor(74, 84, 96, 220)
_MID_FG = QColor(248, 250, 252)
_ASK_FG = QColor(230, 92, 104)
_BID_FG = QColor(53, 190, 130)
_PRICE_FG = QColor(214, 220, 228)
_TARGET_ROW_HEIGHT_PX = 20.0
_MIN_ROW_HEIGHT_PX = 16.0
_MAX_ROW_HEIGHT_PX = 28.0


class LadderCanvas(QWidget):
    def __init__(self, chart_pane: ChartPane | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chart_pane = chart_pane
        self._rows: list[dict[str, float | str]] = []
        self._price_range: tuple[float, float] | None = None
        self._last_price: float | None = None
        self.setMinimumWidth(260)

    def set_rows(self, rows: list[dict[str, float | str]]) -> None:
        self._rows = rows
        self.update()

    def set_price_range(self, price_min: float, price_max: float) -> None:
        self._price_range = (float(price_min), float(price_max))
        self.update()

    def set_last_price(self, value: float | None) -> None:
        self._last_price = None if value is None else float(value)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#060a11"))
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        width = self.width()
        height = self.height()
        price_w = int(width * 0.38)
        size_w = int(width * 0.26)
        total_w = width - price_w - size_w
        price_x = 0
        size_x = price_x + price_w
        total_x = size_x + size_w

        painter.setPen(_GRID_PEN)
        painter.drawLine(size_x, 0, size_x, height)
        painter.drawLine(total_x, 0, total_x, height)

        if self._price_range and self._last_price is not None:
            y = self._price_to_y(self._last_price, height)
            painter.setPen(QPen(QColor("#d6dde6"), 1))
            painter.drawLine(0, int(y), width, int(y))

        row_h = self._row_height(height)
        max_size = max((float(row.get("size", 0)) for row in self._rows if row.get("kind") != "mid"), default=0.0)
        max_total = max((float(row.get("total", 0)) for row in self._rows if row.get("kind") != "mid"), default=0.0)

        for row in self._rows:
            price = float(row["price"])
            y_center = self._price_to_y(price, height)
            top = int(round(y_center - (row_h / 2)))
            bottom = int(round(y_center + (row_h / 2)))
            rect = QRectF(0, top, width, max(bottom - top, 1))
            kind = str(row["kind"])

            if kind == "mid":
                painter.fillRect(rect, _MID_BG)
                price_fg = _MID_FG
                value_fg = _MID_FG
                font = _MID_FONT
            elif kind == "ask":
                painter.fillRect(rect, QColor(64, 12, 18, 90))
                if max_size > 0:
                    bar_w = (float(row.get("size", 0)) / max_size) * size_w
                    painter.fillRect(QRectF(size_x + size_w - bar_w, top, bar_w, rect.height()), QColor(230, 92, 104, 35))
                if max_total > 0:
                    bar_w = (float(row.get("total", 0)) / max_total) * total_w
                    painter.fillRect(QRectF(total_x + total_w - bar_w, top, bar_w, rect.height()), QColor(230, 92, 104, 25))
                price_fg = _PRICE_FG
                value_fg = _ASK_FG
                font = _MONO_FONT
            else:
                painter.fillRect(rect, QColor(14, 48, 34, 80))
                if max_size > 0:
                    bar_w = (float(row.get("size", 0)) / max_size) * size_w
                    painter.fillRect(QRectF(size_x + size_w - bar_w, top, bar_w, rect.height()), QColor(53, 190, 130, 35))
                if max_total > 0:
                    bar_w = (float(row.get("total", 0)) / max_total) * total_w
                    painter.fillRect(QRectF(total_x + total_w - bar_w, top, bar_w, rect.height()), QColor(53, 190, 130, 25))
                price_fg = _PRICE_FG
                value_fg = _BID_FG
                font = _MONO_FONT

            painter.setFont(font)
            price_text = f"{price:.2f}" if kind != "mid" else f"{price:.2f}"
            size_text = "" if float(row["size"]) <= 0 else _format_size(float(row["size"]))
            total_text = "" if float(row["total"]) <= 0 else _format_size(float(row["total"]))

            painter.setPen(price_fg)
            painter.drawText(
                QRectF(price_x + 8, top, price_w - 16, rect.height()),
                Qt.AlignVCenter | Qt.AlignCenter,
                price_text,
            )
            painter.setPen(value_fg)
            painter.drawText(
                QRectF(size_x + 8, top, size_w - 16, rect.height()),
                Qt.AlignVCenter | Qt.AlignRight,
                size_text,
            )
            painter.drawText(
                QRectF(total_x + 8, top, total_w - 16, rect.height()),
                Qt.AlignVCenter | Qt.AlignRight,
                total_text,
            )

        painter.end()

    def _price_to_y(self, price: float, height: int) -> float:
        if self.chart_pane is not None:
            try:
                vb = self.chart_pane.price_plot.getViewBox()
                scene_pos = vb.mapViewToScene(QPointF(0.0, price))
                if scene_pos is not None:
                    widget_pos = self.chart_pane.price_plot.mapFromScene(scene_pos)
                    qp = QPoint(int(widget_pos.x()), int(widget_pos.y()))
                    global_pos = self.chart_pane.price_plot.mapToGlobal(qp)
                    local_pos = self.mapFromGlobal(global_pos)
                    return float(local_pos.y())
            except Exception as e:
                LOGGER.debug("Failed mapping ViewBox Y: %s", e)

        if not self._price_range:
            return height / 2
        low, high = self._price_range
        span = max(high - low, 1e-9)
        norm = (high - price) / span
        return max(0.0, min(height - 1.0, norm * height))

    def _row_height(self, height: int) -> float:
        if not self._rows or not self._price_range:
            return _TARGET_ROW_HEIGHT_PX
        low, high = self._price_range
        span = max(high - low, 1e-9)
        prices = sorted({float(row["price"]) for row in self._rows}, reverse=True)
        if len(prices) < 2:
            return _TARGET_ROW_HEIGHT_PX
        tick = min(
            prices[index] - prices[index + 1]
            for index in range(len(prices) - 1)
            if prices[index] > prices[index + 1]
        )
        if tick <= 0:
            return _TARGET_ROW_HEIGHT_PX
            
        if self.chart_pane is not None:
            y1 = self._price_to_y(prices[0], height)
            y2 = self._price_to_y(prices[0] - tick, height)
            calc_height = float(abs(y2 - y1))
            if calc_height > 0:
                return max(calc_height, 1.0)
                
        return max((tick * height) / span, 1.0)


class OrderflowLadderPane(QWidget):
    def __init__(
        self,
        *,
        chart_pane: ChartPane | None = None,
        exchange: str,
        symbol: str,
        price_precision: float = 0.01,
        fps: int = 15,
    ) -> None:
        super().__init__()
        self.chart_pane = chart_pane
        self.exchange = exchange
        self.symbol = symbol
        self.processor = OrderBookProcessor(price_precision=price_precision)
        self.processor.aggregation_enabled = True
        self._price_precision = float(price_precision)
        self.last_orderbook: dict[str, Any] | None = None
        self._price_range: tuple[float, float] | None = None
        self._last_price: float | None = None
        self._dirty = False
        self._tick_mode = "auto"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(8, 6, 8, 6)
        controls_layout.addWidget(QLabel("Tick"))
        self.tick_label = QLabel(f"{self.processor.tick_size:.8g}")
        self.tick_label.setFont(_HEADER_FONT)
        controls_layout.addWidget(self.tick_label)
        self.mode_button = QPushButton("Auto")
        self.mode_button.setCheckable(True)
        self.mode_button.setChecked(True)
        self.mode_button.clicked.connect(self._toggle_tick_mode)
        controls_layout.addWidget(self.mode_button)
        self.dec_btn = QPushButton("-")
        self.inc_btn = QPushButton("+")
        self.dec_btn.setFixedWidth(26)
        self.inc_btn.setFixedWidth(26)
        self.dec_btn.clicked.connect(self._decrease_tick)
        self.inc_btn.clicked.connect(self._increase_tick)
        controls_layout.addWidget(self.dec_btn)
        controls_layout.addWidget(self.inc_btn)
        controls_layout.addStretch(1)
        self.spread_label = QLabel("Spread: -")
        self.spread_label.setFont(_HEADER_FONT)
        controls_layout.addWidget(self.spread_label)
        root.addWidget(controls)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        for text, stretch, align in (("Price", 38, Qt.AlignCenter), ("Size", 26, Qt.AlignRight), ("Total", 36, Qt.AlignRight)):
            label = QLabel(text)
            label.setFont(_HEADER_FONT)
            label.setStyleSheet("color: #8fa4c2;")
            label.setAlignment(Qt.AlignVCenter | align)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            header_layout.addWidget(label, stretch)
        root.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #162231;")
        root.addWidget(line)

        self.canvas = LadderCanvas(chart_pane=chart_pane)
        root.addWidget(self.canvas, 1)

        self._render_timer = QTimer(self)
        self._render_timer.setInterval(max(int(1000 / max(fps, 1)), 16))
        self._render_timer.timeout.connect(self._render_if_dirty)
        self._render_timer.start()

    @property
    def tick_size(self) -> float:
        return float(self.processor.tick_size)

    @property
    def tick_mode(self) -> str:
        return self._tick_mode

    def set_market(self, exchange: str, symbol: str) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.last_orderbook = None
        self._dirty = True

    def set_orderbook(self, orderbook: dict[str, Any] | None) -> None:
        self.last_orderbook = orderbook
        self._dirty = True

    def set_visible_price_range(self, price_min: float, price_max: float) -> None:
        self._price_range = (float(price_min), float(price_max))
        self.canvas.set_price_range(price_min, price_max)
        self._apply_auto_tick_if_needed()
        self._dirty = True

    def set_last_price(self, value: float | None) -> None:
        self._last_price = None if value is None else float(value)
        self.canvas.set_last_price(self._last_price)
        self._apply_auto_tick_if_needed()

    def _increase_tick(self) -> None:
        self._set_tick_mode("manual")
        self.processor.increase_tick_size(self._last_price)
        self.tick_label.setText(f"{self.processor.tick_size:.8g}")
        self._dirty = True

    def _decrease_tick(self) -> None:
        self._set_tick_mode("manual")
        self.processor.decrease_tick_size(self._last_price)
        if self.processor.tick_size < self._price_precision:
            self.processor.set_tick_size(self._price_precision)
        self.tick_label.setText(f"{self.processor.tick_size:.8g}")
        self._dirty = True

    def _toggle_tick_mode(self, checked: bool) -> None:
        self._set_tick_mode("auto" if checked else "manual")

    def _set_tick_mode(self, mode: str) -> None:
        self._tick_mode = mode
        auto_enabled = mode == "auto"
        self.mode_button.blockSignals(True)
        self.mode_button.setChecked(auto_enabled)
        self.mode_button.setText("Auto" if auto_enabled else "Manual")
        self.mode_button.blockSignals(False)
        self.dec_btn.setEnabled(not auto_enabled)
        self.inc_btn.setEnabled(not auto_enabled)
        if auto_enabled:
            self._apply_auto_tick_if_needed(force=True)
        self._dirty = True

    def _apply_auto_tick_if_needed(self, *, force: bool = False) -> None:
        if self._tick_mode != "auto" or self._price_range is None:
            return
        price_min, price_max = self._price_range
        new_tick = choose_auto_tick_size(
            price_min=price_min,
            price_max=price_max,
            ladder_height_px=max(self.canvas.height(), 1),
            current_tick=self.processor.tick_size,
            presets=self.processor.calculate_tick_presets(self._last_price or 0.0),
            minimum_tick=self._price_precision,
            force=force,
        )
        if not math.isclose(new_tick, float(self.processor.tick_size), rel_tol=0.0, abs_tol=1e-12):
            self.processor.set_tick_size(new_tick)
            self.tick_label.setText(f"{self.processor.tick_size:.8g}")
            self._dirty = True

    def _render_if_dirty(self) -> None:
        if not self._dirty or not self.last_orderbook or self._price_range is None:
            return
        self._dirty = False

        price_min, price_max = self._price_range
        ladder = self.processor.build_visible_ladder(
            self.last_orderbook.get("bids", []),
            self.last_orderbook.get("asks", []),
            price_min=price_min,
            price_max=price_max,
            current_price=self._last_price,
        )
        if not ladder:
            self.canvas.set_rows([])
            return

        self.spread_label.setText(f"Spread: {ladder['best_ask'] - ladder['best_bid']:.2f}")
        self.canvas.set_rows(self._build_visible_tick_rows(ladder))

    def _build_visible_tick_rows(self, ladder: dict[str, Any]) -> list[dict[str, float | str]]:
        if self._price_range is None:
            return ladder["rows"]

        price_min, price_max = self._price_range
        lower = min(price_min, price_max)
        upper = max(price_min, price_max)
        tick = max(float(self.processor.tick_size), self._price_precision)
        anchor_price = self._last_price if self._last_price is not None else float(ladder["midpoint"])
        center_price = round(round(anchor_price / tick) * tick, 10)

        asks_by_price = {
            round(float(row["price"]), 10): row
            for row in ladder["rows"]
            if row["kind"] == "ask"
        }
        bids_by_price = {
            round(float(row["price"]), 10): row
            for row in ladder["rows"]
            if row["kind"] == "bid"
        }

        top_price = round(math.floor(upper / tick) * tick, 10)
        bottom_price = round(math.ceil(lower / tick) * tick, 10)
        if top_price < bottom_price:
            return [{"kind": "mid", "price": center_price, "size": 0.0, "total": 0.0}]

        rows: list[dict[str, float | str]] = []
        price = top_price
        while price >= bottom_price - 1e-9:
            normalized_price = round(price, 10)
            if normalized_price > center_price:
                rows.append(
                    asks_by_price.get(
                        normalized_price,
                        {"kind": "ask", "price": normalized_price, "size": 0.0, "total": 0.0},
                    )
                )
            elif normalized_price < center_price:
                rows.append(
                    bids_by_price.get(
                        normalized_price,
                        {"kind": "bid", "price": normalized_price, "size": 0.0, "total": 0.0},
                    )
                )
            else:
                rows.append({"kind": "mid", "price": center_price, "size": 0.0, "total": 0.0})
            price = round(price - tick, 10)

        if not any(str(row["kind"]) == "mid" for row in rows):
            rows.append({"kind": "mid", "price": center_price, "size": 0.0, "total": 0.0})
            rows.sort(key=lambda row: float(row["price"]), reverse=True)
        return rows

    def shutdown(self) -> None:
        self._render_timer.stop()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_auto_tick_if_needed()


class ChartOrderflowDockWidget(QDockWidget):
    def __init__(
        self,
        *,
        instance_id: str,
        runtime,
        exchange: str = "coinbase",
        symbol: str = "BTC/USD",
        timeframe: str = "1m",
        price_precision: float = 0.01,
        fps: int = 15,
    ) -> None:
        super().__init__(f"Chart+Orderflow - {exchange.upper()} {symbol} ({timeframe})")
        self.instance_id = instance_id
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.runtime = None
        self._handlers_registered = False
        self._subscribed = False

        self.setObjectName(f"dock:{instance_id}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        splitter = QSplitter(Qt.Horizontal)
        self.chart_pane = ChartPane(
            runtime=runtime,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            fps=fps,
            show_price_axis=False,
        )
        self.ladder_pane = OrderflowLadderPane(
            chart_pane=self.chart_pane,
            exchange=exchange,
            symbol=symbol,
            price_precision=price_precision,
            fps=fps,
        )
        splitter.addWidget(self.chart_pane)
        splitter.addWidget(self.ladder_pane)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([1120, 320])
        self.setWidget(splitter)

        self.chart_pane.visible_price_range_changed.connect(self.ladder_pane.set_visible_price_range)
        self.chart_pane.last_price_changed.connect(self.ladder_pane.set_last_price)

        self.set_runtime(runtime)

    def export_definition(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "widget_type": "chart_orderflow",
            "config": {
                "exchange": self.exchange,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "tick_size": self.ladder_pane.tick_size,
            },
        }

    def set_runtime(self, runtime) -> None:
        self.runtime = runtime
        self.chart_pane.set_runtime(runtime)
        if runtime is None or runtime.core is None:
            return
        self._register_handlers()
        self._subscribe()
        if self.chart_pane.current_last_price() is not None:
            self.ladder_pane.set_last_price(self.chart_pane.current_last_price())
        price_min, price_max = self.chart_pane.visible_price_range()
        self.ladder_pane.set_visible_price_range(price_min, price_max)

    def change_subscription(self, exchange: str, symbol: str, timeframe: str) -> None:
        if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:
            return
        self._unsubscribe()
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.chart_pane.change_subscription(exchange, symbol, timeframe)
        self.ladder_pane.set_market(exchange, symbol)
        self.setWindowTitle(f"Chart+Orderflow - {exchange.upper()} {symbol} ({timeframe})")
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
        LOGGER.debug("Chart+Orderflow subscribed: %s/%s", self.exchange, self.symbol)

    def _unsubscribe(self) -> None:
        if not self._subscribed or self.runtime is None or self.runtime.core is None:
            return
        try:
            self.runtime.core.task_manager.unsubscribe(self)
        except Exception as exc:
            LOGGER.warning("Chart+Orderflow unsubscribe failed: %s", exc)
        self._subscribed = False

    def _on_order_book_update(self, exchange: str, orderbook: dict[str, Any]) -> None:
        if exchange != self.exchange:
            return
        ob_symbol = orderbook.get("symbol")
        if ob_symbol is not None and ob_symbol != self.symbol:
            return
        self.ladder_pane.set_orderbook(orderbook)

    def closeEvent(self, event):  # noqa: N802
        self.ladder_pane.shutdown()
        self._unsubscribe()
        self._unregister_handlers()
        self.chart_pane.shutdown()
        super().closeEvent(event)


def _format_size(value: float) -> str:
    if value <= 0:
        return ""
    if value < 0.0001:
        return "<0.0001"
    return f"{value:,.4f}"


def choose_auto_tick_size(
    *,
    price_min: float,
    price_max: float,
    ladder_height_px: int,
    current_tick: float,
    presets: list[float],
    minimum_tick: float,
    force: bool = False,
) -> float:
    span = max(abs(float(price_max) - float(price_min)), minimum_tick)
    height = max(int(ladder_height_px), 1)
    target_rows = max(12, int(height / _TARGET_ROW_HEIGHT_PX))
    ideal_tick = max(span / max(target_rows, 1), minimum_tick)

    normalized_presets = sorted({max(float(p), minimum_tick) for p in presets if float(p) > 0})
    if not normalized_presets:
        normalized_presets = [minimum_tick]

    candidate = normalized_presets[-1]
    for preset in normalized_presets:
        if preset >= ideal_tick:
            candidate = preset
            break

    current = max(float(current_tick), minimum_tick)
    if force:
        return candidate

    current_row_height = (height * current) / span
    if _MIN_ROW_HEIGHT_PX <= current_row_height <= _MAX_ROW_HEIGHT_PX:
        return current
    if current_row_height < _MIN_ROW_HEIGHT_PX:
        return candidate if candidate >= current else current
    if current_row_height > _MAX_ROW_HEIGHT_PX:
        smaller = minimum_tick
        for preset in normalized_presets:
            if preset < current:
                smaller = preset
            else:
                break
        return smaller
    return current
