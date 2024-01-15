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
    # TODO: Create argparser to start program from cmd line
    
    config_manager = ConfigManager()
    # TODO: Initialize exchange after MeuBar clicks or only saved exchanges in config file
    exchanges = config_manager.get_setting('last_exchange') or ['']
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, [exchanges])

    # EZ START LETS GO
    with Viewport(data=data, config_manager=config_manager) as viewport:
        pass
