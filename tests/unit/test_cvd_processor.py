"""Tests for CandleCVDProcessor."""
import pytest
from sentinel.analysis.cvd_processor import CandleCVDProcessor, timeframe_to_ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trade(side: str, amount: float, ts_ms: int) -> dict:
    return {"timestamp": ts_ms, "amount": amount, "side": side, "price": 50_000.0}


ONE_MIN = 60_000  # ms


# ---------------------------------------------------------------------------
# timeframe_to_ms
# ---------------------------------------------------------------------------

def test_timeframe_to_ms_known():
    assert timeframe_to_ms("1m") == 60_000
    assert timeframe_to_ms("1h") == 3_600_000
    assert timeframe_to_ms("1d") == 86_400_000


def test_timeframe_to_ms_unknown():
    with pytest.raises(ValueError):
        timeframe_to_ms("99x")


# ---------------------------------------------------------------------------
# CandleCVDProcessor — basic accumulation
# ---------------------------------------------------------------------------

def test_empty_series():
    proc = CandleCVDProcessor("1m")
    ts, deltas, cum = proc.get_series()
    assert ts == [] and deltas == [] and cum == []


def test_single_buy_trade():
    proc = CandleCVDProcessor("1m")
    proc.add_trade(_trade("buy", 1.0, 0))
    ts, deltas, cum = proc.get_series()
    assert deltas == [1.0]
    assert cum == [1.0]


def test_single_sell_trade():
    proc = CandleCVDProcessor("1m")
    proc.add_trade(_trade("sell", 0.5, 0))
    ts, deltas, cum = proc.get_series()
    assert deltas == pytest.approx([-0.5])
    assert cum == pytest.approx([-0.5])


def test_buy_and_sell_same_candle():
    proc = CandleCVDProcessor("1m")
    proc.add_trade(_trade("buy", 2.0, 1_000))
    proc.add_trade(_trade("sell", 0.8, 5_000))
    ts, deltas, cum = proc.get_series()
    assert len(deltas) == 1
    assert deltas[0] == pytest.approx(1.2)
    assert cum[0] == pytest.approx(1.2)


def test_multiple_candles_sorted():
    proc = CandleCVDProcessor("1m")
    # candle 0 (0–60s): +1.5 - 0.8 = +0.7
    proc.add_trade(_trade("buy", 1.5, 0))
    proc.add_trade(_trade("sell", 0.8, 30_000))
    # candle 1 (60–120s): +2.0 - 1.0 = +1.0
    proc.add_trade(_trade("buy", 2.0, ONE_MIN))
    proc.add_trade(_trade("sell", 1.0, ONE_MIN + 10_000))
    # candle 2 (120–180s): +3.0 - 1.2 = +1.8
    proc.add_trade(_trade("buy", 3.0, 2 * ONE_MIN))
    proc.add_trade(_trade("sell", 1.2, 2 * ONE_MIN + 20_000))

    ts, deltas, cum = proc.get_series()

    assert len(deltas) == 3
    assert deltas[0] == pytest.approx(0.7)
    assert deltas[1] == pytest.approx(1.0)
    assert deltas[2] == pytest.approx(1.8)

    # cumulative must be running sum
    assert cum[0] == pytest.approx(0.7)
    assert cum[1] == pytest.approx(1.7)
    assert cum[2] == pytest.approx(3.5)

    # timestamps must be ascending
    assert ts[0] < ts[1] < ts[2]


def test_candle_boundary_snap():
    """Trades right on the candle boundary land in the correct bucket."""
    proc = CandleCVDProcessor("1m")
    # exactly at candle 1 open
    proc.add_trade(_trade("buy", 1.0, ONE_MIN))
    # one ms before → still candle 0
    proc.add_trade(_trade("sell", 0.5, ONE_MIN - 1))

    ts, deltas, cum = proc.get_series()
    assert len(deltas) == 2
    # candle 0 has the sell
    assert deltas[0] == pytest.approx(-0.5)
    # candle 1 has the buy
    assert deltas[1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# latest_delta
# ---------------------------------------------------------------------------

def test_latest_delta_empty():
    proc = CandleCVDProcessor("1m")
    assert proc.latest_delta() is None


def test_latest_delta_returns_last_candle():
    proc = CandleCVDProcessor("1m")
    proc.add_trade(_trade("buy", 5.0, 0))
    proc.add_trade(_trade("sell", 1.0, ONE_MIN))
    assert proc.latest_delta() == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# reset and set_timeframe
# ---------------------------------------------------------------------------

def test_reset_clears_state():
    proc = CandleCVDProcessor("1m")
    proc.add_trade(_trade("buy", 1.0, 0))
    proc.reset()
    ts, deltas, cum = proc.get_series()
    assert deltas == []


def test_set_timeframe_resets():
    proc = CandleCVDProcessor("1m")
    proc.add_trade(_trade("buy", 1.0, 0))
    proc.set_timeframe("5m")
    ts, deltas, cum = proc.get_series()
    assert deltas == []


# ---------------------------------------------------------------------------
# Bad / missing trade fields
# ---------------------------------------------------------------------------

def test_missing_fields_silently_ignored():
    proc = CandleCVDProcessor("1m")
    proc.add_trade({})                            # no fields at all
    proc.add_trade({"timestamp": 0, "amount": 1.0})  # no side
    proc.add_trade({"timestamp": 0, "side": "buy"})  # no amount
    ts, deltas, cum = proc.get_series()
    assert deltas == []


def test_known_total_matches_graveyard_example():
    """
    Replicates the manual test from the old test_cvd.py:
    trades: +1.5, -0.8, +2.0, -1.0, +3.0, +0.5, -1.2, +2.5 → total 6.5
    All within one 1-hour candle.
    """
    proc = CandleCVDProcessor("1h")
    trades = [
        ("buy",  1.5),
        ("sell", 0.8),
        ("buy",  2.0),
        ("sell", 1.0),
        ("buy",  3.0),
        ("buy",  0.5),
        ("sell", 1.2),
        ("buy",  2.5),
    ]
    for i, (side, amt) in enumerate(trades):
        proc.add_trade(_trade(side, amt, i * 60_000))  # all in hour 0

    _, deltas, cum = proc.get_series()
    assert cum[-1] == pytest.approx(6.5, abs=1e-9)
