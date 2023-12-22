import __init__
import asyncio

from src.data.data_source import Data
from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter
from src.gui.viewport import Viewport

if __name__ == "__main__":
    
    exchanges = ["coinbasepro"]
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, exchanges)
    loop = asyncio.get_event_loop()
    
    with Viewport(loop=loop, data=data, emitter=emitter) as viewport:
        pass