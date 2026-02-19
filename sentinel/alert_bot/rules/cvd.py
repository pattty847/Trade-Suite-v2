#!/usr/bin/env python3
from typing import Optional, Dict, Any
import logging
from .base import AlertRule

logger = logging.getLogger(__name__)

class CVDRule(AlertRule):
    """
    Rule that triggers based on Cumulative Volume Delta (CVD) conditions
    
    CVD tracks the cumulative difference between buy and sell volume,
    helping identify institutional flow and market sentiment shifts.
    """
    
    def __init__(self, symbol: str, config: Dict[str, Any]):
        """
        Initialize a CVD rule
        
        Args:
            symbol: Trading symbol this rule applies to
            config: Configuration with CVD parameters
        """
        super().__init__(symbol, "cvd", config)
        
        # CVD threshold (absolute change in CVD)
        self.cvd_threshold = config.get("cvd_threshold")
        
        # CVD percentage change threshold (% change relative to current CVD)
        self.cvd_percentage_threshold = config.get("cvd_percentage_threshold")
        
        # Time window for measuring change (in minutes)
        self.timeframe_minutes = int(config.get("timeframe", 15))
        
        # Buy/sell ratio threshold (0.0 to 1.0)
        self.buy_ratio_threshold = config.get("buy_ratio_threshold")
        self.sell_ratio_threshold = config.get("sell_ratio_threshold")
        
        # CVD divergence detection
        self.detect_divergence = config.get("detect_divergence", False)
        
        # Alert type
        self.alert_type = config.get("type", "change")  # 'change', 'ratio', 'divergence', 'level'
        
        # For level-based alerts
        self.cvd_level = config.get("cvd_level")
        self.level_condition = config.get("level_condition", "above")  # 'above' or 'below'
        
        # Validate configuration
        self._validate_config()
        
        # More descriptive rule_id
        self.rule_id = f"cvd_{self.alert_type}_{self.timeframe_minutes}min_{self.symbol}"
        
        logger.debug(f"Created CVD {self.alert_type} rule (timeframe: {self.timeframe_minutes}m) for {symbol}")
    
    def _validate_config(self):
        """Validate the CVD rule configuration"""
        if self.alert_type == "change":
            if not self.cvd_threshold and not self.cvd_percentage_threshold:
                raise ValueError("CVD change alerts require either cvd_threshold or cvd_percentage_threshold")
        elif self.alert_type == "ratio":
            if not self.buy_ratio_threshold and not self.sell_ratio_threshold:
                raise ValueError("CVD ratio alerts require either buy_ratio_threshold or sell_ratio_threshold")
        elif self.alert_type == "level":
            if self.cvd_level is None:
                raise ValueError("CVD level alerts require cvd_level")
        elif self.alert_type == "divergence":
            # Divergence detection will be implemented later
            pass
    
    def evaluate(self, current_price: float, state_manager, extra_data=None) -> Optional[str]:
        """
        Check if CVD conditions are met for triggering an alert
        
        Args:
            current_price: Current price of the symbol
            state_manager: StateManager for tracking rule state
            extra_data: Dict containing 'cvd_data' with CVD information
                        
        Returns:
            Alert message if triggered, None otherwise
        """
        try:
            if not state_manager.can_trigger(self.symbol, self.rule_id, self.cooldown_seconds):
                return None  # Still in cooldown period
            
            # We need CVD data to evaluate
            if not extra_data or 'cvd_data' not in extra_data:
                logger.debug(f"No CVD data available for {self.symbol}")
                return None
            
            cvd_data = extra_data['cvd_data']
            
            # Route to appropriate evaluation method based on alert type
            if self.alert_type == "change":
                message = self._evaluate_change(cvd_data, current_price)
            elif self.alert_type == "ratio":
                message = self._evaluate_ratio(cvd_data, current_price)
            elif self.alert_type == "level":
                message = self._evaluate_level(cvd_data, current_price)
            elif self.alert_type == "divergence":
                message = self._evaluate_divergence(cvd_data, current_price)
            else:
                logger.error(f"Unknown CVD alert type: {self.alert_type}")
                return None
            
            if message:
                state_manager.mark_triggered(self.symbol, self.rule_id)
                logger.info(f"TRIGGERED: {message}")
                return message
                
            return None
            
        except Exception as e:
            logger.error(f"Error in CVD evaluation for {self.symbol}: {e}")
            return None
    
    def _evaluate_change(self, cvd_data: Dict[str, Any], current_price: float) -> Optional[str]:
        """Evaluate CVD change-based alerts"""
        # Get CVD change for our timeframe
        cvd_change_key = f"cvd_change_{self.timeframe_minutes}m"
        cvd_change = cvd_data.get(cvd_change_key)
        
        if cvd_change is None:
            logger.debug(f"No CVD change data for {self.timeframe_minutes}m timeframe")
            return None
        
        current_cvd = cvd_data.get('cvd', 0)
        
        # Check absolute threshold
        if self.cvd_threshold and abs(cvd_change) >= self.cvd_threshold:
            direction = "increased" if cvd_change > 0 else "decreased"
            sentiment = "BULLISH" if cvd_change > 0 else "BEARISH"
            
            return (
                f"🔥 {sentiment} CVD ALERT: {self.symbol} CVD has {direction} by "
                f"{abs(cvd_change):.2f} in the last {self.timeframe_minutes} minutes. "
                f"Current CVD: {current_cvd:.2f}, Price: {self.format_price(current_price)}"
            )
        
        # Check percentage threshold
        if self.cvd_percentage_threshold and current_cvd != 0:
            cvd_pct_change = (cvd_change / abs(current_cvd)) * 100
            
            if abs(cvd_pct_change) >= self.cvd_percentage_threshold:
                direction = "increased" if cvd_change > 0 else "decreased"
                sentiment = "BULLISH" if cvd_change > 0 else "BEARISH"
                
                return (
                    f"📈 {sentiment} CVD % ALERT: {self.symbol} CVD has {direction} by "
                    f"{abs(cvd_pct_change):.1f}% in the last {self.timeframe_minutes} minutes. "
                    f"Current CVD: {current_cvd:.2f}, Price: {self.format_price(current_price)}"
                )
        
        return None
    
    def _evaluate_ratio(self, cvd_data: Dict[str, Any], current_price: float) -> Optional[str]:
        """Evaluate buy/sell ratio-based alerts"""
        # Get ratio data for our timeframe
        ratio_key = f"buy_sell_ratio_{self.timeframe_minutes}m"
        ratio_data = cvd_data.get(ratio_key, {})
        
        buy_ratio = ratio_data.get('buy_ratio', 0.5)
        sell_ratio = ratio_data.get('sell_ratio', 0.5)
        buy_volume = ratio_data.get('buy_volume', 0)
        sell_volume = ratio_data.get('sell_volume', 0)
        
        # Check buy ratio threshold
        if self.buy_ratio_threshold and buy_ratio >= self.buy_ratio_threshold:
            return (
                f"🟢 BULLISH VOLUME ALERT: {self.symbol} showing {buy_ratio:.1%} BUY volume "
                f"over the last {self.timeframe_minutes} minutes. "
                f"Buy: {buy_volume:.2f} vs Sell: {sell_volume:.2f}, "
                f"Price: {self.format_price(current_price)}"
            )
        
        # Check sell ratio threshold
        if self.sell_ratio_threshold and sell_ratio >= self.sell_ratio_threshold:
            return (
                f"🔴 BEARISH VOLUME ALERT: {self.symbol} showing {sell_ratio:.1%} SELL volume "
                f"over the last {self.timeframe_minutes} minutes. "
                f"Buy: {buy_volume:.2f} vs Sell: {sell_volume:.2f}, "
                f"Price: {self.format_price(current_price)}"
            )
        
        return None
    
    def _evaluate_level(self, cvd_data: Dict[str, Any], current_price: float) -> Optional[str]:
        """Evaluate CVD level-based alerts"""
        current_cvd = cvd_data.get('cvd', 0)
        
        if self.cvd_level is None:
            return None
        
        triggered = False
        if self.level_condition == "above" and current_cvd > self.cvd_level:
            triggered = True
            message = (
                f"📊 CVD LEVEL ALERT: {self.symbol} CVD is now above {self.cvd_level:.2f} "
                f"(Current: {current_cvd:.2f}, Price: {self.format_price(current_price)})"
            )
        elif self.level_condition == "below" and current_cvd < self.cvd_level:
            triggered = True
            message = (
                f"📊 CVD LEVEL ALERT: {self.symbol} CVD is now below {self.cvd_level:.2f} "
                f"(Current: {current_cvd:.2f}, Price: {self.format_price(current_price)})"
            )
        
        return message if triggered else None
    
    def _evaluate_divergence(self, cvd_data: Dict[str, Any], current_price: float) -> Optional[str]:
        """Evaluate CVD divergence alerts (placeholder for future implementation)"""
        # This would require tracking price trends vs CVD trends
        # Could compare price direction over timeframe vs CVD direction
        # For now, return None - this is a complex feature for later
        logger.debug("CVD divergence detection not yet implemented")
        return None