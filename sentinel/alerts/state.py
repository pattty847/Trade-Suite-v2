import time
from typing import Dict, Tuple


class CooldownState:
    """Tracks per-rule last-trigger timestamps for cooldown enforcement."""

    def __init__(self) -> None:
        # (symbol, rule_id) → last trigger time
        self._last_triggered: Dict[Tuple[str, str], float] = {}

    def can_trigger(self, symbol: str, rule_id: str, cooldown_seconds: float) -> bool:
        key = (symbol, rule_id)
        last = self._last_triggered.get(key)
        if last is None:
            return True
        return (time.monotonic() - last) >= cooldown_seconds

    def mark_triggered(self, symbol: str, rule_id: str) -> None:
        self._last_triggered[(symbol, rule_id)] = time.monotonic()

    def reset(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._last_triggered.clear()
        else:
            keys = [k for k in self._last_triggered if k[0] == symbol]
            for k in keys:
                del self._last_triggered[k]
