import logging
import pandas as pd
import time
from typing import Dict, List, Optional, Tuple

from trade_suite.gui.utils import timeframe_to_seconds


class ChartProcessor:
    """
    Handles data processing operations for chart components.
    Separates data processing logic from UI rendering.
    """
    
    def __init__(self, exchange: str, symbol: str, timeframe: str, price_precision: float = 0.00001):
        """
        Initialize the chart processor with exchange, symbol and timeframe settings.
        
        Args:
            exchange: Exchange identifier
            symbol: Trading pair symbol (e.g. 'BTC/USD')
            timeframe: Timeframe string (e.g. '1m', '1h')
            price_precision: Minimum price increment for the asset
        """
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.timeframe_seconds = timeframe_to_seconds(timeframe)
        self.price_precision = price_precision
        
        # Initialize empty OHLCV dataframe
        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        
        self.last_candle_timestamp = None
        
    def process_candles(self, candles: pd.DataFrame) -> pd.DataFrame:
        """
        Process raw candle data and store it.
        
        Args:
            candles: DataFrame containing OHLCV data
            
        Returns:
            Processed candle DataFrame
        """
        if isinstance(candles, pd.DataFrame) and not candles.empty:
            # Ensure timestamps are in seconds, not milliseconds
            if "dates" in candles.columns and candles["dates"].max() > 1e12:
                candles['dates'] = candles['dates'] / 1000
                
            self.ohlcv = candles
            
            # Update the last candle timestamp for future candle building
            if not self.ohlcv.empty:
                self.last_candle_timestamp = self.ohlcv["dates"].iloc[-1]
                
        return self.ohlcv
        
    def process_trade(self, trade_data: Dict) -> Optional[pd.DataFrame]:
        """
        Process a single trade and update the OHLCV data if needed.
        
        Args:
            trade_data: Dictionary containing trade information
            
        Returns:
            Updated OHLCV DataFrame if candle was updated, None otherwise
        """
        timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
        price = trade_data["price"]
        volume = trade_data["amount"]

        # Adjust timestamp to the candle boundary
        adjusted_timestamp = timestamp - (timestamp % self.timeframe_seconds)
        
        # Initialize last candle timestamp if not set
        if self.last_candle_timestamp is None and not self.ohlcv.empty:
            self.last_candle_timestamp = self.ohlcv["dates"].iloc[-1]
        elif self.last_candle_timestamp is None:
            self.last_candle_timestamp = adjusted_timestamp
            
        # Check if this trade belongs to a new candle
        if adjusted_timestamp >= self.last_candle_timestamp + self.timeframe_seconds:
            # Start a new candle
            new_candle = {
                "dates": self.last_candle_timestamp + self.timeframe_seconds,
                "opens": price,
                "highs": price,
                "lows": price,
                "closes": price,
                "volumes": volume,
            }
            # Add new candle to the dataframe
            new_candle_df = pd.DataFrame([new_candle])
            self.ohlcv = pd.concat([self.ohlcv, new_candle_df], ignore_index=True)
            self.last_candle_timestamp += self.timeframe_seconds
            return self.ohlcv
            
        elif not self.ohlcv.empty:
            # Update the current candle
            last_idx = self.ohlcv.index[-1]
            self.ohlcv.at[last_idx, "highs"] = max(
                self.ohlcv.at[last_idx, "highs"], price
            )
            self.ohlcv.at[last_idx, "lows"] = min(
                self.ohlcv.at[last_idx, "lows"], price
            )
            self.ohlcv.at[last_idx, "closes"] = price
            self.ohlcv.at[last_idx, "volumes"] += volume
            return self.ohlcv
            
        else:
            # Initialize the first candle
            new_candle = {
                "dates": adjusted_timestamp,
                "opens": price,
                "highs": price,
                "lows": price,
                "closes": price,
                "volumes": volume,
            }
            # Convert to DataFrame
            new_candle_df = pd.DataFrame([new_candle])
            self.ohlcv = new_candle_df
            self.last_candle_timestamp = adjusted_timestamp
            return self.ohlcv
            
    def process_trade_batch(self, trade_batch: List[Dict]) -> Optional[pd.DataFrame]:
        """
        Process a batch of trades and update the OHLCV data.
        
        Args:
            trade_batch: List of trade dictionaries
            
        Returns:
            Updated OHLCV DataFrame if changes were made, None otherwise
        """
        if not trade_batch:
            return None
            
        # Sort trades by timestamp to ensure proper processing
        trade_batch.sort(key=lambda x: x["timestamp"])
        
        # Process each trade
        updated = False
        for trade in trade_batch:
            result = self.process_trade(trade)
            if result is not None:
                updated = True
                
        return self.ohlcv if updated else None
    
    def try_resample(self, new_timeframe: str) -> Tuple[bool, Optional[pd.DataFrame]]:
        """
        Attempt to resample candles to a new timeframe.
        
        Args:
            new_timeframe: New timeframe string (e.g. '1h', '4h')
            
        Returns:
            Tuple containing:
            - Boolean indicating if resampling was successful
            - Resampled DataFrame if successful, None otherwise
        """
        new_timeframe_seconds = timeframe_to_seconds(new_timeframe)
        
        # Can only resample to larger timeframes
        if new_timeframe_seconds <= self.timeframe_seconds or self.ohlcv.empty:
            self.timeframe = new_timeframe
            self.timeframe_seconds = new_timeframe_seconds
            return False, None
            
        # Convert to datetime if timestamps are numeric
        df_copy = self.ohlcv.copy()
        
        # Convert timestamps to pandas datetime
        if "dates" in df_copy.columns:
            df_copy["dates_dt"] = pd.to_datetime(df_copy["dates"], unit='s')
            df_copy.set_index("dates_dt", inplace=True)
            
            # Resample to the new timeframe
            rule = self._timeframe_to_pandas_rule(new_timeframe)
            resampled = pd.DataFrame()
            
            # Apply resampling rules for OHLCV
            resampled["opens"] = df_copy["opens"].resample(rule).first()
            resampled["highs"] = df_copy["highs"].resample(rule).max()
            resampled["lows"] = df_copy["lows"].resample(rule).min()
            resampled["closes"] = df_copy["closes"].resample(rule).last()
            resampled["volumes"] = df_copy["volumes"].resample(rule).sum()
            
            # Convert timestamps back to seconds
            resampled["dates"] = resampled.index.astype('int64') // 10**9
            
            # Reset index to get dates as a column
            resampled = resampled.reset_index(drop=True)
            
            # Update state
            self.ohlcv = resampled
            self.timeframe = new_timeframe
            self.timeframe_seconds = new_timeframe_seconds
            
            # Update last candle timestamp if there are candles
            if not self.ohlcv.empty:
                self.last_candle_timestamp = self.ohlcv["dates"].iloc[-1]
                
            return True, resampled
            
        return False, None
    
    def set_symbol(self, new_symbol: str, price_precision: float = None) -> None:
        """
        Update the symbol and optionally the price precision.
        
        Args:
            new_symbol: New trading pair symbol
            price_precision: New price precision value (optional)
        """
        self.symbol = new_symbol
        if price_precision is not None:
            self.price_precision = price_precision
        
        # Reset OHLCV data when symbol changes
        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )
        self.last_candle_timestamp = None
    
    def set_timeframe(self, new_timeframe: str) -> None:
        """
        Update the timeframe without resampling.
        
        Args:
            new_timeframe: New timeframe string
        """
        self.timeframe = new_timeframe
        self.timeframe_seconds = timeframe_to_seconds(new_timeframe)
        
    def get_candle_data(self) -> pd.DataFrame:
        """
        Get the current OHLCV data.
        
        Returns:
            Current OHLCV DataFrame
        """
        return self.ohlcv.copy()
    
    def _timeframe_to_pandas_rule(self, timeframe: str) -> str:
        """
        Convert a timeframe string to a pandas resampling rule.
        
        Args:
            timeframe: Timeframe string (e.g. '1m', '1h')
            
        Returns:
            Pandas resampling rule
        """
        # Extract numeric value and unit
        import re
        match = re.match(r'(\d+)([mhdwM])', timeframe)
        if not match:
            logging.warning(f"Invalid timeframe format: {timeframe}, defaulting to '1min'")
            return '1min'
            
        value, unit = match.groups()
        
        # Convert to pandas resample format
        unit_map = {
            'm': 'min',
            'h': 'H',
            'd': 'D',
            'w': 'W',
            'M': 'M'
        }
        
        return f"{value}{unit_map.get(unit, 'min')}" 