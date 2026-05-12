import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from sentinel.alerts.state import CooldownState


class AlertRule(ABC):
    def __init__(self, symbol: str, rule_type: str, config: Dict[str, Any]) -> None:
        self.symbol = symbol
        self.rule_type = rule_type
        self.rule_id = f"{rule_type}_{uuid.uuid4().hex[:8]}"
        self.config = config
        self.cooldown_seconds: float = float(config.get("cooldown", 300))

    @abstractmethod
    def evaluate(
        self,
        current_price: float,
        state: CooldownState,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Return an alert message string if the rule fires, else None."""

    def format_price(self, price: float) -> str:
        if 0 < abs(price) < 0.001:
            return f"{price:.8f}"
        return f"{price:.2f}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(symbol={self.symbol}, id={self.rule_id})"
