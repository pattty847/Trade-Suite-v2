import asyncio
import logging
import dearpygui.dearpygui as dpg

from src.data.data_source import Data
from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter
from testing.quick_setup import ThreadedViewport


exchanges = ["coinbasepro"]
emitter = SignalEmitter()
influx = InfluxDB()
loop = asyncio.get_event_loop()
data = Data(influx, emitter, exchanges)

if __name__ == "__main__":
    program = ThreadedViewport(loop=loop, data=data)  
    program.start()