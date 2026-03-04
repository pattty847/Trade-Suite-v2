import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
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
        self.setStyleSheet(
            """
            QMainWindow { background: #0b0f14; color: #d4dae3; }
            QMainWindow::separator {
                background: #1f2733;
                width: 1px;
                height: 1px;
            }
            QMenuBar {
                background: #0d131b;
                color: #cdd3de;
                border-bottom: 1px solid #1f2733;
            }
            QMenuBar::item {
                spacing: 3px;
                padding: 5px 9px;
                background: transparent;
            }
            QMenuBar::item:selected { background: #172131; }
            QMenu {
                background: #0f1620;
                color: #d4dae3;
                border: 1px solid #273142;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 18px;
                border: 1px solid transparent;
            }
            QMenu::item:selected {
                background: #1a2638;
                border: 1px solid #2a3a52;
            }
            QToolBar {
                background: #0d131b;
                border: none;
                spacing: 4px;
                padding: 2px 4px;
            }
            QDockWidget::title {
                background: #121a26;
                color: #a8bad7;
                padding: 4px 8px;
                border-bottom: 1px solid #223045;
            }
            QStatusBar {
                background: #0d131b;
                color: #8fa4c2;
                border-top: 1px solid #1f2733;
            }
            QComboBox {
                background: #111924;
                color: #d4dae3;
                border: 1px solid #2a3446;
                padding: 3px 8px;
                min-width: 84px;
            }
            QComboBox:hover { border: 1px solid #39506f; }
            QComboBox::drop-down { border: none; width: 18px; }
            QToolButton {
                background: #101722;
                color: #d4dae3;
                border: 1px solid #273347;
                padding: 3px 8px;
            }
            QToolButton:hover { background: #182337; border: 1px solid #365173; }
            QLabel { color: #c7ced9; }
            """
        )

    def _build_global_toolbar(self) -> None:
        bar = QToolBar("Global")
        bar.setObjectName("toolbar:global")
        bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)

        brand = QLabel("Sentinel")
        brand.setStyleSheet("font-weight:700; color:#8fb3ff; padding-right:8px;")
        bar.addWidget(brand)

        self._toolbar_asset = QComboBox()
        self._toolbar_asset.addItems(["BTC/USD", "ETH/USD", "SOL/USD"])
        self._toolbar_asset.setCurrentText("BTC/USD")
        bar.addWidget(self._toolbar_asset)

        self._toolbar_timeframe = QComboBox()
        self._toolbar_timeframe.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        self._toolbar_timeframe.setCurrentText("1m")
        bar.addWidget(self._toolbar_timeframe)

        mode = QComboBox()
        mode.addItems(["Candles", "Line", "Bars", "Heikin Ashi"])
        bar.addWidget(mode)

        indicators = QComboBox()
        indicators.addItems(["Indicators", "EMA", "VWAP", "RSI", "MACD"])
        bar.addWidget(indicators)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        bar.addAction("Search")
        bar.addAction("Replay")
        bar.addAction("Layout")

    def _build_left_toolbar(self) -> None:
        bar = QToolBar("Drawing")
        bar.setObjectName("toolbar:drawing")
        bar.setMovable(False)
        bar.setOrientation(Qt.Orientation.Vertical)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, bar)
        bar.setIconSize(bar.iconSize())

        for label in ["Cursor", "Crosshair", "Trend", "Ray", "HLine", "Fib", "Text"]:
            bar.addAction(label)

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
