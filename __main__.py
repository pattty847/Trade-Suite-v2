import argparse
import logging

import dotenv

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.data.influx import InfluxDB
from trade_suite.gui.signals import SignalEmitter
from trade_suite.gui.viewport import Viewport

logging.basicConfig(level=logging.INFO)
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
    exchanges = config_manager.get_setting('last_exchange') or args.exchanges # add exchange list to initialize premptively
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, [exchanges])

    # EZ START LETS GO
    with Viewport(data=data, config_manager=config_manager) as viewport:
        pass
