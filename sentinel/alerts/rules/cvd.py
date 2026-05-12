import logging
from typing import Any, Dict, Optional

from sentinel.alerts.rules.base import AlertRule
from sentinel.alerts.state import CooldownState

logger = logging.getLogger(__name__)


class CVDRule(AlertRule):
    """
    Fires based on Cumulative Volume Delta conditions.

    extra_data must contain "cvd_data":
        {
            "cvd": float,                          # running cumulative delta
            "cvd_change_<N>m": float,              # delta change over N minutes
            "buy_sell_ratio_<N>m": {               # optional ratio breakdown
                "buy_ratio": float,
                "sell_ratio": float,
                "buy_volume": float,
                "sell_volume": float,
            }
        }
    """

    def __init__(self, symbol: str, config: Dict[str, Any]) -> None:
        super().__init__(symbol, "cvd", config)
        self.alert_type = config.get("type", "change")  # change | ratio | level
        self.cvd_threshold = config.get("cvd_threshold")
        self.cvd_pct_threshold = config.get("cvd_percentage_threshold")
        self.timeframe_minutes = int(config.get("timeframe", 15))
        self.buy_ratio_threshold = config.get("buy_ratio_threshold")
        self.sell_ratio_threshold = config.get("sell_ratio_threshold")
        self.cvd_level = config.get("cvd_level")
        self.level_condition = config.get("level_condition", "above")
        self.rule_id = f"cvd_{self.alert_type}_{self.timeframe_minutes}min_{symbol}"

    def evaluate(
        self,
        current_price: float,
        state: CooldownState,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if not state.can_trigger(self.symbol, self.rule_id, self.cooldown_seconds):
            return None
        if not extra_data or "cvd_data" not in extra_data:
            return None

        cvd_data = extra_data["cvd_data"]
        dispatch = {
            "change": self._eval_change,
            "ratio": self._eval_ratio,
            "level": self._eval_level,
        }
        fn = dispatch.get(self.alert_type)
        if fn is None:
            return None

        msg = fn(cvd_data, current_price)
        if msg:
            state.mark_triggered(self.symbol, self.rule_id)
            logger.info("ALERT: %s", msg)
        return msg

    def _eval_change(self, cvd_data: dict, price: float) -> Optional[str]:
        change = cvd_data.get(f"cvd_change_{self.timeframe_minutes}m")
        if change is None:
            return None
        current_cvd = cvd_data.get("cvd", 0)

        if self.cvd_threshold and abs(change) >= self.cvd_threshold:
            direction = "increased" if change > 0 else "decreased"
            sentiment = "BULLISH" if change > 0 else "BEARISH"
            return (
                f"{sentiment} CVD: {self.symbol} delta {direction} {abs(change):.2f} "
                f"over {self.timeframe_minutes}m (CVD={current_cvd:.2f}, px={self.format_price(price)})"
            )

        if self.cvd_pct_threshold and current_cvd != 0:
            pct = change / abs(current_cvd) * 100
            if abs(pct) >= self.cvd_pct_threshold:
                direction = "increased" if change > 0 else "decreased"
                sentiment = "BULLISH" if change > 0 else "BEARISH"
                return (
                    f"{sentiment} CVD%: {self.symbol} delta {direction} {abs(pct):.1f}% "
                    f"over {self.timeframe_minutes}m (CVD={current_cvd:.2f}, px={self.format_price(price)})"
                )
        return None

    def _eval_ratio(self, cvd_data: dict, price: float) -> Optional[str]:
        ratio = cvd_data.get(f"buy_sell_ratio_{self.timeframe_minutes}m", {})
        buy_r = ratio.get("buy_ratio", 0.5)
        sell_r = ratio.get("sell_ratio", 0.5)
        bv = ratio.get("buy_volume", 0)
        sv = ratio.get("sell_volume", 0)

        if self.buy_ratio_threshold and buy_r >= self.buy_ratio_threshold:
            return (
                f"BULLISH VOLUME: {self.symbol} {buy_r:.1%} buy over {self.timeframe_minutes}m "
                f"(buy {bv:.2f} / sell {sv:.2f}, px={self.format_price(price)})"
            )
        if self.sell_ratio_threshold and sell_r >= self.sell_ratio_threshold:
            return (
                f"BEARISH VOLUME: {self.symbol} {sell_r:.1%} sell over {self.timeframe_minutes}m "
                f"(buy {bv:.2f} / sell {sv:.2f}, px={self.format_price(price)})"
            )
        return None

    def _eval_level(self, cvd_data: dict, price: float) -> Optional[str]:
        if self.cvd_level is None:
            return None
        current_cvd = cvd_data.get("cvd", 0)
        if self.level_condition == "above" and current_cvd > self.cvd_level:
            return (
                f"CVD LEVEL: {self.symbol} CVD {current_cvd:.2f} above {self.cvd_level:.2f} "
                f"(px={self.format_price(price)})"
            )
        if self.level_condition == "below" and current_cvd < self.cvd_level:
            return (
                f"CVD LEVEL: {self.symbol} CVD {current_cvd:.2f} below {self.cvd_level:.2f} "
                f"(px={self.format_price(price)})"
            )
        return None
