#!/usr/bin/env python3
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class StateManager:
    """
    Manages the state of alert rules, tracking when they were last triggered
    and enforcing cooldown periods.
    """
    
    def __init__(self):
        # Structure: {symbol: {rule_id: last_triggered_timestamp}}
        self._state: Dict[str, Dict[str, datetime]] = {}
    
    def register_symbol(self, symbol: str) -> None:
        """
        Register a new symbol to track
        """
        if symbol not in self._state:
            self._state[symbol] = {}
            logger.debug(f"Registered symbol {symbol} for state tracking")
    
    def can_trigger(self, symbol: str, rule_id: str, cooldown_seconds: int) -> bool:
        """
        Check if a rule can trigger based on its cooldown period
        
        Args:
            symbol: Trading symbol (e.g., BTC/USD)
            rule_id: Unique identifier for the rule
            cooldown_seconds: Seconds that must pass before the rule can trigger again
            
        Returns:
            True if enough time has passed since the last trigger
        """
        self.register_symbol(symbol)
        
        if rule_id not in self._state[symbol]:
            return True  # Never triggered before
        
        last_triggered = self._state[symbol][rule_id]
        cooldown = timedelta(seconds=cooldown_seconds)
        now = datetime.now()
        
        # Check if cooldown has passed
        return (now - last_triggered) >= cooldown
    
    def mark_triggered(self, symbol: str, rule_id: str) -> None:
        """
        Mark a rule as triggered at the current time
        
        Args:
            symbol: Trading symbol
            rule_id: Unique identifier for the rule
        """
        self.register_symbol(symbol)
        self._state[symbol][rule_id] = datetime.now()
        logger.debug(f"Rule {rule_id} for {symbol} marked as triggered")
    
    def get_last_triggered(self, symbol: str, rule_id: str) -> Optional[datetime]:
        """
        Get when a rule was last triggered
        
        Args:
            symbol: Trading symbol
            rule_id: Unique identifier for the rule
            
        Returns:
            Timestamp when the rule was last triggered, or None if never triggered
        """
        self.register_symbol(symbol)
        return self._state[symbol].get(rule_id)
    
    def get_symbols(self) -> list:
        """Get list of registered symbols"""
        return list(self._state.keys())
    
    def reset_symbol(self, symbol: str) -> None:
        """
        Reset all rule states for a symbol
        
        Args:
            symbol: Trading symbol to reset
        """
        if symbol in self._state:
            self._state[symbol] = {}
            logger.info(f"Reset state for symbol {symbol}")
    
    def reset_all(self) -> None:
        """Reset all state data"""
        self._state = {}
        logger.info("Reset all state data")
    
    def __repr__(self) -> str:
        counts = {symbol: len(rules) for symbol, rules in self._state.items()}
        return f"StateManager(symbols={len(counts)}, rule_counts={counts})" 