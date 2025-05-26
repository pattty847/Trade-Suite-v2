#!/usr/bin/env python3
import argparse
import logging
import time
import os
import sys
import asyncio
from pathlib import Path
from typing import Any, Optional, Dict, Set, List

from sentinel.alert_bot.config.loader import load_config
from sentinel.alert_bot.fetcher.trade_streamer import TradeStreamer
from sentinel.alert_bot.rules.engine import RuleEngine
from sentinel.alert_bot.fetcher.ticker import TickerStreamer
from sentinel.alert_bot.fetcher.ohlcv import OHLCVStreamer
from sentinel.alert_bot.notifier.async_email_notifier import AsyncEmailNotifier
from sentinel.alert_bot.notifier.async_console_notifier import AsyncConsoleNotifier
from sentinel.alert_bot.metrics import start_metrics_server

# Setup logging
logger = logging.getLogger("price_alert")

def setup_logging(log_level: str = "INFO") -> None:
    """
    Set up logging configuration
    
    Args:
        log_level: Logging level (INFO, DEBUG, etc.)
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Ensure logs directory exists
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file_path = log_dir / 'alert_logs.log'
    
    # Configure logging
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler()
        ]
    )

class AlertBot:
    """Main alert bot class that coordinates components"""
    
    def __init__(self, config_path: str, exchange_id: str = 'coinbase', ticker_interval: int = 10, cvd_lookback_minutes: int = 120):
        """
        Initialize the alert bot
        
        Args:
            config_path: Path to YAML config file
            exchange_id: CCXT exchange ID to use
            ticker_interval: Seconds between ticker updates
            cvd_lookback_minutes: Minutes of trade history for CVD calculation
        """
        self.config_path = config_path
        self.exchange_id = exchange_id
        self.ticker_interval = ticker_interval
        
        # Initialize components
        self.config = load_config(config_path)
        self.rule_engine = RuleEngine(self.config)
        
        # Streamers
        self.ticker_streamer = TickerStreamer(exchange_id=exchange_id, update_interval=ticker_interval)
        self.ohlcv_streamer = OHLCVStreamer(exchange_id=exchange_id)
        self.trade_streamer = TradeStreamer(exchange_id=exchange_id, lookback_minutes=cvd_lookback_minutes)
        
        # Notifiers (now using async versions)
        self.console_notifier = AsyncConsoleNotifier()
        self.email_notifier = AsyncEmailNotifier(use_env_vars=True)
        
        # Collected required timeframes for each symbol
        self.required_timeframes: Dict[str, Set[int]] = {}
        
        # Track symbols needing CVD data
        self.cvd_symbols: Set[str] = set()
        
        # Set up callbacks
        self.setup_callbacks()
    
    def setup_callbacks(self):
        """Set up callbacks for price, OHLCV, and CVD data"""
        
        # When new price data arrives, evaluate rules
        self.ticker_streamer.register_callback(self.on_new_price)
        
        # When new OHLCV data arrives, update cache
        self.ohlcv_streamer.register_callback(self.on_new_ohlcv)
        
        # When CVD data updates, we don't trigger evaluations directly
        # CVD is evaluated during price updates
        self.trade_streamer.register_callback(self.on_new_cvd_data)
    
    def on_new_price(self, symbol: str, price: float):
        """
        Callback for new price data
        
        Args:
            symbol: Trading symbol
            price: Current price
        """
        try:
            # Get any additional data for this symbol
            extra_data = {}
            
            # If we have OHLCV data for this symbol, include it
            if symbol in self.required_timeframes and self.required_timeframes[symbol]:
                ohlcv_data = {}
                for timeframe in self.required_timeframes[symbol]:
                    candles = self.ohlcv_streamer.get_latest_data(symbol, timeframe)
                    if candles:
                        ohlcv_data[timeframe] = candles
                
                if ohlcv_data:
                    extra_data['ohlcv_data'] = ohlcv_data
            
            # If we have CVD data for this symbol, include it
            if symbol in self.cvd_symbols:
                cvd_data = self.trade_streamer.get_cvd_data(symbol)
                if cvd_data:
                    extra_data['cvd_data'] = cvd_data
            
            # Evaluate rules for this symbol with the new price
            alert_messages = self.rule_engine.evaluate_symbol(symbol, price, extra_data)
            
            # Send notifications if there are any alerts
            if alert_messages:
                combined_message = "\n\n".join(alert_messages)
                asyncio.create_task(self.console_notifier.queue_notification(combined_message))
                asyncio.create_task(self.email_notifier.queue_notification(combined_message))
        
        except Exception as e:
            logger.error(f"Error processing new price for {symbol}: {e}")
    
    def on_new_cvd_data(self, symbol: str, cvd_value: float, extra_data: Dict[str, Any]):
        """
        Callback for new CVD data - just log it for debugging
        
        Args:
            symbol: Trading symbol
            cvd_value: Current CVD value
            extra_data: Additional CVD metrics
        """
        logger.debug(f"CVD updated for {symbol}: {cvd_value:.2f}")
        # Note: We don't trigger rule evaluation here - that happens on price updates
        # This ensures all data (price, OHLCV, CVD) is available together
    
    async def initialize(self):
        """Initialize all components"""
        # Collect required timeframes and CVD symbols
        for symbol_key in self.rule_engine.get_symbols():
            self.required_timeframes[symbol_key] = set()
            
            # Analyze rules to determine required timeframes and features
            for rule in self.rule_engine.get_rules_for_symbol(symbol_key):
                if hasattr(rule, 'timeframe_minutes') and isinstance(getattr(rule, 'timeframe_minutes'), int):
                    self.required_timeframes[symbol_key].add(rule.timeframe_minutes)
                
                # Check if this symbol needs CVD data
                if rule.rule_type == 'cvd':
                    self.cvd_symbols.add(symbol_key)
        
        # Initialize streamers
        await self.ticker_streamer.initialize()
        await self.ohlcv_streamer.initialize()
        await self.trade_streamer.initialize()
        
        # Initialize notifiers
        await self.console_notifier.start()
        await self.email_notifier.start()
        
        # Set up what to track
        for symbol in self.rule_engine.get_symbols():
            # Track ticker for all symbols
            self.ticker_streamer.track_symbol(symbol)
            
            # Track OHLCV for symbols that need it
            if symbol in self.required_timeframes:
                for timeframe in self.required_timeframes[symbol]:
                    self.ohlcv_streamer.track_symbol_timeframe(symbol, timeframe)
            
            # Track trades for CVD calculation
            if symbol in self.cvd_symbols:
                self.trade_streamer.track_symbol(symbol)
        
        logger.info(f"CVD tracking enabled for {len(self.cvd_symbols)} symbols: {list(self.cvd_symbols)}")
    
    async def start(self):
        """Start all components"""
        # Start streamers
        await self.ticker_streamer.start()
        await self.ohlcv_streamer.start()
        await self.trade_streamer.start()
        
        logger.info(f"Started monitoring {len(self.rule_engine.get_symbols())} symbols")
        
        # Keep main task alive
        while True:
            await asyncio.sleep(60)
    
    async def stop(self):
        """Stop all components"""
        # Stop notifiers
        await self.email_notifier.stop()
        await self.console_notifier.stop()
        
        # Stop streamers
        await self.ticker_streamer.stop()
        await self.ohlcv_streamer.stop()
        await self.trade_streamer.stop()
        
        logger.info("Stopped monitoring")

async def async_main():
    """Async entry point for price alert bot"""
    parser = argparse.ArgumentParser(description='Crypto Price Alert Bot')
    parser.add_argument('--config', type=str, default='sentinel/alert_bot/alerts_config.yaml', 
                      help='Path to YAML configuration file')
    parser.add_argument('--interval', type=int, default=10, 
                      help='Ticker update interval in seconds (default: 10)')
    parser.add_argument('--cvd-lookback', type=int, default=120,
                      help='Lookback window in minutes for CVD calculation (default: 120)')
    parser.add_argument('--log-level', type=str, default='INFO', 
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Logging level')
    parser.add_argument('--test-email', action='store_true', 
                      help='Send a test email and exit')
    parser.add_argument('--exchange', type=str, default='coinbase',
                      help='CCXT exchange ID to use (default: coinbase)')
    parser.add_argument('--create-config', action='store_true',
                      help='Create an example configuration file and exit')
    parser.add_argument('--metrics-port', type=int, default=9090,
                      help='Port for Prometheus metrics HTTP server (default: 9090)')
    parser.add_argument('--disable-metrics', action='store_true',
                      help='Disable Prometheus metrics collection')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Create example config if requested
    if args.create_config:
        from sentinel.alert_bot.config.create_example_config import create_example_config
        config_path = create_example_config()
        logger.info(f"Created example configuration at {config_path}")
        return
    
    try:
        # Start metrics server if not disabled
        if not args.disable_metrics:
            metrics_server = await start_metrics_server(args.metrics_port)
        
        # Test email if requested
        if args.test_email:
            logger.info("Sending test email...")
            email_notifier = AsyncEmailNotifier(use_env_vars=True)
            await email_notifier.start()
            await email_notifier.send_test_notification()
            # Wait a bit for email to be sent
            await asyncio.sleep(5)
            await email_notifier.stop()
            return
        
        # Create and initialize alert bot
        bot = AlertBot(
            config_path=args.config,
            exchange_id=args.exchange,
            ticker_interval=args.interval,
            cvd_lookback_minutes=args.cvd_lookback
        )
        
        # Initialize
        logger.info("Initializing alert bot...")
        await bot.initialize()
        
        # Run
        logger.info(f"Starting price monitoring with {args.interval}s update interval")
        logger.info("Press Ctrl+C to stop")
        
        try:
            await bot.start()
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user (Ctrl+C).")
        finally:
            await bot.stop()
            
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

def main():
    """Entry point that runs the async loop"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
