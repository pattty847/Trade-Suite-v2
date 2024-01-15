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
    exchanges = ["coinbasepro", "kucoin"]
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, exchanges)
    config_manager = ConfigManager()

    # EZ START LETS GO
    with Viewport(data=data, config_manager=config_manager) as viewport:
        pass
