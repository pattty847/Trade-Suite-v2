import asyncio
import logging
from math import cos, sin
import dearpygui.dearpygui as dpg
from src.data.data_source import Data
from src.gui import tags

from src.gui.signals import SignalEmitter, Signals

class Chart:
    def __init__(self, emitter: SignalEmitter, data: Data, exchange: str) -> None:
        self.emitter = emitter
        self.data = data
        self.uuid = dpg.generate_uuid()
        self.exchange = exchange
        self.emitter.register(Signals.NEW_TRADE_DATA, self.on_new_trade)
        
        with dpg.window(
            label=f'{self.exchange.capitalize()}', 
            tag=self.uuid, 
            width=500, 
            height=500):
            pass
            # with dpg.menu_bar():
            #     with dpg.menu(label="Symbols"):
            #         # To add callback to create new child window object for chart.
            #         try:
            #             dpg.add_listbox(
            #                 items=self.data.exchange_list[exchange]['symbols'],
            #                 callback=lambda sender, app_data: self.emitter.emit(Signals.CREATE_CHART_FOR_SYMBOL, app_data)
            #             )
            #         except Exception as e:
            #             logging.warning(e)
                        
    def on_new_trade(self, trade):
        print(trade)