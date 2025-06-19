import sys
import os

# Add the project root (Trade-Suite-v2) to sys.path
# This allows imports like `from sentinel...` and `from trade_suite...` to work correctly
# when the script is run as `python sentinel/alert_bot/main.py` from the project root.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

#!/usr/bin/env python3
import argparse
import logging
# import time # No longer directly used
import os
import sys
import asyncio
from pathlib import Path
from typing import Optional
# from typing import Any, Optional, Dict, Set, List # No longer directly used here

# Updated imports for AlertDataManager and trade_suite components
from sentinel.alert_bot.config.loader import load_alerts_from_yaml, create_example_global_config_file # Changed from load_config
from sentinel.alert_bot.manager import AlertDataManager
from sentinel.alert_bot.notifier.async_email_notifier import AsyncEmailNotifier # Keep for --test-email
# from sentinel.alert_bot.notifier.async_console_notifier import AsyncConsoleNotifier # Not directly used in main after refactor
from sentinel.alert_bot.metrics import start_metrics_server

# Trade Suite components
from trade_suite.core.facade import CoreServicesFacade

# Setup logging
logger = logging.getLogger(__name__) # Changed from "price_alert" to module name for consistency

def setup_logging(log_level: str = "INFO") -> None:
    """
    Set up logging configuration
    
    Args:
        log_level: Logging level (INFO, DEBUG, etc.)
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file_path = log_dir / 'sentinel_alert_bot.log' # More specific log file name
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler()
        ]
    )
    logger.info(f"Logging setup complete. Log level: {log_level.upper()}. File: {log_file_path}")

# Removed the old AlertBot class entirely

async def async_main():
    """Async entry point for Sentinel Alert Bot using the CoreServicesFacade."""
    parser = argparse.ArgumentParser(description='Sentinel Alert Bot')
    parser.add_argument('--config', type=str, default='sentinel/alert_bot/config/alerts_config.yaml', 
                      help='Path to YAML configuration file for AlertDataManager')
    # Removed --interval and --cvd-lookback as AlertDataManager derives needs from its config
    parser.add_argument('--log-level', type=str, default='INFO', 
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Logging level')
    parser.add_argument('--test-email', action='store_true', 
                      help='Send a test email using settings from config and exit')
    parser.add_argument('--exchange', type=str, default='coinbase', # Could be a list for Data source
                      help='Default CCXT exchange ID to use if not specified in alerts_config.yaml or for general setup. Can be multiple comma-separated.')
    parser.add_argument('--create-config', action='store_true',
                      help='Create an example GlobalAlertConfig YAML file and exit')
    parser.add_argument('--metrics-port', type=int, default=9090,
                      help='Port for Prometheus metrics HTTP server (default: 9090)')
    parser.add_argument('--disable-metrics', action='store_true',
                      help='Disable Prometheus metrics collection')
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    if args.create_config:
        try:
            from sentinel.alert_bot.config.loader import create_example_global_config_file
            # Determine the path relative to the main.py script's location or project root
            # Assuming main.py is in sentinel/alert_bot/
            output_dir = Path(__file__).parent / "config"
            output_dir.mkdir(parents=True, exist_ok=True) # Ensure config directory exists
            example_config_file_path = output_dir / "example_global_alerts_config.yaml"
            
            logger.info(f"Attempting to generate example global configuration file at: {example_config_file_path}")
            create_example_global_config_file(example_config_file_path)
            logger.info(f"Example configuration file created. Please review it and copy/rename to your desired alerts_config.yaml path (default: {args.config}) and customize it.")
        except Exception as e:
            logger.exception(f"Could not create example configuration: {e}")
        return
    
    core: Optional[CoreServicesFacade] = None
    alert_manager: Optional[AlertDataManager] = None

    try:
        if not args.disable_metrics:
            await start_metrics_server(args.metrics_port)
            logger.info(f"Metrics server started on port {args.metrics_port}")

        # Load the global configuration for the alert bot
        # This is used by AlertDataManager and potentially for --test-email
        global_alerts_config = load_alerts_from_yaml(args.config)

        if args.test_email:
            logger.info("Sending test email...")
            # Find email notifier config from global_alerts_config
            email_conf = None
            if global_alerts_config.notification_settings:
                for nc in global_alerts_config.notification_settings.notifiers:
                    if nc.type == 'email' and nc.enabled:
                        email_conf = nc.config
                        break
            
            if email_conf:
                email_notifier = AsyncEmailNotifier(config=email_conf) # Pass specific config
                await email_notifier.start()
                await email_notifier.send_test_notification() 
                await asyncio.sleep(2) # Brief pause for email sending
                await email_notifier.stop()
                logger.info("Test email process complete.")
            else:
                logger.warning("No enabled email notifier configuration found in alerts_config.yaml to send a test email.")
            return

        # Initialize Trade Suite core components
        logger.info("Initializing Core Services via Facade...")
        core = CoreServicesFacade(force_public=True)
        
        exchanges_to_use = [e.strip() for e in args.exchange.split(',') if e.strip()]
        if not exchanges_to_use:
            logger.error("No exchanges specified. Please use the --exchange argument.")
            return
            
        await core.start(exchanges=exchanges_to_use)
        
        logger.info("Initializing AlertDataManager...")
        alert_manager = AlertDataManager(
            core_services=core,
            config_file_path=args.config
        )
        
        await alert_manager.start_monitoring()
        logger.info("AlertDataManager started. Sentinel Alert Bot is running.")
        logger.info("Press Ctrl+C to stop.")
        
        while True:
            await asyncio.sleep(3600)
            
    except FileNotFoundError as e:
        logger.error(f"Configuration file error: {e}.")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error in Sentinel Alert Bot: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if alert_manager:
            logger.info("Stopping AlertDataManager...")
            await alert_manager.stop_monitoring()
            logger.info("AlertDataManager stopped.")
        
        if core:
            logger.info("Cleaning up Core Services...")
            core.cleanup()
            logger.info("Core Services cleanup complete.")

        logger.info("Sentinel Alert Bot shutdown complete.")

def main():
    """Entry point that runs the async loop"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(async_main())

if __name__ == "__main__":
    # Add project root to sys.path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    main()
