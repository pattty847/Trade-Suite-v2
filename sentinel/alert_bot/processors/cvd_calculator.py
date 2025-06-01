import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from collections import deque
from sentinel.alert_bot.models.trade_data import TradeData

logger = logging.getLogger(__name__)

class CVDCalculator:
    """Calculates Cumulative Volume Delta from trade data"""
    
    def __init__(self, lookback_minutes: int = 60):
        self.lookback_minutes = lookback_minutes
        self.trades: deque[TradeData] = deque()  # Store TradeData objects
        self.cvd_value = 0.0
        self.last_update = datetime.now() # Consider making this Optional[datetime] and setting it on first trade
    
    def add_trade(self, trade: TradeData):
        """Add a new trade and update CVD"""
        self.trades.append(trade)
        self.cvd_value += trade.delta
        self.last_update = trade.timestamp
        
        # Clean old trades outside lookback window
        cutoff_time = trade.timestamp - timedelta(minutes=self.lookback_minutes)
        while self.trades and self.trades[0].timestamp < cutoff_time:
            old_trade = self.trades.popleft()
            self.cvd_value -= old_trade.delta
    
    def get_cvd(self) -> float:
        """Get current CVD value"""
        return self.cvd_value
    
    def get_cvd_change(self, minutes: int) -> Optional[float]:
        """Get CVD change over specified minutes"""
        if not self.trades:
            return None
            
        # Ensure last_update is a datetime object before using it for timedelta calculation
        # This check might be redundant if self.last_update is always set before this method is called
        # after trades have been added.
        if not isinstance(self.last_update, datetime):
            logger.warning("CVDCalculator.last_update is not set, cannot calculate change.")
            return None

        target_start_time = self.last_update - timedelta(minutes=minutes)
        
        # Calculate CVD at the start of the window
        # We need to sum deltas of trades *older* than the window that are still in our lookback
        # and subtract this from the current CVD. 
        # A simpler way might be to sum deltas of trades *within* the window.

        cvd_at_window_start = 0.0
        # Iterate backwards to find the CVD at the point `minutes` ago from `last_update`
        # This needs to be precise. The current self.cvd_value includes all trades in self.trades.
        # We want to find out what the CVD was `minutes` ago from `self.last_update`.

        # Summing deltas of trades that occurred *within* the specified `minutes` window up to `self.last_update`
        change_in_window = 0.0
        for trade in reversed(self.trades):
            if trade.timestamp >= target_start_time:
                change_in_window += trade.delta
            else:
                # This trade is older than the start of our change window
                break 
        return change_in_window

    def get_buy_sell_ratio(self, minutes: Optional[int] = None) -> Dict[str, float]:
        """Get buy/sell volume ratio over specified period (or entire lookback if minutes is None)"""
        relevant_trades: list[TradeData]
        if minutes is not None:
            if not isinstance(self.last_update, datetime):
                logger.warning("CVDCalculator.last_update is not set, cannot calculate ratio for specific minutes.")
                return {'buy_ratio': 0.5, 'sell_ratio': 0.5, 'buy_volume': 0, 'sell_volume': 0}
            cutoff_time = self.last_update - timedelta(minutes=minutes)
            relevant_trades = [t for t in self.trades if t.timestamp >= cutoff_time]
        else:
            relevant_trades = list(self.trades)
        
        if not relevant_trades:
            return {'buy_ratio': 0.5, 'sell_ratio': 0.5, 'buy_volume': 0, 'sell_volume': 0}
            
        buy_volume = sum(t.volume for t in relevant_trades if t.side == 'buy')
        sell_volume = sum(t.volume for t in relevant_trades if t.side == 'sell')
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return {'buy_ratio': 0.5, 'sell_ratio': 0.5, 'buy_volume': buy_volume, 'sell_volume': sell_volume}
        
        return {
            'buy_ratio': buy_volume / total_volume,
            'sell_ratio': sell_volume / total_volume,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume
        } 