import logging

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

        self.setStyleSheet(
            """
            /* ── Base ──────────────────────────────────────────────────────── */
            QMainWindow { background: #0b0f14; color: #d4dae3; }
            QMainWindow::separator { background: #1a2535; width: 2px; height: 2px; }
            QMainWindow::separator:hover { background: #3a5878; }

            /* pyqtgraph PlotWidget lives in a QGraphicsView — strip its frame */
            QGraphicsView { border: none; background: #060a11; }

            /* ── Menu bar ───────────────────────────────────────────────────── */
            QMenuBar {
                background: #0d131b;
                color: #cdd3de;
                border-bottom: 1px solid #1a2535;
                font-size: 12px;
            }
            QMenuBar::item { padding: 5px 9px; background: transparent; }
            QMenuBar::item:selected { background: #172131; }

            QMenu {
                background: #0f1620;
                color: #d4dae3;
                border: 1px solid #273142;
                padding: 4px;
            }
            QMenu::item { padding: 5px 20px; border: 1px solid transparent; }
            QMenu::item:selected { background: #1a2638; border: 1px solid #2a3a52; }
            QMenu::separator { height: 1px; background: #1a2535; margin: 3px 6px; }

            /* ── Toolbars ───────────────────────────────────────────────────── */
            QToolBar {
                background: #0d131b;
                border: none;
                border-bottom: 1px solid #1a2535;
                spacing: 3px;
                padding: 2px 4px;
            }
            QToolBar#toolbar\\:drawing {
                border-bottom: none;
                border-right: 1px solid #1a2535;
                padding: 4px 2px;
            }
            QToolBar::separator {
                background: #1a2535;
                width: 1px;
                margin: 3px 2px;
            }

            /* ── Tool buttons (toolbar actions render as these) ─────────────── */
            QToolButton {
                background: transparent;
                color: #9db8d6;
                border: 1px solid transparent;
                padding: 4px 8px;
                font-size: 12px;
            }
            QToolButton:hover {
                background: #172131;
                border: 1px solid #2a3e5a;
                color: #d4dae3;
            }
            QToolButton:checked, QToolButton:pressed {
                background: #152338;
                border: 1px solid #3d6090;
                color: #8fb3ff;
            }

            /* ── Dock widgets ───────────────────────────────────────────────── */
            QDockWidget {
                color: #7a99be;
                font-size: 11px;
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }
            QDockWidget::title {
                background: #0e1520;
                color: #7a99be;
                padding: 3px 8px;
                border-bottom: 1px solid #1a2535;
                text-align: left;
            }
            QDockWidget::close-button, QDockWidget::float-button {
                background: transparent;
                border: 1px solid transparent;
                padding: 1px;
                icon-size: 10px;
                subcontrol-position: top right;
            }
            QDockWidget::close-button:hover, QDockWidget::float-button:hover {
                background: #1e2e45;
                border: 1px solid #2a3e5a;
            }

            /* ── Status bar ─────────────────────────────────────────────────── */
            QStatusBar {
                background: #0d131b;
                color: #6a85a8;
                border-top: 1px solid #1a2535;
                font-size: 11px;
            }

            /* ── Push buttons ───────────────────────────────────────────────── */
            QPushButton {
                background: #111924;
                color: #b8c8d8;
                border: 1px solid #253446;
                padding: 3px 10px;
                min-width: 20px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #182337;
                border: 1px solid #3a5878;
                color: #d4dae3;
            }
            QPushButton:pressed {
                background: #0c1520;
                border: 1px solid #2a4a6a;
            }
            QPushButton:flat { border: none; background: transparent; }

            /* ── Combo boxes ────────────────────────────────────────────────── */
            QComboBox {
                background: #111924;
                color: #d0d8e4;
                border: 1px solid #253446;
                padding: 3px 8px;
                min-width: 80px;
                font-size: 12px;
            }
            QComboBox:hover { border: 1px solid #3a5878; }
            QComboBox::drop-down { border: none; width: 16px; }
            QComboBox QAbstractItemView {
                background: #0f1620;
                color: #d4dae3;
                border: 1px solid #273142;
                selection-background-color: #1a2638;
                outline: none;
            }

            /* ── Labels ─────────────────────────────────────────────────────── */
            QLabel { color: #b8c8d8; font-size: 12px; }

            /* ── Check boxes ────────────────────────────────────────────────── */
            QCheckBox { color: #b8c8d8; spacing: 6px; font-size: 12px; }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                background: #111924;
                border: 1px solid #253446;
            }
            QCheckBox::indicator:hover { border: 1px solid #3a5878; }
            QCheckBox::indicator:checked {
                background: #1a3d6a;
                border: 1px solid #2d6aaa;
            }

            /* ── Sliders ────────────────────────────────────────────────────── */
            QSlider::groove:horizontal {
                height: 3px;
                background: #1a2535;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #3a5a8a;
                border: 1px solid #2d4e7a;
                width: 10px;
                height: 10px;
                border-radius: 5px;
                margin: -4px 0;
            }
            QSlider::handle:horizontal:hover { background: #4a70aa; }
            QSlider::sub-page:horizontal { background: #1e3a5f; border-radius: 1px; }

            /* ── Tables ─────────────────────────────────────────────────────── */
            QTableWidget {
                background: #0b0f14;
                alternate-background-color: #0e1520;
                gridline-color: #131d2c;
                border: none;
                outline: none;
                selection-background-color: #1a2638;
                font-size: 12px;
            }
            QTableWidget::item { padding: 1px 4px; border: none; }
            QTableWidget::item:selected { background: #1a2638; }

            QHeaderView { background: #0d131b; border: none; }
            QHeaderView::section {
                background: #0d131b;
                color: #6a85a8;
                border: none;
                border-right: 1px solid #1a2535;
                border-bottom: 1px solid #1a2535;
                padding: 3px 6px;
                font-size: 11px;
                font-weight: 600;
            }
            QHeaderView::section:last { border-right: none; }

            /* ── Scrollbars ─────────────────────────────────────────────────── */
            QScrollBar:vertical {
                background: #0b0f14;
                width: 5px;
                margin: 0;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #243044;
                min-height: 24px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover { background: #3a5070; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

            QScrollBar:horizontal {
                background: #0b0f14;
                height: 5px;
                margin: 0;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: #243044;
                min-width: 24px;
                border-radius: 2px;
            }
            QScrollBar::handle:horizontal:hover { background: #3a5070; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

            /* ── Splitter handles ───────────────────────────────────────────── */
            QSplitter::handle { background: #151f2e; }
            QSplitter::handle:vertical { height: 3px; }
            QSplitter::handle:horizontal { width: 3px; }
            QSplitter::handle:hover { background: #2a4060; }
            """
        )

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
        bar.addWidget(self._toolbar_asset)

        self._toolbar_timeframe = QComboBox()
        self._toolbar_timeframe.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        self._toolbar_timeframe.setCurrentText("1m")
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

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("File")
        new_chart_action = QAction("New Chart", self)
        new_chart_action.triggered.connect(self._on_new_chart)
        file_menu.addAction(new_chart_action)

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
        dom = next((dock for dock in docks if isinstance(dock, DomDockWidget)), None)
        depth = next((dock for dock in docks if isinstance(dock, OrderbookDockWidget)), None)

        if chart is not None:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, chart)
        if dom is not None:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dom)
        if depth is not None:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, depth)
            if dom is not None:
                self.splitDockWidget(dom, depth, Qt.Orientation.Vertical)
                self.resizeDocks([dom, depth], [560, 340], Qt.Orientation.Vertical)
        if chart is not None and (dom is not None or depth is not None):
            right_anchor = dom if dom is not None else depth
            self.resizeDocks([chart, right_anchor], [1280, 380], Qt.Orientation.Horizontal)

    def _ensure_chart_visible(self) -> None:
        chart = next(
            (dock for dock in self.widget_registry.docks.values() if isinstance(dock, ChartDockWidget)),
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
        if self.runtime is None:
            self.statusBar().showMessage("Shell only (no runtime)")
            return
        self.widget_registry.attach_runtime(self.runtime)
        self.runtime.started.connect(lambda: self.widget_registry.attach_runtime(self.runtime))
        self.runtime.status_changed.connect(self.statusBar().showMessage)
        self.runtime.runtime_error.connect(self._show_runtime_error)
        self.statusBar().showMessage("Initializing runtime...")

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
