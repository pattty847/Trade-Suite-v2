import logging
from typing import Any, Dict, Optional

from sentinel.alerts.rules.base import AlertRule
from sentinel.alerts.state import CooldownState

logger = logging.getLogger(__name__)


class PercentageChangeRule(AlertRule):
    """Fires when price changes by ≥ threshold% relative to the previous closed candle."""

    def __init__(self, symbol: str, config: Dict[str, Any]) -> None:
        super().__init__(symbol, "percentage_change", config)
        self.percentage = float(config["percentage"])
        self.timeframe_minutes = int(config["timeframe"])
        self.rule_id = f"pct_change_{self.percentage}_{self.timeframe_minutes}min_{symbol}"

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

        # extra_data["ohlcv_data"] → {timeframe_minutes: [[ts,o,h,l,c,v], ...]}
        candles = (extra_data.get("ohlcv_data") or {}).get(self.timeframe_minutes, [])
        if len(candles) < 2:
            return None

        ref_price = float(candles[-2][4])  # previous candle close
        if ref_price == 0:
            return None

        pct = (current_price - ref_price) / ref_price * 100
        if abs(pct) < self.percentage:
            return None

        direction = "risen" if pct > 0 else "fallen"
        msg = (
            f"{self.symbol} has {direction} {abs(pct):.2f}% in {self.timeframe_minutes}m "
            f"({self.format_price(ref_price)} → {self.format_price(current_price)})"
        )
        state.mark_triggered(self.symbol, self.rule_id)
        logger.info("ALERT: %s", msg)
        return msg
