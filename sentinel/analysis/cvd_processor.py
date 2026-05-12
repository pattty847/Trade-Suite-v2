import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# Timeframe string → milliseconds
_TF_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def timeframe_to_ms(timeframe: str) -> int:
    ms = _TF_MS.get(timeframe)
    if ms is None:
        raise ValueError(f"Unknown timeframe: {timeframe!r}")
    return ms


class CandleCVDProcessor:
    """
    Accumulates per-candle buy/sell volume delta from a live trade stream.

    Each trade dict is the raw ccxt format:
        {"timestamp": <ms>, "price": float, "amount": float, "side": "buy"|"sell", ...}

    Exposes two series for chart rendering:
        - bar_delta:   per-candle (buy_vol - sell_vol), rendered as coloured bars
        - cumulative:  running sum of bar_delta from session start, rendered as a line
    """

    def __init__(self, timeframe: str = "1m") -> None:
        self.timeframe = timeframe
        self._tf_ms = timeframe_to_ms(timeframe)
        # candle_ts_ms → [buy_vol, sell_vol]
        self._buckets: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        self._sorted_ts: list[int] = []  # kept sorted for cheap series export

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_timeframe(self, timeframe: str) -> None:
        """Switch timeframe and reset — called when the chart changes interval."""
        self.timeframe = timeframe
        self._tf_ms = timeframe_to_ms(timeframe)
        self.reset()

    def add_trade(self, trade: dict) -> None:
        """Ingest one raw ccxt trade dict."""
        ts_ms = trade.get("timestamp")
        amount = trade.get("amount")
        side = trade.get("side", "")

        if ts_ms is None or amount is None or not side:
            return

        bucket = self._snap(float(ts_ms))
        slot = self._buckets[bucket]
        if side == "buy":
            slot[0] += float(amount)
        elif side == "sell":
            slot[1] += float(amount)

        if bucket not in self._sorted_ts:
            # Insertion-sort to keep list ordered without full re-sort every tick
            self._insert_sorted(bucket)

    def get_series(
        self,
    ) -> tuple[list[float], list[float], list[float]]:
        """
        Returns (timestamps_s, bar_deltas, cumulative_cvd).
        timestamps_s are candle open times in seconds (matches pyqtgraph x-axis).
        """
        ts_s: list[float] = []
        deltas: list[float] = []
        cumulative: list[float] = []
        running = 0.0

        for ts_ms in self._sorted_ts:
            buy, sell = self._buckets[ts_ms]
            delta = buy - sell
            running += delta
            ts_s.append(ts_ms / 1000.0)
            deltas.append(delta)
            cumulative.append(running)

        return ts_s, deltas, cumulative

    def latest_delta(self) -> Optional[float]:
        """Delta for the current (live) candle — useful for a heads-up display."""
        if not self._sorted_ts:
            return None
        buy, sell = self._buckets[self._sorted_ts[-1]]
        return buy - sell

    def reset(self) -> None:
        self._buckets.clear()
        self._sorted_ts.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _snap(self, ts_ms: float) -> int:
        """Snap a trade timestamp to its candle-open bucket."""
        return int(ts_ms // self._tf_ms) * self._tf_ms

    def _insert_sorted(self, ts_ms: int) -> None:
        lo, hi = 0, len(self._sorted_ts)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._sorted_ts[mid] < ts_ms:
                lo = mid + 1
            else:
                hi = mid
        self._sorted_ts.insert(lo, ts_ms)
