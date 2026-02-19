#!/usr/bin/env python3
from typing import Optional, Dict, Any, List
import logging
import statistics
from .base import AlertRule

logger = logging.getLogger(__name__)

# Number of periods to use for volatility calculation
N_VOLATILITY_PERIODS = 14

class VolatilityRule(AlertRule):
    """
    Rule that triggers when price volatility exceeds a threshold within timeframe
    Volatility is measured as standard deviation of closing prices as a percentage of current price
    """
    
    def __init__(self, symbol: str, config: Dict[str, Any]):
        """
        Initialize a volatility rule
        
        Args:
            symbol: Trading symbol this rule applies to
            config: Configuration with volatility threshold and timeframe
        """
        super().__init__(symbol, "volatility", config)
        self.threshold = float(config["threshold"])
        self.timeframe_minutes = int(config["timeframe"])
        
        # More descriptive rule_id
        self.rule_id = f"volatility_{self.threshold}_{self.timeframe_minutes}min_{self.symbol}"
        
        logger.debug(f"Created {self.threshold}% volatility rule (timeframe: {self.timeframe_minutes}m) for {symbol}")
    
    def evaluate(self, current_price: float, state_manager, extra_data=None) -> Optional[str]:
        """
        Check if price volatility exceeds threshold
        
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
            
            # We need the OHLCV data to calculate volatility
            if not extra_data:
                logger.debug(f"No extra_data available for {self.symbol} to evaluate volatility")
                return None
                
            if 'ohlcv_data' not in extra_data:
                logger.debug(f"No ohlcv_data found in extra_data for {self.symbol}. Keys: {list(extra_data.keys())}")
                return None
                
            # Extract the correct timeframe from the ohlcv_data dictionary
            ohlcv_data = extra_data.get('ohlcv_data', {})
            
            # Log the available timeframes
            available_timeframes = list(ohlcv_data.keys())
            logger.debug(f"Available timeframes for volatility {self.symbol}: {available_timeframes}, looking for {self.timeframe_minutes}m")
            
            # Get candles for this specific timeframe
            candles = ohlcv_data.get(self.timeframe_minutes, [])
            
            if not candles or len(candles) < N_VOLATILITY_PERIODS:
                logger.debug(f"Insufficient candles for {self.symbol} to evaluate volatility (need {N_VOLATILITY_PERIODS}, got {len(candles) if candles else 0})")
                return None
                
            # Use the last N_VOLATILITY_PERIODS candles
            relevant_candles = candles[-N_VOLATILITY_PERIODS:]
            closes = [c[4] for c in relevant_candles]  # Index 4 is close price
            
            # Calculate standard deviation of closing prices
            try:
                std_dev = statistics.stdev(closes)
            except statistics.StatisticsError as e:
                logger.error(f"Error calculating standard deviation for {self.symbol}: {e}")
                return None
                
            if current_price == 0:  # Avoid division by zero
                logger.warning(f"Current price is zero for {self.symbol}, cannot calculate volatility percentage")
                return None
                
            # Volatility as a percentage of the current price
            volatility_percentage = (std_dev / current_price) * 100
            
            logger.debug(f"{self.symbol} volatility over {self.timeframe_minutes}m: {volatility_percentage:.2f}% (threshold: {self.threshold}%)")
            
            # Check if volatility exceeds threshold
            if volatility_percentage >= self.threshold:
                hours_period = round(self.timeframe_minutes * N_VOLATILITY_PERIODS / 60, 1)
                message = (
                    f"{self.symbol} shows high volatility of {volatility_percentage:.2f}% over the last ~{hours_period} hours "
                    f"(based on {N_VOLATILITY_PERIODS} periods of {self.timeframe_minutes}m candles). "
                    f"(StdDev: {self.format_price(std_dev)}, Current Price: {self.format_price(current_price)})"
                )
                
                state_manager.mark_triggered(self.symbol, self.rule_id)
                logger.info(f"TRIGGERED: {message}")
                return message
                
            return None
            
        except Exception as e:
            logger.error(f"Error in volatility evaluation for {self.symbol} ({self.timeframe_minutes}m): {e}")
            return None 