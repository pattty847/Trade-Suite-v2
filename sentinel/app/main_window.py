import logging

import pyqtgraph as pg
import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QSizePolicy, QToolBar, QWidget
from qasync import asyncClose

from sentinel.app.layout_manager import LayoutManager
from sentinel.app.runtime import SentinelRuntime
from sentinel.app.theme import Colors, load_qss
from sentinel.app.widget_registry import WidgetRegistry
from sentinel.widgets.chart_orderflow_widget import ChartOrderflowDockWidget
from sentinel.widgets.chart_widget import ChartDockWidget
from sentinel.widgets.dom_widget import DomDockWidget
from sentinel.widgets.orderbook_widget import OrderbookDockWidget


LOGGER = logging.getLogger(__name__)


_DOT_GLYPH = "•  "   # bullet + two non-breaking spaces


def _set_status_state(label: QLabel, state: str, text: str) -> None:
    """Update a status dot's [state] property so QSS reapplies the right color."""
    label.setText(f"{_DOT_GLYPH}{text}")
    label.setProperty("state", state)
    label.style().unpolish(label)
    label.style().polish(label)


class SentinelMainWindow(QMainWindow):
    def __init__(self, app_version: str, runtime: SentinelRuntime | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"Sentinel · v{app_version}")
        self.resize(1600, 900)
        self.setDockNestingEnabled(True)
        self.runtime = runtime
        self._app_version = app_version

        self.layout_manager = LayoutManager(app_version=app_version)
        self.widget_registry = WidgetRegistry(self)

        self._apply_theme()
        self._build_global_toolbar()
        self._build_left_toolbar()
        self._build_menus()
        self._bootstrap_layout()
        self._setup_status()

    def _apply_theme(self) -> None:
        # Set pyqtgraph defaults before any plots are created.
        pg.setConfigOptions(
            foreground=Colors.TEXT_MUTED,
            background=Colors.BG_CANVAS,
            antialias=True,
        )

        self.setStyleSheet(load_qss())

    def _build_global_toolbar(self) -> None:
        bar = QToolBar("Global")
        bar.setObjectName("toolbar:global")
        bar.setMovable(False)
        bar.setIconSize(QSize(16, 16))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)

        brand = QLabel("SENTINEL")
        brand.setObjectName("brand")
        bar.addWidget(brand)

        version = QLabel(f"v{self._app_version}")
        version.setObjectName("brand-version")
        bar.addWidget(version)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        save_act = QAction(
            qta.icon("mdi6.content-save-outline", color=Colors.TEXT_DIM),
            "Save Layout",
            self,
        )
        save_act.setToolTip("Save layout  (Ctrl+S)")
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._save_layout)
        bar.addAction(save_act)

        reset_act = QAction(
            qta.icon("mdi6.restore", color=Colors.TEXT_DIM),
            "Reset Layout",
            self,
        )
        reset_act.setToolTip("Reset to default layout")
        reset_act.triggered.connect(self._reset_layout)
        bar.addAction(reset_act)

    def _build_left_toolbar(self) -> None:
        bar = QToolBar("Drawing")
        bar.setObjectName("toolbar:drawing")
        bar.setMovable(False)
        bar.setOrientation(Qt.Orientation.Vertical)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, bar)

        # Drawing tools are visual placeholders for now — the cursor entry is
        # active by default and the others are reserved for future wiring.
        tools = [
            ("Cursor",    "mdi6.cursor-default-outline", "Cursor"),
            ("Crosshair", "mdi6.crosshairs",             "Crosshair"),
            None,  # separator
            ("Trend",     "mdi6.trending-up",            "Trend line  (coming soon)"),
            ("Ray",       "mdi6.ray-start-arrow",        "Ray  (coming soon)"),
            ("HLine",     "mdi6.minus",                  "Horizontal line  (coming soon)"),
            ("Fib",       "mdi6.sine-wave",              "Fibonacci  (coming soon)"),
            ("Text",      "mdi6.format-text",            "Text annotation  (coming soon)"),
        ]

        group = QActionGroup(self)
        group.setExclusive(True)
        first = True
        for entry in tools:
            if entry is None:
                bar.addSeparator()
                continue
            name, icon_id, tooltip = entry
            act = QAction(
                qta.icon(icon_id, color=Colors.TEXT_FAINT, color_active=Colors.ACCENT),
                name,
                self,
            )
            act.setToolTip(tooltip)
            act.setCheckable(True)
            if first:
                act.setChecked(True)
                first = False
            group.addAction(act)
            bar.addAction(act)

    def _build_menus(self) -> None:
        menu = self.menuBar()
        _ic = Colors.TEXT_DIM

        # ── File menu ────────────────────────────────────────────────
        file_menu = menu.addMenu("File")

        save_layout_action = QAction(
            qta.icon("mdi6.content-save-outline", color=_ic), "Save Layout", self
        )
        save_layout_action.setShortcut(QKeySequence.StandardKey.Save)
        save_layout_action.triggered.connect(self._save_layout)
        file_menu.addAction(save_layout_action)

        reset_layout_action = QAction(
            qta.icon("mdi6.restore", color=_ic), "Reset Layout", self
        )
        reset_layout_action.triggered.connect(self._reset_layout)
        file_menu.addAction(reset_layout_action)

        file_menu.addSeparator()
        exit_action = QAction(qta.icon("mdi6.exit-to-app", color=_ic), "Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ── Widgets menu ─────────────────────────────────────────────
        widgets_menu = menu.addMenu("Widgets")

        new_chart_action = QAction(
            qta.icon("mdi6.chart-candlestick", color=_ic), "New Chart", self
        )
        new_chart_action.setShortcut(QKeySequence("Ctrl+Alt+C"))
        new_chart_action.triggered.connect(self._on_new_chart)
        widgets_menu.addAction(new_chart_action)

        new_chart_orderflow_action = QAction(
            qta.icon("mdi6.chart-box-outline", color=_ic), "New Chart + Orderflow", self
        )
        new_chart_orderflow_action.setShortcut(QKeySequence("Ctrl+Alt+O"))
        new_chart_orderflow_action.triggered.connect(self._on_new_chart_orderflow)
        widgets_menu.addAction(new_chart_orderflow_action)

        new_equity_chart_action = QAction(
            qta.icon("mdi6.finance", color=_ic), "New Equity Chart", self
        )
        new_equity_chart_action.triggered.connect(self._on_new_equity_chart)
        widgets_menu.addAction(new_equity_chart_action)

        widgets_menu.addSeparator()

        new_dom_action = QAction(
            qta.icon("mdi6.table-of-contents", color=_ic), "New DOM", self
        )
        new_dom_action.setShortcut(QKeySequence("Ctrl+Alt+D"))
        new_dom_action.triggered.connect(self._on_new_dom)
        widgets_menu.addAction(new_dom_action)

        new_orderbook_action = QAction(
            qta.icon("mdi6.book-open-outline", color=_ic), "New Orderbook", self
        )
        new_orderbook_action.triggered.connect(self._on_new_orderbook)
        widgets_menu.addAction(new_orderbook_action)

    def _bootstrap_layout(self) -> None:
        self.widget_registry.load_or_create_defaults()
        restored = self.layout_manager.restore_layout(self)
        if not restored:
            self._arrange_default_docks()
        self._ensure_chart_visible()

    def _arrange_default_docks(self) -> None:
        docks = list(self.widget_registry.docks.values())
        if not docks:
            return

        chart = next((dock for dock in docks if isinstance(dock, ChartDockWidget)), None)
        chart_orderflow = next(
            (dock for dock in docks if isinstance(dock, ChartOrderflowDockWidget)),
            None,
        )
        dom = next((dock for dock in docks if isinstance(dock, DomDockWidget)), None)
        depth = next((dock for dock in docks if isinstance(dock, OrderbookDockWidget)), None)

        primary_chart = chart_orderflow or chart
        if primary_chart is not None:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, primary_chart)
        if chart is not None and chart_orderflow is not None:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, chart)
            self.tabifyDockWidget(primary_chart, chart)
            chart.hide()
        if dom is not None:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dom)
        if depth is not None:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, depth)
            if dom is not None:
                self.splitDockWidget(dom, depth, Qt.Orientation.Vertical)
                self.resizeDocks([dom, depth], [560, 340], Qt.Orientation.Vertical)
        if primary_chart is not None and (dom is not None or depth is not None):
            right_anchor = dom if dom is not None else depth
            self.resizeDocks([primary_chart, right_anchor], [1280, 380], Qt.Orientation.Horizontal)

    def _ensure_chart_visible(self) -> None:
        chart = next(
            (
                dock
                for dock in self.widget_registry.docks.values()
                if isinstance(dock, (ChartDockWidget, ChartOrderflowDockWidget))
            ),
            None,
        )
        if chart is None:
            return
        if self.dockWidgetArea(chart) == Qt.DockWidgetArea.NoDockWidgetArea:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, chart)
        if not chart.isVisible():
            chart.show()

    def _on_new_equity_chart(self) -> None:
        self.widget_registry.add_equity_chart(
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
        )

    def _on_new_placeholder(self) -> None:
        count = len(self.widget_registry.docks) + 1
        self.widget_registry.add_placeholder(
            title=f"Placeholder {count}",
            area=Qt.DockWidgetArea.RightDockWidgetArea,
        )

    def _on_new_chart(self) -> None:
        self.widget_registry.add_chart(
            exchange="coinbase",
            symbol="BTC/USD",
            timeframe="1m",
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
        )

    def _on_new_chart_orderflow(self) -> None:
        self.widget_registry.add_chart_orderflow(
            exchange="coinbase",
            symbol="BTC/USD",
            timeframe="1m",
            tick_size=0.01,
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
        )

    def _on_new_orderbook(self) -> None:
        self.widget_registry.add_orderbook(
            exchange="coinbase",
            symbol="BTC/USD",
            area=Qt.DockWidgetArea.RightDockWidgetArea,
        )

    def _on_new_dom(self) -> None:
        self.widget_registry.add_dom(
            exchange="coinbase",
            symbol="BTC/USD",
            levels=16,
            area=Qt.DockWidgetArea.RightDockWidgetArea,
        )

    def _save_layout(self) -> None:
        self.widget_registry.save_user_definitions()
        self.layout_manager.save_layout(self)

    def _setup_status(self) -> None:
        sb = self.statusBar()

        # Permanent right-side: exchange badge + connection dot
        exchanges = getattr(self.runtime, "exchanges", []) if self.runtime else []
        if exchanges:
            ex_label = QLabel("  ".join(e.upper() for e in exchanges))
            ex_label.setObjectName("status-meta")
            ex_label.setToolTip("Connected exchanges")
            sb.addPermanentWidget(ex_label)

        self._conn_dot = QLabel()
        self._conn_dot.setObjectName("status-dot")
        _set_status_state(self._conn_dot, "warn", "Connecting")
        sb.addPermanentWidget(self._conn_dot)

        if self.runtime is None:
            sb.showMessage("Shell only — no runtime attached")
            _set_status_state(self._conn_dot, "idle", "No runtime")
            return

        self.widget_registry.attach_runtime(self.runtime)
        self.runtime.started.connect(lambda: self.widget_registry.attach_runtime(self.runtime))
        self.runtime.started.connect(self._on_runtime_started)
        self.runtime.stopped.connect(self._on_runtime_stopped)
        self.runtime.status_changed.connect(sb.showMessage)
        self.runtime.runtime_error.connect(self._show_runtime_error)
        sb.showMessage("Initializing runtime…")

    def _on_runtime_started(self) -> None:
        _set_status_state(self._conn_dot, "ok", "Live")

    def _on_runtime_stopped(self) -> None:
        _set_status_state(self._conn_dot, "err", "Disconnected")

    def _show_runtime_error(self, message: str) -> None:
        QMessageBox.warning(self, "Runtime Error", message)

    def _reset_layout(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Layout",
            "Reset to default Sentinel layout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.layout_manager.reset_user_layout()
        self.widget_registry.reset_user_definitions()
        self.widget_registry.clear()
        self.widget_registry.load_or_create_defaults()
        self._arrange_default_docks()
        self._ensure_chart_visible()
        LOGGER.info("Reset to default Qt layout.")

    @asyncClose
    async def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self._save_layout()
        except Exception as exc:
            LOGGER.warning("Failed saving layout on close: %s", exc)
        if self.runtime is not None:
            await self.runtime.shutdown()
        event.accept()
