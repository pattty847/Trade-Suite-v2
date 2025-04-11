"""
Dockable widget system for the Trading Suite application.

This package provides a framework for creating and managing dockable UI widgets
that can be arranged by the user into custom layouts.
"""

from trade_suite.gui.widgets.base_widget import DockableWidget
from trade_suite.gui.widgets.dashboard_manager import DashboardManager
from trade_suite.gui.widgets.chart_widget import ChartWidget
from trade_suite.gui.widgets.orderbook_widget import OrderbookWidget
from trade_suite.gui.widgets.trading_widget import TradingWidget
from trade_suite.gui.widgets.price_level_widget import PriceLevelWidget
from trade_suite.gui.widgets.sec_filing_viewer import SECFilingViewer

__all__ = [
    "DockableWidget", 
    "DashboardManager",
    "ChartWidget",
    "OrderbookWidget",
    "TradingWidget",
    "PriceLevelWidget",
    "SECFilingViewer"
] 