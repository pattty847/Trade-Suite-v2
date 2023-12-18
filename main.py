import asyncio
import logging

import dotenv
from src.data.data_source import Data
from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter
from src.gui.viewport import Viewport

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

influx = InfluxDB()
exchanges = ["coinbasepro"]
emitter = SignalEmitter()

async def main():
    async with Data(influx, emitter, exchanges=exchanges) as data:
        with Viewport(emitter, data) as viewport:
            viewport.run()

if __name__ == "__main__":
    asyncio.run(main())