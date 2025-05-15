#!/usr/bin/env python3
import ccxt
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import yaml
from pathlib import Path

# Load environment variables
load_dotenv()

class PriceAlert:
    def __init__(self, symbols: List[str], interval_minutes=5):
        self.exchange = ccxt.coinbase()
        self.symbols = symbols if isinstance(symbols, list) else [symbols]
        self.interval = interval_minutes * 60  # Convert to seconds
        self.alerts: Dict[str, Dict[Any, Any]] = {}  # Symbol -> {alert_key: alert_condition/data}
        self.price_history: Dict[str, List[float]] = {}  # Store recent price history for each symbol
        self.history_length = 10  # Number of price points to keep for each symbol
        
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.alert_email = os.getenv('ALERT_EMAIL')

    def add_alert(self, symbol: str, price_level: float, condition: str = 'above'):
        """Add a price alert level for a specific symbol"""
        if symbol not in self.alerts:
            self.alerts[symbol] = {}
        self.alerts[symbol][price_level] = condition
        print(f"Added alert for {symbol} {condition} {price_level}")

    def add_percentage_change_alert(self, symbol: str, percentage: float, timeframe_minutes: int = 5):
        """Add an alert for percentage change over a timeframe"""
        if symbol not in self.alerts:
            self.alerts[symbol] = {}
        alert_key = f"pct_change_{percentage}_{timeframe_minutes}"
        self.alerts[symbol][alert_key] = {
            'type': 'percentage_change',
            'percentage': percentage,
            'timeframe': timeframe_minutes,
            'triggered': False
        }
        print(f"Added {percentage}% change alert for {symbol} over {timeframe_minutes} minutes")

    def add_volatility_alert(self, symbol: str, threshold: float, timeframe_minutes: int = 5):
        """Add an alert for high volatility"""
        if symbol not in self.alerts:
            self.alerts[symbol] = {}
        alert_key = f"volatility_{threshold}_{timeframe_minutes}"
        self.alerts[symbol][alert_key] = {
            'type': 'volatility',
            'threshold': threshold,
            'timeframe': timeframe_minutes,
            'triggered': False
        }
        print(f"Added volatility alert for {symbol} (threshold: {threshold}%) over {timeframe_minutes} minutes")

    def load_config_data(self, config_data: Dict[str, Any]):
        """Load alert configuration from pre-loaded config data"""
        try:
            if not isinstance(config_data, dict):
                raise ValueError("Config data must be a dictionary of symbol configurations")
            
            for symbol, alerts_config_for_symbol in config_data.items():
                if symbol not in self.symbols: # self.symbols are the ones PriceAlert was initialized with
                    # This is informational: config has data for a symbol we're not actively monitoring
                    # print(f"Info: Symbol {symbol} found in config data but not in the current monitoring list for this instance.")
                    continue
                
                print(f"Applying configuration for actively monitored symbol: {symbol}")
                # Process price level alerts
                if 'price_levels' in alerts_config_for_symbol:
                    for level in alerts_config_for_symbol['price_levels']:
                        if 'price' in level and 'condition' in level:
                            self.add_alert(symbol, float(level['price']), level['condition'])
                
                # Process percentage change alerts
                if 'percentage_changes' in alerts_config_for_symbol:
                    for change in alerts_config_for_symbol['percentage_changes']:
                        if 'percentage' in change:
                            timeframe = change.get('timeframe', 5)
                            self.add_percentage_change_alert(symbol, float(change['percentage']), timeframe)
                
                # Process volatility alerts
                if 'volatility' in alerts_config_for_symbol:
                    for vol in alerts_config_for_symbol['volatility']:
                        if 'threshold' in vol:
                            timeframe = vol.get('timeframe', 5)
                            self.add_volatility_alert(symbol, float(vol['threshold']), timeframe)
            
            print(f"Applied alert configurations for monitored symbols from provided data.")
            
        except Exception as e:
            print(f"Error applying config data: {e}")
            # Not raising here, as main() will continue if config load fails partially
            # Consider if this should halt operations or just log. For now, logs.

    def send_email_alert(self, message: str):
        """Send email alert"""
        if not all([self.smtp_username, self.smtp_password, self.alert_email]):
            print("Email configuration not complete. Skipping email alert.")
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
            print("Alert email sent successfully!")
        except Exception as e:
            print(f"Failed to send email alert: {e}")

    def send_test_alert(self):
        """Send a test email to verify credentials"""
        test_message = f"Test Alert\\n\\nThis is a test message to verify your email configuration is working correctly.\\n\\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        print("Sending test email...")
        self.send_email_alert(test_message)

    def update_price_history(self, symbol: str, price: float):
        """Update price history for a symbol"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > self.history_length:
            self.price_history[symbol].pop(0)

    def check_percentage_change(self, symbol: str, current_price: float) -> Optional[str]:
        """Check for significant percentage changes"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 2:
            return None
        if symbol not in self.alerts: return None

        old_price = self.price_history[symbol][0]
        pct_change = ((current_price - old_price) / old_price) * 100

        for alert_key, alert_data in self.alerts[symbol].items():
            if isinstance(alert_data, dict) and alert_data.get('type') == 'percentage_change' and not alert_data.get('triggered'):
                if abs(pct_change) >= alert_data['percentage']:
                    alert_data['triggered'] = True # Mark as triggered
                    return f"{symbol} has changed by {pct_change:.2f}% in the last {alert_data['timeframe']} minutes (Current price: ${current_price:.2f})"
        return None

    def check_volatility(self, symbol: str, current_price: float) -> Optional[str]:
        """Check for high volatility"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 2:
            return None
        if symbol not in self.alerts: return None

        prices = self.price_history[symbol]
        price_changes = [abs((prices[i] - prices[i-1])/prices[i-1] * 100) for i in range(1, len(prices))]
        avg_volatility = sum(price_changes) / len(price_changes) if price_changes else 0

        for alert_key, alert_data in self.alerts[symbol].items():
            if isinstance(alert_data, dict) and alert_data.get('type') == 'volatility' and not alert_data.get('triggered'):
                if avg_volatility >= alert_data['threshold']:
                    alert_data['triggered'] = True # Mark as triggered
                    return f"{symbol} showing high volatility: {avg_volatility:.2f}% (Current price: ${current_price:.2f})"
        return None

    def check_alerts(self, symbol: str, current_price: float):
        """Check if any price alerts have been triggered"""
        if symbol not in self.alerts:
            return

        alerts_to_remove = []
        
        for alert_key, condition_or_data in self.alerts[symbol].items():
            if isinstance(condition_or_data, str):  # Basic price level alert
                price_level = float(alert_key) # Key is the price level for basic alerts
                condition = condition_or_data
                triggered = False
                message = ""
                if condition == 'above' and current_price > price_level:
                    message = f"{symbol} is now above {price_level} (Current price: ${current_price:.2f})"
                    triggered = True
                elif condition == 'below' and current_price < price_level:
                    message = f"{symbol} is now below {price_level} (Current price: ${current_price:.2f})"
                    triggered = True
                
                if triggered:
                    self.send_email_alert(message)
                    alerts_to_remove.append(alert_key)

        for key_to_remove in alerts_to_remove:
            del self.alerts[symbol][key_to_remove]

        # Check smart alerts (which manage their own 'triggered' state and are not removed this way)
        pct_change_alert_msg = self.check_percentage_change(symbol, current_price)
        if pct_change_alert_msg:
            self.send_email_alert(pct_change_alert_msg)

        volatility_alert_msg = self.check_volatility(symbol, current_price)
        if volatility_alert_msg:
            self.send_email_alert(volatility_alert_msg)

    def run(self):
        """Main loop to fetch prices and check alerts"""
        print(f"Starting price monitoring for {', '.join(self.symbols)}")
        print("Press Ctrl+C to stop")
        
        while True:
            try:
                for symbol in self.symbols:
                    ticker = self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{timestamp}] {symbol}: ${current_price:.2f}")
                    
                    self.update_price_history(symbol, current_price)
                    self.check_alerts(symbol, current_price)
                
                time.sleep(self.interval)
                
            except Exception as e:
                print(f"Error: {e}")
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
                {'percentage': 5, 'timeframe': 10}
            ],
            'volatility': [
                {'threshold': 2, 'timeframe': 5}
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
        }
    }
    
    config_path = Path('scripts/alerts_config.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(example_config, f, default_flow_style=False)
    print(f"Created example configuration file at {config_path}")

def main():
    parser = argparse.ArgumentParser(description='Crypto Price Alert Monitor')
    parser.add_argument('--symbols', nargs='+', default=None, help='Trading pair symbols. If --config is used, these symbols override those in config or filter them.')
    parser.add_argument('--interval', type=int, default=5, help='Check interval in minutes (default: 5)')
    parser.add_argument('--config', type=str, help='Path to YAML configuration file')
    parser.add_argument('--create-config', action='store_true', help='Create an example configuration file')
    parser.add_argument('--alert-above', type=float, help='Alert when price goes above this level (legacy CLI mode)')
    parser.add_argument('--alert-below', type=float, help='Alert when price goes below this level (legacy CLI mode)')
    parser.add_argument('--pct-change', type=float, help='Alert on percentage change (legacy CLI mode)')
    parser.add_argument('--volatility', type=float, help='Alert on high volatility (percentage) (legacy CLI mode)')
    parser.add_argument('--timeframe', type=int, default=5, help='Timeframe in minutes for smart alerts (legacy CLI mode)')
    parser.add_argument('--test-email', action='store_true', help='Send a test email to verify credentials')
    
    args = parser.parse_args()
    
    if args.create_config:
        create_example_config()
        return

    symbols_to_monitor = []
    loaded_config_data = None

    if args.config:
        try:
            with open(args.config, 'r') as f:
                loaded_config_data = yaml.safe_load(f)
            if not isinstance(loaded_config_data, dict):
                print(f"Error: Config file {args.config} is not a valid YAML dictionary. Exiting.")
                return
            
            config_file_symbols = list(loaded_config_data.keys())

            if args.symbols:  # --symbols explicitly provided, use them as the primary list
                symbols_to_monitor = args.symbols
                # Optionally, warn if a CLI symbol isn't in the config, but still monitor it
                # And apply config only to those CLI symbols that ARE in the config.
                # For simplicity here, we'll let load_config_data handle filtering.
                print(f"Using symbols from command line: {', '.join(symbols_to_monitor)}")
                print(f"Will apply configurations from '{args.config}' only for these symbols if they exist in the file.")
            else:  # --symbols NOT provided, so use all symbols from the config file
                symbols_to_monitor = config_file_symbols
                print(f"No --symbols specified, using all symbols from config file '{args.config}': {', '.join(symbols_to_monitor)}")
        
        except FileNotFoundError:
            print(f"Error: Config file '{args.config}' not found. Exiting.")
            return
        except Exception as e:
            print(f"Error reading or parsing config file {args.config}: {e}. Exiting.")
            return
    elif args.symbols:  # No config file, but --symbols provided
        symbols_to_monitor = args.symbols
        print(f"No config file specified. Monitoring symbols from command line: {', '.join(symbols_to_monitor)}")
    else:  # No config and no --symbols CLI argument
        symbols_to_monitor = ['BTC/USD'] # Fallback default
        print("Warning: No config file or --symbols specified. Defaulting to BTC/USD. Use CLI arguments for alerts.")

    if not symbols_to_monitor:
        print("Error: No symbols to monitor. Please specify symbols via --symbols or a config file. Exiting.")
        return
    
    monitor = PriceAlert(symbols_to_monitor, args.interval)
    
    if args.test_email:
        monitor.send_test_alert()
        return
    
    if loaded_config_data: # If config was successfully loaded
        monitor.load_config_data(loaded_config_data)
    else: # No config file used, or it failed to load, rely on CLI args for alerts
        if not args.config: # Only print this if no config was attempted
             print("Using legacy CLI arguments for alerts.")
        if args.alert_above:
            for symbol in symbols_to_monitor: # Apply to all monitored symbols
                monitor.add_alert(symbol, args.alert_above, 'above')
        if args.alert_below:
            for symbol in symbols_to_monitor:
                monitor.add_alert(symbol, args.alert_below, 'below')
        if args.pct_change:
            for symbol in symbols_to_monitor:
                monitor.add_percentage_change_alert(symbol, args.pct_change, args.timeframe)
        if args.volatility:
            for symbol in symbols_to_monitor:
                monitor.add_volatility_alert(symbol, args.volatility, args.timeframe)
    
    monitor.run()

if __name__ == "__main__":
    main() 