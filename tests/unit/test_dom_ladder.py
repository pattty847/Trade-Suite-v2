from sentinel.analysis.orderbook_processor import OrderBookProcessor


def test_build_dom_ladder_compacts_empty_tick_levels() -> None:
    processor = OrderBookProcessor(price_precision=0.01)
    raw_bids = [
        [69480.60, 0.0297],
        [69480.58, 0.0344],
        [69479.56, 0.0144],
        [69477.61, 0.00002],
    ]
    raw_asks = [
        [69484.00, 0.0135],
        [69484.12, 0.0410],
        [69484.34, 0.0014],
        [69489.16, 0.0522],
    ]

    ladder = processor.build_dom_ladder(raw_bids, raw_asks, levels_per_side=8, current_price=69482.30)

    assert ladder is not None
    rows = ladder["rows"]
    assert len(rows) == 1 + len([row for row in rows if row["kind"] == "ask"]) + len(
        [row for row in rows if row["kind"] == "bid"]
    )

    ask_rows = [row for row in rows if row["kind"] == "ask"]
    bid_rows = [row for row in rows if row["kind"] == "bid"]
    mid_rows = [row for row in rows if row["kind"] == "mid"]

    assert len(mid_rows) == 1
    assert all(row["ask_qty"] > 0 for row in ask_rows)
    assert all(row["bid_qty"] > 0 for row in bid_rows)
    assert ask_rows[-1]["price"] > mid_rows[0]["price"]
    assert bid_rows[0]["price"] < mid_rows[0]["price"]


def test_build_dom_ladder_preserves_cumulative_values_for_populated_rows() -> None:
    processor = OrderBookProcessor(price_precision=0.01)
    raw_bids = [
        [100.00, 1.0],
        [99.99, 2.0],
    ]
    raw_asks = [
        [100.02, 3.0],
        [100.03, 4.0],
    ]

    ladder = processor.build_dom_ladder(raw_bids, raw_asks, levels_per_side=4, current_price=100.01)

    assert ladder is not None
    ask_rows = [row for row in ladder["rows"] if row["kind"] == "ask"]
    bid_rows = [row for row in ladder["rows"] if row["kind"] == "bid"]

    assert ask_rows[-1]["ask_cum"] == 3.0
    assert ask_rows[0]["ask_cum"] == 7.0
    assert bid_rows[0]["bid_cum"] == 1.0
    assert bid_rows[1]["bid_cum"] == 3.0
