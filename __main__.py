import __init__

from src.data.data_source import Data
from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter
from src.gui.viewport import Viewport

if __name__ == "__main__":
    
    # Setup program dependencies
    exchanges = ["coinbasepro"]
    emitter = SignalEmitter()
    influx = InfluxDB()
    data = Data(influx, emitter, exchanges)
    
    # EZ START LETS GO
    with Viewport(data=data, emitter=emitter) as viewport:
        print('bai')