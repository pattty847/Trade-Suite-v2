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
    - trade_suite.config.ConfigManager: Manages configuration settings.
    - trade_suite.data.data_source.Data: Provides data from various sources.
    - trade_suite.data.influx.InfluxDB: Handles data storage in InfluxDB.
    - trade_suite.gui.signals.SignalEmitter: Emits trading signals.
    - trade_suite.gui.viewport.Viewport: GUI interface for the trading program.

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

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.data.influx import InfluxDB
from trade_suite.gui.signals import SignalEmitter
from trade_suite.gui.viewport import Viewport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(filename)s:%(funcName)s: %(message)s",
)
dotenv.load_dotenv()
logging.info(f"Environment variables loaded and logging setup.")

if __name__ == "__main__":
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

    args = parser.parse_args()

    config_manager = ConfigManager()
    exchanges = (
        config_manager.get_setting("last_exchange") or args.exchanges
    )  # add exchange list to initialize premptively
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, [exchanges])

    # EZ START LET'S GO
    with Viewport(data=data, config_manager=config_manager) as viewport:
        pass
