#!/usr/bin/env python3
"""
!!! DEPRECATED !!!

This module has been refactored into a more modular structure.
Please use the new implementation in the sentinel/alert_bot/ package:

    python -m sentinel.alert_bot.main

This monolithic version is kept for backwards compatibility only
and will be removed in a future release.

New code should be added to the modular implementation.
"""

import ccxt
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import yaml
from pathlib import Path
import logging
import statistics # Added for volatility calculation
import warnings

# Show deprecation warning
warnings.warn(
    "The price_alert.py module is deprecated. "
    "Please use the new implementation in sentinel.alert_bot.main", 
    DeprecationWarning, stacklevel=2
)

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Ensure logs directory exists
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
log_file_path = log_dir / 'alert_logs.log'

# File handler
fh = logging.FileHandler(log_file_path)
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Load environment variables
load_dotenv()

N_VOLATILITY_PERIODS = 14  # Number of periods for volatility calculation (e.g., stdev)
MIN_CANDLES_FOR_PCT_CHANGE = 2

class PriceAlert:
    def __init__(self, config_data: Dict[str, Any], main_loop_interval_seconds: int = 60):
        self.exchange = ccxt.coinbase()
        try:
            self.exchange.load_markets()
        except Exception as e:
            logger.error(f"Error loading markets: {e}. Price formatting might be affected.")

        self.config_data = config_data
        self.symbols = list(self.config_data.keys())
        if not self.symbols:
            logger.warning("No symbols found in the configuration data.")
        
        self.main_loop_interval_seconds = main_loop_interval_seconds
        
        self.ohlcv_data: Dict[str, Dict[str, List[list]]] = {symbol: {} for symbol in self.symbols}
        self.last_ohlcv_fetch_time: Dict[str, Dict[str, datetime]] = {symbol: {} for symbol in self.symbols}
        self.last_ticker_prices: Dict[str, float] = {}
        
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.alert_email = os.getenv('ALERT_EMAIL')

        logger.info(f"PriceAlert initialized for symbols: {', '.join(self.symbols)}")
        logger.info(f"Main loop interval: {self.main_loop_interval_seconds} seconds")

    def _get_ccxt_timeframe(self, minutes: int) -> Optional[str]:
        """Converts minutes to ccxt timeframe string."""
        if minutes < 1:
            return None
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440: # Less than a day
            hours = minutes // 60
            return f"{hours}h"
        else: # Days
            days = minutes // 1440
            return f"{days}d"

    def _format_price(self, symbol: str, price: float) -> str:
        """Formats the price according to the symbol's precision."""
        try:
            # Get market precision from CCXT if available
            if symbol in self.exchange.markets:
                precision_info = self.exchange.markets[symbol].get('precision', {})
                price_precision = precision_info.get('price')
                
                if price_precision is not None:
                    # Handle float precision (e.g., 0.00000001)
                    if isinstance(price_precision, float):
                        decimal_places = len(format(price_precision, '.10f').split('.')[1].rstrip('0'))
                        return f"{price:.{decimal_places}f}"
                    # Handle integer precision (number of decimal places)
                    else:
                        return f"{price:.{int(price_precision)}f}"
                        
            # Fallbacks based on price value if no precision info
            if abs(price) > 0 and abs(price) < 0.001:  # Very small prices
                return f"{price:.8f}"
            return f"{price:.2f}"  # Default format
            
        except Exception as e:
            logger.error(f"Error formatting price for {symbol} ({price}): {e}. Defaulting to .2f")
            return f"{price:.2f}"

    def send_email_alert(self, message: str):
        """Send email alert"""
        if not all([self.smtp_username, self.smtp_password, self.alert_email]):
            logger.warning("Email configuration not complete. Skipping email alert.")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.alert_email
            msg['Subject'] = "Crypto Price Alert"
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()
            logger.info("Alert email sent successfully!")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def send_test_alert(self):
        """Send a test email to verify credentials"""
        test_message = f"Test Alert\\n\\nThis is a test message to verify your email configuration is working correctly.\\n\\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        logger.info("Sending test email...")
        self.send_email_alert(test_message)

    def check_percentage_change(self, symbol: str, current_price: float, alert_config: Dict[str, Any], ohlcv_candles: List[list]) -> Optional[str]:
        """Check for significant percentage changes using OHLCV data."""
        if alert_config.get('triggered_session', False):
            return None # Already triggered in this session

        required_candles = MIN_CANDLES_FOR_PCT_CHANGE
        if len(ohlcv_candles) < required_candles:
            logger.debug(f"Not enough candles for {symbol} {alert_config.get('timeframe')}m percentage change (need {required_candles}, got {len(ohlcv_candles)})")
            return None

        # OHLCV candles are [timestamp, open, high, low, close, volume]
        # Last candle (ohlcv_candles[-1]) is the current, possibly incomplete one.
        # Second to last candle (ohlcv_candles[-2]) is the most recent fully completed one.
        # Its closing price is our 'old_price'.
        old_price = ohlcv_candles[-2][4] # Index 4 is close price

        if old_price == 0: # Avoid division by zero
            logger.warning(f"Old price is zero for {symbol}, cannot calculate percentage change.")
            return None

        percentage_diff = ((current_price - old_price) / old_price) * 100
        target_percentage = alert_config['percentage']
        timeframe_minutes = alert_config['timeframe']

        # Check if absolute percentage change meets the threshold
        if abs(percentage_diff) >= target_percentage:
            direction = "risen" if percentage_diff > 0 else "fallen"
            message = (
                f"{symbol} has {direction} by {percentage_diff:.2f}% in the last {timeframe_minutes} minutes. "
                f"(From {self._format_price(symbol, old_price)} to {self._format_price(symbol, current_price)})"
            )
            alert_config['triggered_session'] = True # Mark as triggered for this session
            return message
        return None

    def check_volatility(self, symbol: str, current_price: float, alert_config: Dict[str, Any], ohlcv_candles: List[list]) -> Optional[str]:
        """Check for high volatility using OHLCV data (std dev of closing prices)."""
        if alert_config.get('triggered_session', False):
            return None # Already triggered in this session

        if len(ohlcv_candles) < N_VOLATILITY_PERIODS:
            logger.debug(f"Not enough candles for {symbol} {alert_config.get('timeframe')}m volatility (need {N_VOLATILITY_PERIODS}, got {len(ohlcv_candles)})")
            return None

        # Use closing prices of the last N_VOLATILITY_PERIODS candles
        relevant_candles = ohlcv_candles[-N_VOLATILITY_PERIODS:]
        closes = [c[4] for c in relevant_candles] # Index 4 is close price

        if not closes or len(closes) < 2: # statistics.stdev needs at least 2 data points
            logger.debug(f"Not enough closing prices for stdev calculation for {symbol}.")
            return None
        
        std_dev = statistics.stdev(closes)
        
        if current_price == 0: # Avoid division by zero
            logger.warning(f"Current price is zero for {symbol}, cannot calculate volatility percentage.")
            return None

        # Volatility as a percentage of the current price
        volatility_percentage = (std_dev / current_price) * 100
        target_threshold = alert_config['threshold']
        timeframe_minutes = alert_config['timeframe']

        if volatility_percentage >= target_threshold:
            message = (
                f"{symbol} shows high volatility of {volatility_percentage:.2f}% over the last ~{timeframe_minutes * N_VOLATILITY_PERIODS / 60:.1f} hours (based on {N_VOLATILITY_PERIODS} periods of {timeframe_minutes}m candles). "
                f"(StdDev: {self._format_price(symbol, std_dev)}, Current Price: {self._format_price(symbol, current_price)})"
            )
            # The timeframe description in the message can be a bit tricky if timeframe_minutes varies.
            # For now, this gives an idea of the total period length used for stdev calc.
            alert_config['triggered_session'] = True # Mark as triggered for this session
            return message
        return None

    def check_alerts(self, symbol: str, current_price: float):
        """Check if any price alerts have been triggered based on config_data."""
        symbol_config = self.config_data.get(symbol)
        if not symbol_config:
            return

        alerts_triggered_messages = []

        # 1. Price Level Alerts
        if 'price_levels' in symbol_config:
            for alert_conf in symbol_config['price_levels']:
                price_level = float(alert_conf['price'])
                condition = alert_conf['condition']
                # Basic check; consider adding state to prevent re-alerting immediately
                if condition == 'above' and current_price > price_level:
                    message = f"{symbol} is now above {self._format_price(symbol, price_level)} (Current: {self._format_price(symbol, current_price)})"
                    alerts_triggered_messages.append(message)
                elif condition == 'below' and current_price < price_level:
                    message = f"{symbol} is now below {self._format_price(symbol, price_level)} (Current: {self._format_price(symbol, current_price)})"
                    alerts_triggered_messages.append(message)
        
        # 2. Percentage Change Alerts (OHLCV based - Stage 2)
        if 'percentage_changes' in symbol_config:
            for alert_conf in symbol_config['percentage_changes']:
                # OHLCV fetching and checking logic will go here in Stage 2
                # For now, it will call the placeholder check_percentage_change
                timeframe_minutes = alert_conf.get('timeframe')
                ccxt_tf = self._get_ccxt_timeframe(timeframe_minutes) if timeframe_minutes else None
                if ccxt_tf and symbol in self.ohlcv_data and ccxt_tf in self.ohlcv_data[symbol]:
                    candles = self.ohlcv_data[symbol][ccxt_tf]
                    if candles:
                        msg = self.check_percentage_change(symbol, current_price, alert_conf, candles)
                        if msg: alerts_triggered_messages.append(msg)
                    else:
                        logger.debug(f"No OHLCV candles available for {symbol} {ccxt_tf} to check percentage_changes.")
                else:
                    logger.debug(f"OHLCV data not ready for {symbol} {ccxt_tf} for percentage_changes (or no timeframe specified).")

        # 3. Volatility Alerts (OHLCV based - Stage 2)
        if 'volatility' in symbol_config:
            for alert_conf in symbol_config['volatility']:
                # OHLCV fetching and checking logic will go here in Stage 2
                timeframe_minutes = alert_conf.get('timeframe')
                ccxt_tf = self._get_ccxt_timeframe(timeframe_minutes) if timeframe_minutes else None
                if ccxt_tf and symbol in self.ohlcv_data and ccxt_tf in self.ohlcv_data[symbol]:
                    candles = self.ohlcv_data[symbol][ccxt_tf]
                    if candles:
                        msg = self.check_volatility(symbol, current_price, alert_conf, candles)
                        if msg: alerts_triggered_messages.append(msg)
                    else:
                        logger.debug(f"No OHLCV candles available for {symbol} {ccxt_tf} to check volatility.")
                else:
                    logger.debug(f"OHLCV data not ready for {symbol} {ccxt_tf} for volatility (or no timeframe specified).")

        for msg in alerts_triggered_messages:
            logger.info(f"ALERT: {msg}") # Log the alert locally
            self.send_email_alert(msg)

    def _fetch_ohlcv_if_needed(self, symbol: str, alert_configs: List[Dict[str, Any]]):
        """Fetches OHLCV data for the symbol if required by any alert and if cooldown passed."""
        required_timeframes_minutes = set()
        for alert_conf in alert_configs:
            if 'timeframe' in alert_conf:
                required_timeframes_minutes.add(alert_conf['timeframe'])

        for tf_minutes in required_timeframes_minutes:
            ccxt_tf = self._get_ccxt_timeframe(tf_minutes)
            if not ccxt_tf: continue

            now = datetime.now()
            last_fetch = self.last_ohlcv_fetch_time.get(symbol, {}).get(ccxt_tf)
            # Fetch if never fetched, or if (time since last fetch >= timeframe duration)
            # Example: for a '5m' timeframe, fetch every 5 minutes.
            should_fetch = False
            if last_fetch is None:
                should_fetch = True
            else:
                if (now - last_fetch) >= timedelta(minutes=tf_minutes):
                    should_fetch = True
            
            if should_fetch:
                try:
                    # Determine number of candles. For now, a fixed number.
                    # For percentage change, 2 might be enough (current forming, last closed).
                    # For volatility, more might be needed (e.g., 20-50).
                    # Let's use a heuristic or make it configurable later.
                    limit = 50 # Default limit, can be refined per alert type
                    logger.info(f"Fetching {limit} OHLCV candles for {symbol} ({ccxt_tf})...")
                    candles = self.exchange.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=limit)
                    if symbol not in self.ohlcv_data: self.ohlcv_data[symbol] = {}
                    self.ohlcv_data[symbol][ccxt_tf] = candles
                    if symbol not in self.last_ohlcv_fetch_time: self.last_ohlcv_fetch_time[symbol] = {}
                    self.last_ohlcv_fetch_time[symbol][ccxt_tf] = now
                    logger.info(f"Fetched {len(candles)} OHLCV candles for {symbol} ({ccxt_tf}).")
                except Exception as e:
                    logger.error(f"Error fetching OHLCV for {symbol} ({ccxt_tf}): {e}")
                    # Ensure old data isn't used if fetch fails, or handle staleness
                    if symbol in self.ohlcv_data and ccxt_tf in self.ohlcv_data[symbol]:
                        del self.ohlcv_data[symbol][ccxt_tf] # Invalidate old data on error

    def run(self):
        """Main loop to fetch prices and check alerts"""
        logger.info(f"Starting price monitoring for {', '.join(self.symbols)}")
        logger.info("Press Ctrl+C to stop")
        
        if not self.symbols:
            logger.warning("No symbols to monitor. Exiting.")
            return

        while True:
            try:
                for symbol in self.symbols:
                    symbol_config = self.config_data.get(symbol)
                    if not symbol_config: continue

                    try:
                        # Fetch current ticker price
                        ticker = self.exchange.fetch_ticker(symbol)
                        current_price = ticker['last']
                        self.last_ticker_prices[symbol] = current_price
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        logger.info(f"[{timestamp}] {symbol}: {self._format_price(symbol, current_price)}")
                        
                        # Determine all alert configs that need OHLCV for this symbol
                        ohlcv_alert_configs = []
                        if 'percentage_changes' in symbol_config:
                            ohlcv_alert_configs.extend(symbol_config['percentage_changes'])
                        if 'volatility' in symbol_config:
                            ohlcv_alert_configs.extend(symbol_config['volatility'])
                        
                        if ohlcv_alert_configs:
                            self._fetch_ohlcv_if_needed(symbol, ohlcv_alert_configs)
                        
                        # Perform all checks for the symbol
                        self.check_alerts(symbol, current_price)
                    
                    except ccxt.NetworkError as e:
                        logger.error(f"Network error for {symbol}: {e}. Will retry.")
                    except ccxt.ExchangeError as e:
                        logger.error(f"Exchange error for {symbol}: {e}. Will retry.")
                    except Exception as e:
                        logger.error(f"Error processing symbol {symbol}: {e}")
                
                logger.debug(f"Main loop completed. Sleeping for {self.main_loop_interval_seconds}s.")
                time.sleep(self.main_loop_interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user (Ctrl+C).")
                break
            except Exception as e:
                logger.error(f"Unhandled error in main loop: {e}", exc_info=True)
                time.sleep(60)  # Wait a minute before retrying

def create_example_config():
    """Create an example configuration file"""
    example_config = {
        'BTC/USD': {
            'price_levels': [
                {'price': 50000, 'condition': 'above'},
                {'price': 45000, 'condition': 'below'}
            ],
            'percentage_changes': [
                {'percentage': 5, 'timeframe': 10} # 10 minutes
            ],
            'volatility': [
                {'threshold': 2, 'timeframe': 5} # 5 minutes
            ]
        },
        'ETH/USD': {
            'price_levels': [
                {'price': 3000, 'condition': 'above'},
                {'price': 2500, 'condition': 'below'}
            ],
            'percentage_changes': [
                {'percentage': 7, 'timeframe': 15}
            ],
            'volatility': [
                {'threshold': 3, 'timeframe': 5}
            ]
        },
        'PEPE/USD': { # Example for high precision
            'price_levels': [
                {'price': 0.00001700, 'condition': 'above'},
                {'price': 0.00001200, 'condition': 'below'}
            ]
        }
    }
    
    # Write the config to the new location used by the refactored code
    config_path = Path('sentinel/alert_bot/config/alerts_config.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(example_config, f, default_flow_style=False)
    logger.info(f"Created example configuration file at {config_path}")
    
    # DEPRECATED: Also write to the old location for backward compatibility
    old_config_path = Path('sentinel/alert_bot/alerts_config.yaml')
    with open(old_config_path, 'w') as f:
        yaml.dump(example_config, f, default_flow_style=False)
    logger.info(f"Also created config file at {old_config_path} (deprecated location)")

def main():
    parser = argparse.ArgumentParser(description='Crypto Price Alert Monitor - Config Driven')
    parser.add_argument('--config', type=str, default='sentinel/alert_bot/config/alerts_config.yaml', help='Path to YAML configuration file (default: sentinel/alert_bot/config/alerts_config.yaml)')
    parser.add_argument('--main-loop-interval', type=int, default=60, help='Main loop check interval in seconds (default: 60)')
    parser.add_argument('--create-config', action='store_true', help='Create an example configuration file and exit')
    parser.add_argument('--test-email', action='store_true', help='Send a test email to verify credentials and exit')
    
    args = parser.parse_args()
    
    if args.create_config:
        create_example_config()
        return

    config_data = None
    try:
        with open(args.config, 'r') as f:
            config_data = yaml.safe_load(f)
        if not isinstance(config_data, dict):
            logger.error(f"Error: Config file {args.config} is not a valid YAML dictionary. Exiting.")
            return
        if not config_data:
            logger.error(f"Error: Config file {args.config} is empty or invalid. Exiting.")
            return
            
    except FileNotFoundError:
        logger.error(f"Error: Config file '{args.config}' not found. Use --create-config to generate an example. Exiting.")
        return
    except Exception as e:
        logger.error(f"Error reading or parsing config file {args.config}: {e}. Exiting.")
        return
    
    # Initialize PriceAlert with the loaded config_data
    monitor = PriceAlert(config_data=config_data, main_loop_interval_seconds=args.main_loop_interval)
    
    if args.test_email:
        monitor.send_test_alert()
        return
    
    monitor.run()

if __name__ == "__main__":
    main() 