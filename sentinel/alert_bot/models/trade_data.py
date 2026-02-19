from datetime import datetime
from typing import Optional

class TradeData:
    """Represents a single trade"""
    def __init__(self, timestamp: datetime, price: float, volume: float, side: str):
        self.timestamp = timestamp
        self.price = price
        self.volume = volume
        self.side = side  # 'buy' or 'sell'
        self.delta = volume if side == 'buy' else -volume
    
    def __repr__(self):
        return f"Trade({self.side}, {self.price}, {self.volume}, {self.timestamp})"

    @staticmethod
    def from_ccxt_trade(trade_raw: dict) -> Optional['TradeData']:
        """
        Parse a raw trade dictionary from CCXT into a TradeData object.
        
        Args:
            trade_raw: Raw trade data from ccxt
            
        Returns:
            TradeData object or None if parsing fails
        """
        try:
            timestamp_ms = trade_raw.get('timestamp')
            price = trade_raw.get('price')
            amount = trade_raw.get('amount')
            side = trade_raw.get('side')

            if None in [timestamp_ms, price, amount, side]:
                # logger.warning(f"Missing essential fields in trade_raw: {trade_raw}")
                return None

            timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0)
            
            # Validate side (standardize if necessary, e.g., some exchanges might use 'b'/'s')
            if side.lower() not in ['buy', 'sell']:
                # logger.warning(f"Unknown trade side: {side} in {trade_raw}")
                return None

            return TradeData(timestamp=timestamp, price=float(price), volume=float(amount), side=side.lower())
        except Exception as e:
            # logger.error(f"Error parsing trade data: {e} - Raw: {trade_raw}", exc_info=True)
            return None 