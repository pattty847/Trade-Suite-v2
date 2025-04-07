"""
This script is used to run a trading program with user-defined settings.

Usage:
    python script.py [--exchanges EXCHANGE1 EXCHANGE2 ...]

Parameters:
    --exchanges: A list of exchanges to use in the trading program. By default, it uses 'coinbasepro'.
                 You can provide multiple exchanges by separating them with spaces.

Example:
    python script.py --exchanges coinbasepro binance kraken

Dependencies:
    - argparse: Used for parsing command-line arguments.
    - logging: Used for configuring logging settings.
    - dotenv: Used for loading environment variables from a .env file.
    - config.ConfigManager: Manages configuration settings.
    - data.data_source.Data: Provides data from various sources.
    - data.influx.InfluxDB: Handles data storage in InfluxDB.
    - gui.signals.SignalEmitter: Emits trading signals.
    - gui.viewport.Viewport: GUI interface for the trading program.

Instructions:
    1. Make sure to set up the required environment variables in a .env file.
    2. Run the script with optional command-line arguments to specify exchanges to use.
    3. The script initializes the trading program with the specified settings and starts the trading viewport.

Note:
    - This script requires a proper configuration setup and access to the specified exchanges.
    - Make sure to customize the description in the argparse.ArgumentParser according to your program's needs.
"""

import argparse
import logging
from dotenv import load_dotenv
import asyncio
import sys
import os
from datetime import datetime

from config import ConfigManager
from data.data_source import Data
from data.influx import InfluxDB
from gui.signals import SignalEmitter
from gui.viewport import Viewport

load_dotenv(override=True)

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
    # Setup program dependencies
    # Create argparser to start the program from the command line
    parser = argparse.ArgumentParser(description="Your program description here")

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

    return parser.parse_args()


if __name__ == "__main__":
    args = _get_args()
    
    # Set the logging level based on command line argument
    numeric_level = getattr(logging, args.level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {args.level}")
    
    # Setup logging
    _setup_logging(numeric_level)
    
    logging.info(f"Environment variables loaded and logging setup.")

    config_manager = ConfigManager()
    exchanges = (
        config_manager.get_setting("default_exchange") or args.exchanges
    )  # add exchange list to initialize premptively
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, [exchanges])

    # EZ START LET'S GO
    with Viewport(data=data, config_manager=config_manager) as viewport:
        viewport.start_program()
