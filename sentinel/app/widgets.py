"""Reusable Qt building blocks for the Sentinel UI.

Small, dock-agnostic widgets that need to look the same across panels — empty
state placeholders and a live data freshness badge. Keeping them here avoids
re-creating bespoke versions inside every dock widget.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EmptyState(QWidget):
    """Centered placeholder rendered when a dock has no data yet.

    The visual treatment lives in `theme.qss` under `#empty-state-label`
    and `#empty-state-hint`. Use :meth:`set_label` / :meth:`set_hint` to
    update text in place; the widget itself stays mounted in the parent
    layout so its position doesn't shift between states.
    """

    def __init__(
        self,
        label: str = "WAITING FOR FEED",
        hint: str | None = "Streaming data will appear here.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("empty-state")

        self._label = QLabel(label.upper())
        self._label.setObjectName("empty-state-label")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hint = QLabel(hint or "")
        self._hint.setObjectName("empty-state-hint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setVisible(bool(hint))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(4)
        layout.addStretch(1)
        layout.addWidget(self._label)
        layout.addWidget(self._hint)
        layout.addStretch(1)

    def set_label(self, text: str) -> None:
        self._label.setText(text.upper())

    def set_hint(self, text: str | None) -> None:
        self._hint.setText(text or "")
        self._hint.setVisible(bool(text))


class LiveBadge(QLabel):
    """Compact freshness indicator: 'LIVE', '1.4s', or 'STALE'.

    Call :meth:`mark_update` whenever fresh upstream data lands. A 500 ms
    timer decays the badge through three states (``ok`` → ``warn`` →
    ``err``) so a stuck feed is visible without spamming logs. The state
    is exposed via the ``state`` dynamic property so QSS styles it.
    """

    OK_AFTER_S    = 2.0
    WARN_AFTER_S  = 6.0
    STALE_AFTER_S = 15.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("live-badge")
        self._set_state("idle", "OFFLINE")
        self._last_update: float | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def mark_update(self) -> None:
        self._last_update = time.monotonic()
        self._refresh()

    def _refresh(self) -> None:
        if self._last_update is None:
            return
        age = time.monotonic() - self._last_update
        if age < self.OK_AFTER_S:
            self._set_state("ok", "● LIVE")
        elif age < self.WARN_AFTER_S:
            self._set_state("warn", f"● {age:.1f}s")
        elif age < self.STALE_AFTER_S:
            self._set_state("warn", f"● {age:.0f}s")
        else:
            self._set_state("err", "● STALE")

    def _set_state(self, state: str, text: str) -> None:
        if self.text() != text:
            self.setText(text)
        if self.property("state") != state:
            self.setProperty("state", state)
            # Force QSS re-evaluation since dynamic properties don't
            # trigger restyle automatically.
            self.style().unpolish(self)
            self.style().polish(self)

    def shutdown(self) -> None:
        self._timer.stop()
