import logging
from typing import Any, Dict, List, Optional

from sentinel.alerts.rules.base import AlertRule
from sentinel.alerts.state import CooldownState

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Evaluates registered alert rules against incoming market data.

    Rules are added programmatically — no YAML config required.
    Each widget or feature that wants alerts creates its own RuleEngine
    (or shares one) and adds rules via add_rule().
    """

    def __init__(self) -> None:
        self._rules: Dict[str, List[AlertRule]] = {}  # symbol → rules
        self._state = CooldownState()

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.setdefault(rule.symbol, []).append(rule)
        logger.debug("Added rule %s for %s", rule.rule_id, rule.symbol)

    def remove_rule(self, rule: AlertRule) -> None:
        rules = self._rules.get(rule.symbol, [])
        try:
            rules.remove(rule)
        except ValueError:
            pass

    def clear_symbol(self, symbol: str) -> None:
        self._rules.pop(symbol, None)
        self._state.reset(symbol)

    def evaluate(
        self,
        symbol: str,
        current_price: float,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Return list of alert messages that fired this tick."""
        messages: List[str] = []
        for rule in self._rules.get(symbol, []):
            try:
                msg = rule.evaluate(current_price, self._state, extra_data)
                if msg:
                    messages.append(msg)
            except Exception:
                logger.exception("Error evaluating rule %s for %s", rule.rule_id, symbol)
        return messages

    def symbols(self) -> List[str]:
        return list(self._rules.keys())

    def __repr__(self) -> str:
        total = sum(len(v) for v in self._rules.values())
        return f"RuleEngine(symbols={len(self._rules)}, rules={total})"
