import logging
import statistics
from typing import Any, Dict, Optional

from sentinel.alerts.rules.base import AlertRule
from sentinel.alerts.state import CooldownState

logger = logging.getLogger(__name__)

_N_PERIODS = 14


class VolatilityRule(AlertRule):
    """Fires when stdev of the last N closes as % of price exceeds threshold."""

    def __init__(self, symbol: str, config: Dict[str, Any]) -> None:
        super().__init__(symbol, "volatility", config)
        self.threshold = float(config["threshold"])
        self.timeframe_minutes = int(config["timeframe"])
        self.rule_id = f"volatility_{self.threshold}_{self.timeframe_minutes}min_{symbol}"

    def evaluate(
        self,
        current_price: float,
        state: CooldownState,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if not state.can_trigger(self.symbol, self.rule_id, self.cooldown_seconds):
            return None

        if not extra_data:
            return None

        candles = (extra_data.get("ohlcv_data") or {}).get(self.timeframe_minutes, [])
        if len(candles) < _N_PERIODS:
            return None

        closes = [float(c[4]) for c in candles[-_N_PERIODS:]]
        if current_price == 0:
            return None

        vol_pct = statistics.stdev(closes) / current_price * 100
        if vol_pct < self.threshold:
            return None

        hours = round(self.timeframe_minutes * _N_PERIODS / 60, 1)
        msg = (
            f"{self.symbol} volatility {vol_pct:.2f}% over ~{hours}h "
            f"(threshold {self.threshold}%, price {self.format_price(current_price)})"
        )
        state.mark_triggered(self.symbol, self.rule_id)
        logger.info("ALERT: %s", msg)
        return msg
