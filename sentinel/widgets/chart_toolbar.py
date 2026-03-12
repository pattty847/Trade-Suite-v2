from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget


DEFAULT_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
DEFAULT_MODES = ["Candles", "Line", "Heikin Ashi"]


class ChartToolbar(QWidget):
    symbol_changed = Signal(str)
    timeframe_changed = Signal(str)
    mode_changed = Signal(str)
    bubbles_changed = Signal(bool)

    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str,
        mode: str,
        bubbles_enabled: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("chart-toolbar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(DEFAULT_SYMBOLS)
        self._set_combo_value(self.symbol_combo, symbol)
        self.symbol_combo.currentTextChanged.connect(self.symbol_changed.emit)
        layout.addWidget(self.symbol_combo)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(DEFAULT_TIMEFRAMES)
        self._set_combo_value(self.timeframe_combo, timeframe)
        self.timeframe_combo.currentTextChanged.connect(self.timeframe_changed.emit)
        layout.addWidget(self.timeframe_combo)

        self.mode_combo = QComboBox()
        _ic = "#6a85a8"
        self.mode_combo.addItems(DEFAULT_MODES)
        self.mode_combo.setItemIcon(0, qta.icon("mdi6.chart-box-outline", color=_ic))
        self.mode_combo.setItemIcon(1, qta.icon("mdi6.chart-line", color=_ic))
        self.mode_combo.setItemIcon(2, qta.icon("mdi6.chart-areaspline", color=_ic))
        self._set_combo_value(self.mode_combo, _normalize_mode_label(mode))
        self.mode_combo.currentTextChanged.connect(self.mode_changed.emit)
        layout.addWidget(self.mode_combo)

        self.bubbles_check = QCheckBox("Bubbles")
        self.bubbles_check.setChecked(bubbles_enabled)
        self.bubbles_check.toggled.connect(self.bubbles_changed.emit)
        layout.addWidget(self.bubbles_check)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer)

        self.context_label = QLabel("")
        self.context_label.setStyleSheet("color: #6a85a8; font-size: 11px;")
        layout.addWidget(self.context_label)
        self._update_context_label()

        self.symbol_changed.connect(lambda _value: self._update_context_label())
        self.timeframe_changed.connect(lambda _value: self._update_context_label())

    def symbol(self) -> str:
        return self.symbol_combo.currentText()

    def timeframe(self) -> str:
        return self.timeframe_combo.currentText()

    def mode(self) -> str:
        return self.mode_combo.currentText()

    def bubbles_enabled(self) -> bool:
        return self.bubbles_check.isChecked()

    def set_symbol(self, value: str) -> None:
        self._set_combo_value(self.symbol_combo, value)
        self._update_context_label()

    def set_timeframe(self, value: str) -> None:
        self._set_combo_value(self.timeframe_combo, value)
        self._update_context_label()

    def set_mode(self, value: str) -> None:
        self._set_combo_value(self.mode_combo, _normalize_mode_label(value))

    def set_bubbles_enabled(self, enabled: bool) -> None:
        self.bubbles_check.setChecked(enabled)

    def _update_context_label(self) -> None:
        self.context_label.setText(f"{self.symbol()} · {self.timeframe()}")

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx < 0:
            combo.addItem(value)
            idx = combo.findText(value)
        combo.setCurrentIndex(idx)


def _normalize_mode_label(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "line":
        return "Line"
    if normalized == "heikin ashi":
        return "Heikin Ashi"
    return "Candles"
