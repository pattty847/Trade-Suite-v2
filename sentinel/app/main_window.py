import logging
from pathlib import Path

import pyqtgraph as pg
import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QToolBar,
    QWidget,
)
from qasync import asyncClose

from sentinel.app.layout_manager import LayoutManager
from sentinel.app.runtime import SentinelRuntime
from sentinel.app.widget_registry import WidgetRegistry
from sentinel.widgets.chart_orderflow_widget import ChartOrderflowDockWidget
from sentinel.widgets.chart_widget import ChartDockWidget
from sentinel.widgets.dom_widget import DomDockWidget
from sentinel.widgets.orderbook_widget import OrderbookDockWidget


LOGGER = logging.getLogger(__name__)


class SentinelMainWindow(QMainWindow):
    def __init__(self, app_version: str, runtime: SentinelRuntime | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Sentinel")
        self.resize(1600, 900)
        self.setDockNestingEnabled(True)
        self.runtime = runtime

        self.layout_manager = LayoutManager(app_version=app_version)
        self.widget_registry = WidgetRegistry(self)
        self._toolbar_asset: QComboBox | None = None
        self._toolbar_timeframe: QComboBox | None = None

        self._apply_theme()
        self._build_global_toolbar()
        self._build_left_toolbar()
        self._build_menus()
        self._bootstrap_layout()
        self._setup_status()

    def _apply_theme(self) -> None:
        # Set pyqtgraph defaults before any plots are created.
        pg.setConfigOptions(foreground="#8fa4c2", background="#060a11", antialias=True)

        with open(Path(__file__).parent / "theme.qss") as f:
            self.setStyleSheet(f.read())

    def _build_global_toolbar(self) -> None:
        bar = QToolBar("Global")
        bar.setObjectName("toolbar:global")
        bar.setMovable(False)
        bar.setIconSize(QSize(16, 16))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)

        brand = QLabel("Sentinel")
        brand.setStyleSheet("font-weight:700; color:#8fb3ff; padding: 0 10px 0 4px; font-size:13px;")
        bar.addWidget(brand)

        self._toolbar_asset = QComboBox()
        self._toolbar_asset.addItems(["BTC/USD", "ETH/USD", "SOL/USD"])
        self._toolbar_asset.setCurrentText("BTC/USD")
        self._toolbar_asset.currentTextChanged.connect(self._on_selector_changed)
        bar.addWidget(self._toolbar_asset)

        self._toolbar_timeframe = QComboBox()
        self._toolbar_timeframe.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        self._toolbar_timeframe.setCurrentText("1m")
        self._toolbar_timeframe.currentTextChanged.connect(self._on_selector_changed)
        bar.addWidget(self._toolbar_timeframe)

        _ic = "#6a85a8"  # icon tint for combo labels
        mode = QComboBox()
        mode.addItems(["Candles", "Line", "Bars", "Heikin Ashi"])
        mode.setItemIcon(0, qta.icon("mdi6.chart-box-outline", color=_ic))
        mode.setItemIcon(1, qta.icon("mdi6.chart-line", color=_ic))
        mode.setItemIcon(2, qta.icon("mdi6.chart-bar", color=_ic))
        mode.setItemIcon(3, qta.icon("mdi6.chart-areaspline", color=_ic))
        bar.addWidget(mode)

        indicators = QComboBox()
        indicators.addItems(["Indicators", "EMA", "VWAP", "RSI", "MACD"])
        indicators.setItemIcon(0, qta.icon("mdi6.chart-bell-curve-cumulative", color=_ic))
        bar.addWidget(indicators)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        _btn = "#7a99be"
        search_act = QAction(qta.icon("mdi6.magnify", color=_btn), "Search", self)
        replay_act = QAction(qta.icon("mdi6.history", color=_btn), "Replay", self)
        layout_act = QAction(qta.icon("mdi6.view-dashboard-outline", color=_btn), "Layout", self)
        for act in (search_act, replay_act, layout_act):
            bar.addAction(act)

    def _build_left_toolbar(self) -> None:
        bar = QToolBar("Drawing")
        bar.setObjectName("toolbar:drawing")
        bar.setMovable(False)
        bar.setOrientation(Qt.Orientation.Vertical)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, bar)

        _ic = "#6a85a8"
        _tools = [
            ("Cursor",    "mdi6.cursor-default-outline", "Cursor"),
            ("Crosshair", "mdi6.crosshairs",             "Crosshair"),
            ("Trend",     "mdi6.trending-up",            "Trend line"),
            ("Ray",       "mdi6.ray-start-arrow",        "Ray"),
            ("HLine",     "mdi6.minus",                  "Horizontal line"),
            ("Fib",       "mdi6.sine-wave",               "Fibonacci"),
            ("Text",      "mdi6.format-text",            "Text annotation"),
        ]

        group = QActionGroup(self)
        group.setExclusive(True)
        first = True
        for name, icon_id, tooltip in _tools:
            act = QAction(qta.icon(icon_id, color=_ic, color_active="#b8d0f0"), name, self)
            act.setToolTip(tooltip)
            act.setCheckable(True)
            if first:
                act.setChecked(True)
                first = False
            group.addAction(act)
            bar.addAction(act)

    def _on_selector_changed(self, _text: str) -> None:
        """Propagate asset/timeframe combo changes to all open chart widgets."""
        if self._toolbar_asset is None or self._toolbar_timeframe is None:
            return
        symbol = self._toolbar_asset.currentText()
        timeframe = self._toolbar_timeframe.currentText()
        for dock in self.widget_registry.docks.values():
            if isinstance(dock, (ChartDockWidget, ChartOrderflowDockWidget)):
                dock.change_subscription("coinbase", symbol, timeframe)

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("File")
        new_chart_action = QAction("New Chart", self)
        new_chart_action.triggered.connect(self._on_new_chart)
        file_menu.addAction(new_chart_action)

        new_chart_orderflow_action = QAction("New Chart + Orderflow", self)
        new_chart_orderflow_action.triggered.connect(self._on_new_chart_orderflow)
        file_menu.addAction(new_chart_orderflow_action)

        new_orderbook_action = QAction("New Orderbook", self)
        new_orderbook_action.triggered.connect(self._on_new_orderbook)
        file_menu.addAction(new_orderbook_action)

        new_dom_action = QAction("New DOM", self)
        new_dom_action.triggered.connect(self._on_new_dom)
        file_menu.addAction(new_dom_action)

        new_dock_action = QAction("New Placeholder Dock", self)
        new_dock_action.triggered.connect(self._on_new_placeholder)
        file_menu.addAction(new_dock_action)

        save_layout_action = QAction("Save Layout", self)
        save_layout_action.triggered.connect(self._save_layout)
        file_menu.addAction(save_layout_action)

        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        file_menu.addAction(reset_layout_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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

    def _on_new_placeholder(self) -> None:
        count = len(self.widget_registry.docks) + 1
        self.widget_registry.add_placeholder(
            title=f"Placeholder {count}",
            area=Qt.DockWidgetArea.RightDockWidgetArea,
        )

    def _on_new_chart(self) -> None:
        symbol = self._toolbar_asset.currentText() if self._toolbar_asset is not None else "BTC/USD"
        timeframe = self._toolbar_timeframe.currentText() if self._toolbar_timeframe is not None else "1m"
        self.widget_registry.add_chart(
            exchange="coinbase",
            symbol=symbol,
            timeframe=timeframe,
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
        )

    def _on_new_chart_orderflow(self) -> None:
        symbol = self._toolbar_asset.currentText() if self._toolbar_asset is not None else "BTC/USD"
        timeframe = self._toolbar_timeframe.currentText() if self._toolbar_timeframe is not None else "1m"
        self.widget_registry.add_chart_orderflow(
            exchange="coinbase",
            symbol=symbol,
            timeframe=timeframe,
            tick_size=0.01,
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
        )

    def _on_new_orderbook(self) -> None:
        symbol = self._toolbar_asset.currentText() if self._toolbar_asset is not None else "BTC/USD"
        self.widget_registry.add_orderbook(
            exchange="coinbase",
            symbol=symbol,
            area=Qt.DockWidgetArea.RightDockWidgetArea,
        )

    def _on_new_dom(self) -> None:
        symbol = self._toolbar_asset.currentText() if self._toolbar_asset is not None else "BTC/USD"
        self.widget_registry.add_dom(
            exchange="coinbase",
            symbol=symbol,
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
            ex_label.setStyleSheet("color: #3f5a76; padding: 0 10px; font-size: 11px;")
            sb.addPermanentWidget(ex_label)

        self._conn_dot = QLabel("●  Connecting")
        self._conn_dot.setStyleSheet("color: #ef5350; padding: 0 10px; font-size: 11px;")
        sb.addPermanentWidget(self._conn_dot)

        if self.runtime is None:
            sb.showMessage("Shell only (no runtime)")
            self._conn_dot.setText("●  No runtime")
            return

        self.widget_registry.attach_runtime(self.runtime)
        self.runtime.started.connect(lambda: self.widget_registry.attach_runtime(self.runtime))
        self.runtime.started.connect(self._on_runtime_started)
        self.runtime.stopped.connect(self._on_runtime_stopped)
        self.runtime.status_changed.connect(sb.showMessage)
        self.runtime.runtime_error.connect(self._show_runtime_error)
        sb.showMessage("Initializing runtime...")

    def _on_runtime_started(self) -> None:
        self._conn_dot.setText("●  Connected")
        self._conn_dot.setStyleSheet("color: #26a69a; padding: 0 10px; font-size: 11px;")

    def _on_runtime_stopped(self) -> None:
        self._conn_dot.setText("●  Disconnected")
        self._conn_dot.setStyleSheet("color: #ef5350; padding: 0 10px; font-size: 11px;")

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
