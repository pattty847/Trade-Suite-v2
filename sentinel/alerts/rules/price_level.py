import logging
from typing import Any, Dict, Optional

from sentinel.alerts.rules.base import AlertRule
from sentinel.alerts.state import CooldownState

logger = logging.getLogger(__name__)


class PriceLevelRule(AlertRule):
    def __init__(self, symbol: str, config: Dict[str, Any]) -> None:
        super().__init__(symbol, "price_level", config)
        self.price_level = float(config["price"])
        self.condition = config["condition"]  # "above" | "below"
        if self.condition not in ("above", "below"):
            raise ValueError(f"condition must be 'above' or 'below', got {self.condition!r}")
        self.rule_id = f"price_level_{self.condition}_{self.price_level}_{symbol}"

    def evaluate(
        self,
        current_price: float,
        state: CooldownState,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if not state.can_trigger(self.symbol, self.rule_id, self.cooldown_seconds):
            return None

        if self.condition == "above" and current_price > self.price_level:
            msg = (
                f"{self.symbol} above {self.format_price(self.price_level)} "
                f"(now {self.format_price(current_price)})"
            )
        elif self.condition == "below" and current_price < self.price_level:
            msg = (
                f"{self.symbol} below {self.format_price(self.price_level)} "
                f"(now {self.format_price(current_price)})"
            )
        else:
            return None

        state.mark_triggered(self.symbol, self.rule_id)
        logger.info("ALERT: %s", msg)
        return msg
