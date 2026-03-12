from __future__ import annotations

from PySide6.QtWidgets import QApplication

from sentinel.analysis.orderbook_processor import OrderBookProcessor
from sentinel.widgets.chart_widget import ChartDockWidget
from sentinel.widgets.chart_orderflow_widget import (
    ChartOrderflowDockWidget,
    OrderflowLadderPane,
    choose_auto_tick_size,
)


def test_build_visible_ladder_keeps_populated_rows_and_midpoint() -> None:
    processor = OrderBookProcessor(price_precision=0.01)
    raw_bids = [
        [100.00, 1.0],
        [99.99, 2.0],
        [99.95, 3.0],
    ]
    raw_asks = [
        [100.02, 4.0],
        [100.03, 5.0],
        [100.08, 6.0],
    ]

    ladder = processor.build_visible_ladder(
        raw_bids,
        raw_asks,
        price_min=99.98,
        price_max=100.04,
        current_price=100.01,
    )

    assert ladder is not None
    rows = ladder["rows"]
    assert [row["kind"] for row in rows] == ["ask", "ask", "mid", "bid", "bid"]
    assert [row["price"] for row in rows if row["kind"] == "ask"] == [100.03, 100.02]
    assert [row["price"] for row in rows if row["kind"] == "bid"] == [100.0, 99.99]


def test_build_visible_ladder_filters_rows_to_chart_range() -> None:
    processor = OrderBookProcessor(price_precision=0.01)
    raw_bids = [
        [100.00, 1.0],
        [99.99, 2.0],
        [99.95, 3.0],
    ]
    raw_asks = [
        [100.02, 4.0],
        [100.03, 5.0],
        [100.08, 6.0],
    ]

    wide = processor.build_visible_ladder(
        raw_bids,
        raw_asks,
        price_min=99.94,
        price_max=100.09,
        current_price=100.01,
    )
    narrow = processor.build_visible_ladder(
        raw_bids,
        raw_asks,
        price_min=99.99,
        price_max=100.02,
        current_price=100.01,
    )

    assert wide is not None
    assert narrow is not None
    assert len(wide["rows"]) > len(narrow["rows"])
    assert [row["kind"] for row in narrow["rows"]] == ["ask", "mid", "bid", "bid"]


def test_chart_orderflow_export_definition_includes_tick_size() -> None:
    app = QApplication.instance() or QApplication([])
    dock = ChartOrderflowDockWidget(
        instance_id="chart_orderflow_test",
        runtime=None,
        exchange="coinbase",
        symbol="BTC/USD",
        timeframe="1m",
        price_precision=0.01,
        chart_mode="line",
        show_bubbles=True,
    )

    exported = dock.export_definition()

    assert exported["widget_type"] == "chart_orderflow"
    assert exported["config"]["exchange"] == "coinbase"
    assert exported["config"]["symbol"] == "BTC/USD"
    assert exported["config"]["timeframe"] == "1m"
    assert exported["config"]["tick_size"] == dock.ladder_pane.tick_size
    assert exported["config"]["chart_mode"] == "line"
    assert exported["config"]["show_bubbles"] is True

    dock.close()
    del app


def test_choose_auto_tick_size_grows_when_view_span_grows() -> None:
    presets = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50]

    tight = choose_auto_tick_size(
        price_min=99.5,
        price_max=100.5,
        ladder_height_px=800,
        current_tick=0.01,
        presets=presets,
        minimum_tick=0.01,
        force=True,
    )
    wide = choose_auto_tick_size(
        price_min=0.0,
        price_max=500.0,
        ladder_height_px=800,
        current_tick=0.01,
        presets=presets,
        minimum_tick=0.01,
        force=True,
    )

    assert tight < wide
    assert tight in presets
    assert wide in presets


def test_choose_auto_tick_size_keeps_current_tick_inside_hysteresis_band() -> None:
    presets = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50]

    selected = choose_auto_tick_size(
        price_min=95.0,
        price_max=105.0,
        ladder_height_px=800,
        current_tick=0.25,
        presets=presets,
        minimum_tick=0.01,
    )

    assert selected == 0.25


def test_visible_tick_rows_use_snapped_last_price_as_single_center_row() -> None:
    pane = OrderflowLadderPane(exchange="coinbase", symbol="BTC/USD", price_precision=10.0)
    pane.set_visible_price_range(69300.0, 69500.0)
    pane.set_last_price(69412.3)

    ladder = {
        "rows": [
            {"kind": "ask", "price": 69440.0, "size": 1.0, "total": 1.0},
            {"kind": "bid", "price": 69400.0, "size": 2.0, "total": 2.0},
        ],
        "midpoint": 69410.0,
        "best_bid": 69400.0,
        "best_ask": 69420.0,
    }
    rows = pane._build_visible_tick_rows(ladder)

    mid_rows = [row for row in rows if row["kind"] == "mid"]
    assert len(mid_rows) == 1
    assert mid_rows[0]["price"] == 69410.0


def test_orderbook_tick_presets_include_intermediate_nice_steps() -> None:
    processor = OrderBookProcessor(price_precision=0.01)
    presets = processor.calculate_tick_presets(70000.0)

    assert 0.01 in presets
    assert 0.1 in presets
    assert 1.0 in presets
    assert 10.0 in presets
    assert 20.0 in presets
    assert 25.0 in presets
    assert 50.0 in presets
    assert 100.0 in presets


def test_chart_dock_toolbar_initializes_and_exports_local_state() -> None:
    app = QApplication.instance() or QApplication([])
    dock = ChartDockWidget(
        instance_id="chart_test",
        runtime=None,
        exchange="coinbase",
        symbol="ETH/USD",
        timeframe="5m",
        chart_mode="heikin ashi",
        show_bubbles=True,
    )

    assert dock.toolbar.symbol() == "ETH/USD"
    assert dock.toolbar.timeframe() == "5m"
    assert dock.toolbar.mode() == "Heikin Ashi"
    assert dock.toolbar.bubbles_enabled() is True
    assert dock.chart_pane.chart_mode() == "heikin ashi"
    assert dock.chart_pane.bubbles_enabled() is True

    exported = dock.export_definition()
    assert exported["config"]["symbol"] == "ETH/USD"
    assert exported["config"]["timeframe"] == "5m"
    assert exported["config"]["chart_mode"] == "heikin ashi"
    assert exported["config"]["show_bubbles"] is True

    dock.close()
    del app


def test_changing_one_chart_toolbar_does_not_change_another_chart() -> None:
    app = QApplication.instance() or QApplication([])
    first = ChartDockWidget(
        instance_id="chart_one",
        runtime=None,
        exchange="coinbase",
        symbol="BTC/USD",
        timeframe="1m",
    )
    second = ChartDockWidget(
        instance_id="chart_two",
        runtime=None,
        exchange="coinbase",
        symbol="ETH/USD",
        timeframe="5m",
    )

    first.toolbar.set_symbol("SOL/USD")
    first.toolbar.symbol_changed.emit("SOL/USD")
    first.toolbar.set_timeframe("15m")
    first.toolbar.timeframe_changed.emit("15m")
    first.toolbar.set_mode("Line")
    first.toolbar.mode_changed.emit("Line")
    first.toolbar.set_bubbles_enabled(True)

    assert first.symbol == "SOL/USD"
    assert first.timeframe == "15m"
    assert first.chart_mode == "line"
    assert first.show_bubbles is True
    assert second.symbol == "ETH/USD"
    assert second.timeframe == "5m"
    assert second.chart_mode == "candles"
    assert second.show_bubbles is False

    first.close()
    second.close()
    del app
