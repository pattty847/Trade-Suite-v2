import asyncio
import os
import sys
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.data.influx import InfluxDB
from trade_suite.gui.signals import SignalEmitter
from trade_suite.gui.viewport import Viewport

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _setup_logging(level=logging.INFO):
    """Configure logging to both console and file with timestamps."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"logs/trade_suite_{timestamp}.log"
    
    # Create a formatter
    formatter = logging.Formatter("%(asctime)s %(levelname)s:%(filename)s:%(funcName)s: %(message)s")
    
    # Create handlers
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add the handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    logging.info(f"Logging initialized. Log file: {log_filename}")


def _get_args():
    # Create argparser to start the program from the command line
    parser = argparse.ArgumentParser(description="Trading Suite with Dockable Widgets")

    # Add an argument for the list of exchanges
    parser.add_argument(
        "--exchanges",
        nargs="+",
        default=["coinbase"],
        help="List of exchanges to use",
    )
    
    parser.add_argument(
        "--level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: %(default)s)",
    )
    
    parser.add_argument(
        "--reset-layout",
        action="store_true",
        help="Reset layout to factory default",
    )

    return parser.parse_args()


def main():
    """Main entry point for the application."""
    args = _get_args()
    
    # Set the logging level based on command line argument
    numeric_level = getattr(logging, args.level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {args.level}")
    
    # Setup logging
    _setup_logging(numeric_level)
    
    logging.info(f"Environment variables loaded and logging setup.")

    # Load environment variables from .env file
    load_dotenv(override=True)

    # Create configuration manager
    config_manager = ConfigManager()
    
    # Get default exchange from config or use command line arguments
    default_exchange = config_manager.get_setting("default_exchange")
    
    # Determine exchanges to use
    exchanges_to_use = []
    if default_exchange:
        # If default_exchange is a string, make it a single-item list
        if isinstance(default_exchange, str):
            exchanges_to_use = [default_exchange]
        # If it's already a list, use it directly
        elif isinstance(default_exchange, list):
            exchanges_to_use = default_exchange
    else:
        # Use the command line arguments
        exchanges_to_use = args.exchanges
    
    logging.info(f"Using exchanges: {exchanges_to_use}")
    
    # Create signal emitter
    emitter = SignalEmitter()
    
    # Create InfluxDB
    influx = InfluxDB()
    
    # Create data source with exchanges
    data = Data(influx, emitter, exchanges_to_use)
    
    # If --reset-layout flag is set, delete the user layout file
    if args.reset_layout:
        user_layout_file = "config/user_layout.ini"
        if os.path.exists(user_layout_file):
            logging.info(f"Removing user layout file: {user_layout_file}")
            os.remove(user_layout_file)
    
    # Ensure the config directory exists
    os.makedirs('config', exist_ok=True)
    
    # Create and run the viewport (main application window)
    with Viewport(data=data, config_manager=config_manager) as viewport:
        viewport.start_program()


if __name__ == "__main__":
    main()
