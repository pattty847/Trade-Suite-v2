#!/usr/bin/env python3
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import uuid

from ..metrics import track_rule_evaluation

class AlertRule(ABC):
    """
    Abstract base class for all alert rules.
    
    Each rule implements its own logic for when to trigger an alert
    based on price data and other inputs.
    """
    
    def __init__(self, symbol: str, rule_type: str, config: Dict[str, Any]):
        """
        Initialize a new alert rule
        
        Args:
            symbol: Trading symbol this rule applies to (e.g., BTC/USD)
            rule_type: Type of rule (e.g., price_level, percentage_change, volatility)
            config: Configuration dictionary for this rule
        """
        self.symbol = symbol
        self.rule_type = rule_type
        self.rule_id = f"{rule_type}_{uuid.uuid4().hex[:8]}"  # Generate a unique ID
        self.config = config
        self.cooldown_seconds = config.get('cooldown', 300)  # Default 5 minutes
    
    @track_rule_evaluation
    @abstractmethod
    def evaluate(self, current_price: float, state_manager, extra_data=None) -> Optional[str]:
        """
        Evaluate if the rule should trigger an alert
        
        Args:
            current_price: Current price of the symbol
            state_manager: StateManager instance to check/update rule state
            extra_data: Any additional data needed for evaluation (e.g., OHLCV candles)
            
        Returns:
            Alert message if rule triggers, None otherwise
        """
        pass
    
    def format_price(self, price: float) -> str:
        """Format price with appropriate precision"""
        # TODO: Improve based on symbol's precision
        if abs(price) > 0 and abs(price) < 0.001:  # Very small prices
            return f"{price:.8f}"
        return f"{price:.2f}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(symbol={self.symbol}, id={self.rule_id})" 