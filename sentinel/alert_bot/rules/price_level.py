#!/usr/bin/env python3
from typing import Optional, Dict, Any
import logging
from .base import AlertRule

logger = logging.getLogger(__name__)

class PriceLevelRule(AlertRule):
    """
    Rule that triggers when price crosses above or below a specified level
    """
    
    def __init__(self, symbol: str, config: Dict[str, Any]):
        """
        Initialize a price level rule
        
        Args:
            symbol: Trading symbol this rule applies to
            config: Configuration with price and condition
        """
        super().__init__(symbol, "price_level", config)
        self.price_level = float(config["price"])
        self.condition = config["condition"]  # 'above' or 'below'
        
        if self.condition not in ["above", "below"]:
            raise ValueError(f"Invalid condition '{self.condition}' - must be 'above' or 'below'")
        
        # More descriptive rule_id
        self.rule_id = f"price_level_{self.condition}_{self.price_level}_{self.symbol}"
        
        logger.debug(f"Created {self.condition} {self.price_level} rule for {symbol}")
    
    def evaluate(self, current_price: float, state_manager, extra_data=None) -> Optional[str]:
        """
        Check if price has crossed the specified level
        
        Args:
            current_price: Current price of the symbol
            state_manager: StateManager for tracking rule state
            extra_data: Not used for this rule type
            
        Returns:
            Alert message if triggered, None otherwise
        """
        if not state_manager.can_trigger(self.symbol, self.rule_id, self.cooldown_seconds):
            return None  # Still in cooldown period
        
        triggered = False
        
        if self.condition == "above" and current_price > self.price_level:
            triggered = True
            message = (
                f"{self.symbol} is now above {self.format_price(self.price_level)} "
                f"(Current: {self.format_price(current_price)})"
            )
        elif self.condition == "below" and current_price < self.price_level:
            triggered = True
            message = (
                f"{self.symbol} is now below {self.format_price(self.price_level)} "
                f"(Current: {self.format_price(current_price)})"
            )
        
        if triggered:
            state_manager.mark_triggered(self.symbol, self.rule_id)
            logger.info(f"TRIGGERED: {message}")
            return message
            
        return None 