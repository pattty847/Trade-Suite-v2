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
import dotenv

from config import ConfigManager
from data.data_source import Data
from data.influx import InfluxDB
from gui.signals import SignalEmitter
from gui.viewport import Viewport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(filename)s:%(funcName)s: %(message)s",
)

dotenv.load_dotenv()
logging.info(f"Environment variables loaded and logging setup.")

def _get_args():
    # Setup program dependencies
    # Create argparser to start the program from the command line
    parser = argparse.ArgumentParser(description="Your program description here")

    # Add an argument for the list of exchanges
    parser.add_argument(
        "--exchanges",
        nargs="+",
        default=["coinbasepro"],
        help="List of exchanges to use",
    )

    return parser.parse_args()

if __name__ == "__main__":
    args = _get_args()

    config_manager = ConfigManager()
    exchanges = (
        config_manager.get_setting("last_exchange") or args.exchanges
    )  # add exchange list to initialize premptively
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, [exchanges])

    # EZ START LET'S GO
    with Viewport(data=data, config_manager=config_manager) as viewport:
        viewport.start_program()
