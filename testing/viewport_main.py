"""

Testing streaming with the user interface.

# TODO: 
- Add threading capabilities for the streaming of tickers.

"""


import asyncio
import logging
import dotenv

from matplotlib import pyplot as plt
from src.data.data_source import Data
from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter
from src.gui.viewport import Viewport

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

influx = InfluxDB()
exchanges = ["coinbasepro"]


async def watch_tick_data(symbols, exchanges):
    async with Data(influx, exchanges=exchanges) as data:
        await data.stream_trades(symbols=symbols)


if __name__ == "__main__":
    emitter = SignalEmitter()
    with Viewport(emitter) as viewport:
        viewport.run()

    # try:
    #     asyncio.run(
    #         watch_tick_data(
    #             exchanges=exchanges,
    #             symbols=["BTC/USD", "ETH/USD", "SOL/USD"],
    #         )
    #     )
    # except KeyboardInterrupt:
    #     print("Program stopped by user.")
