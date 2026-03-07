#!/usr/bin/env python3
from typing import Optional, Dict, Any, List
import logging
import statistics
from .base import AlertRule

logger = logging.getLogger(__name__)

class PercentageChangeRule(AlertRule):
    """
    Rule that triggers when price changes by X% within specified timeframe
    """
    
    def __init__(self, symbol: str, config: Dict[str, Any]):
        """
        Initialize a percentage change rule
        
        Args:
            symbol: Trading symbol this rule applies to
            config: Configuration with percentage threshold and timeframe
        """
        super().__init__(symbol, "percentage_change", config)
        self.percentage = float(config["percentage"])
        self.timeframe_minutes = int(config["timeframe"])
        
        # More descriptive rule_id
        self.rule_id = f"pct_change_{self.percentage}_{self.timeframe_minutes}min_{self.symbol}"
        
        logger.debug(f"Created {self.percentage}% change rule (timeframe: {self.timeframe_minutes}m) for {symbol}")
    
    def evaluate(self, current_price: float, state_manager, extra_data=None) -> Optional[str]:
        """
        Check if price has changed by the specified percentage within timeframe
        
        Args:
            current_price: Current price of the symbol
            state_manager: StateManager for tracking rule state
            extra_data: Dict containing 'ohlcv_data' with candles for this symbol/timeframe
                        Format: [timestamp, open, high, low, close, volume]
                        
        Returns:
            Alert message if triggered, None otherwise
        """
        try:
            if not state_manager.can_trigger(self.symbol, self.rule_id, self.cooldown_seconds):
                return None  # Still in cooldown period
            
            # We need the OHLCV data to calculate percentage change
            if not extra_data:
                logger.debug(f"No extra_data available for {self.symbol} to evaluate percentage change")
                return None
                
            if 'ohlcv_data' not in extra_data:
                logger.debug(f"No ohlcv_data found in extra_data for {self.symbol}. Keys: {list(extra_data.keys())}")
                return None
                
            # Extract the correct timeframe from the ohlcv_data dictionary
            ohlcv_data = extra_data.get('ohlcv_data', {})
            
            # Log the available timeframes
            available_timeframes = list(ohlcv_data.keys())
            logger.debug(f"Available timeframes for {self.symbol}: {available_timeframes}, looking for {self.timeframe_minutes}m")
            
            # Get candles for this specific timeframe
            candles = ohlcv_data.get(self.timeframe_minutes, [])
            
            if not candles:
                logger.debug(f"No candles found for {self.symbol} with timeframe {self.timeframe_minutes}m")
                return None
                
            if len(candles) < 2:
                logger.debug(f"Insufficient candles for {self.symbol} ({self.timeframe_minutes}m): only {len(candles)} available, need at least 2")
                return None
                
            # Use the second most recent candle as reference point (most recent may be incomplete)
            reference_candle = candles[-2]
            reference_price = reference_candle[4]  # Index 4 is close price
            
            if reference_price == 0:  # Avoid division by zero
                logger.warning(f"Reference price is zero for {self.symbol}, cannot calculate percentage change")
                return None
                
            # Calculate percentage change from reference candle to current price
            percentage_change = ((current_price - reference_price) / reference_price) * 100
            
            logger.debug(f"{self.symbol} percentage change over {self.timeframe_minutes}m: {percentage_change:.2f}% (threshold: {self.percentage}%)")
            
            # Check if absolute percentage change meets the threshold
            if abs(percentage_change) >= self.percentage:
                direction = "risen" if percentage_change > 0 else "fallen"
                message = (
                    f"{self.symbol} has {direction} by {percentage_change:.2f}% in the last {self.timeframe_minutes} minutes. "
                    f"(From {self.format_price(reference_price)} to {self.format_price(current_price)})"
                )
                
                state_manager.mark_triggered(self.symbol, self.rule_id)
                logger.info(f"TRIGGERED: {message}")
                return message
                
            return None
            
        except Exception as e:
            logger.error(f"Error in percentage change evaluation for {self.symbol} ({self.timeframe_minutes}m): {e}")
            return None 