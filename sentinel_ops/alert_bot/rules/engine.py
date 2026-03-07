#!/usr/bin/env python3
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path
from ..config.loader import AlertConfig, CVDRule as CVDRuleConfig, load_config
from ..state.manager import StateManager
from .base import AlertRule
from .price_level import PriceLevelRule
from .percentage_change import PercentageChangeRule
from .volatility import VolatilityRule
from .cvd import CVDRule

logger = logging.getLogger(__name__)

class RuleEngine:
    """
    Manages and evaluates all alert rules across all symbols
    """
    
    def __init__(self, config_or_path: Any):
        """
        Initialize rule engine from config
        
        Args:
            config_or_path: Either AlertConfig object or path to config file
        """
        self.state_manager = StateManager()
        self.rules: Dict[str, List[AlertRule]] = {}  # {symbol: [rule1, rule2, ...]}
        
        if isinstance(config_or_path, (str, Path)):
            self.config = load_config(config_or_path)
        else:
            self.config = config_or_path
            
        self._initialize_rules()
        
    def _initialize_rules(self) -> None:
        """
        Initialize all rules from the config
        """
        for symbol, symbol_config in self.config.symbols.items():
            if symbol not in self.rules:
                self.rules[symbol] = []
                
            # Price level rules
            for rule_config in symbol_config.price_levels:
                rule = PriceLevelRule(symbol, rule_config.dict())
                self.rules[symbol].append(rule)
                
            # Percentage change rules
            for rule_config in symbol_config.percentage_changes:
                rule = PercentageChangeRule(symbol, rule_config.dict())
                self.rules[symbol].append(rule)
                
            # Volatility rules
            for rule_config in symbol_config.volatility:
                rule = VolatilityRule(symbol, rule_config.dict())
                self.rules[symbol].append(rule)
                
            # CVD rules - ADD THIS SECTION
            for rule_config in symbol_config.cvd:
                rule = CVDRule(symbol, rule_config.dict())
                self.rules[symbol].append(rule)
                
            logger.info(f"Initialized {len(self.rules[symbol])} rules for {symbol}")

    
    def get_symbols(self) -> List[str]:
        """Get all symbols with rules"""
        return list(self.rules.keys())
    
    def get_rules_for_symbol(self, symbol: str) -> List[AlertRule]:
        """Get all rules for a specific symbol"""
        return self.rules.get(symbol, [])
    
    def evaluate_symbol(self, symbol: str, current_price: float, 
                        extra_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Evaluate all rules for a symbol with the current price
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            extra_data: Additional data needed for evaluation (OHLCV, etc.)
            
        Returns:
            List of alert messages generated
        """
        if symbol not in self.rules:
            logger.warning(f"No rules defined for {symbol}")
            return []
            
        alert_messages = []
        extra_data = extra_data or {}
        
        for rule in self.rules[symbol]:
            try:
                message = rule.evaluate(current_price, self.state_manager, extra_data)
                if message:
                    alert_messages.append(message)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.rule_id} for {symbol}: {e}")
                
        return alert_messages
    
    def reload(self, config_or_path: Any) -> None:
        """
        Reload rules from a new config
        
        Args:
            config_or_path: New config or path to config file
        """
        if isinstance(config_or_path, (str, Path)):
            self.config = load_config(config_or_path)
        else:
            self.config = config_or_path
            
        # Clear existing rules
        self.rules = {}
        # Load new rules
        self._initialize_rules()
        logger.info(f"Reloaded rules - now tracking {len(self.rules)} symbols")
        
    def __repr__(self) -> str:
        rule_counts = {symbol: len(rules) for symbol, rules in self.rules.items()}
        total_rules = sum(rule_counts.values())
        return f"RuleEngine(symbols={len(self.rules)}, total_rules={total_rules})" 