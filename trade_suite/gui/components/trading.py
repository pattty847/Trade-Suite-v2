import datetime
import json

import dearpygui.dearpygui as dpg
import pandas as pd

from trade_suite.config import ConfigManager
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.utils import timeframe_to_seconds


class Trading:
    def __init__(self, emitter: SignalEmitter, data: Data, config: ConfigManager, task_manager: TaskManager) -> None:
        
        self.emitter = emitter
        self.data = data
        self.config_manager = config
        self.task_manager = task_manager
        
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        
        self.in_trade_mode = False
        self.trade_mode_drag_line_tag = False
        self.candlestick_plot = None # tag to candle stick plot

        self.order_table_id = None  # Keep track of the order table ID
        
        self.register_event_listeners()
        
    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles,
            Signals.TIMEFRAME_CHANGED: self.on_timeframe_change,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)
            
    
    def setup_trading_menu(self):
        with dpg.menu(label="Trading"):
            dpg.add_checkbox(label="Order Line", callback=self.toggle_drag_line)
            dpg.add_menu_item(label="Trade", callback=self.toggle_place_order)

            # Adding a tooltip to the menu to give users more information
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Use these options to manage trading on the chart.\n"
                            "'Order Line' will show or hide a line at which you can place your trade.\n"
                            "'Trade' will open the trade window at the line's price.")
           
            
    def on_timeframe_change(self, new_timeframe: str):
        timeframe_in_minutes = timeframe_to_seconds(new_timeframe)
        self.timeframe_str = new_timeframe
        self.timeframe_seconds = timeframe_in_minutes
            
            
    def on_new_candles(self, exchange, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
        
        
    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']
        
        # update x
        # update y
        # etc...

        
    def toggle_drag_line(self):
        self.in_trade_mode = not self.in_trade_mode
        if self.in_trade_mode: 
            dpg.configure_item(self.trade_mode_drag_line_tag, show=True, default_value=self.ohlcv['closes'].tolist()[-1])
        else: 
            dpg.configure_item(self.trade_mode_drag_line_tag, show=False)
    
    
    def toggle_place_order(self):
        price = dpg.get_value(self.trade_mode_drag_line_tag)
        
        def apply_percentage(profit_pct):
            percentage = dpg.get_value(profit_pct) / 100
            take_profit_price = price * (1 + percentage)
            dpg.set_value(profit_pct, take_profit_price)

        if not dpg.does_item_exist("order_window"):
            # Create the window once
            width, height = 400, 200
            with dpg.window(
                label="Place Order", 
                modal=True, 
                tag="order_window",
                width=width, height=height,
                pos=(dpg.get_viewport_width() / 2 - width/2, dpg.get_viewport_height() / 2 - height/2), 
                show=False):
                account = dpg.add_button(label="Account", callback=lambda: print(self.task_manager.run_task_until_complete(self.data.exchange_list['coinbasepro']['ccxt'].fetch_balance())))
                price_ = dpg.add_input_float(label="Price", default_value=price)
                stop = dpg.add_input_float(label="Stop Loss")
                profit_pct = dpg.add_input_float(label="Take Profit")
                size = dpg.add_input_int(label="Size")

                # Quick buttons for setting take profit percentage
                with dpg.group(horizontal=True):
                    for percent in [2, 3, 5]:
                        dpg.add_button(label=f"{percent}%", callback=lambda: apply_percentage(profit_pct), user_data=percent)

                order = (price_, stop, profit_pct, size)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Long", callback=self.place_order, user_data=(order, "Long"))
                    dpg.add_button(label="Short", callback=self.place_order, user_data=(order, "Short"))

        # Show or hide the window
        if dpg.is_item_shown("order_window"):
            dpg.hide_item("order_window")
        else:
            dpg.show_item("order_window")
            
    
    def place_order(self, sender, app_data, user_data):
        price, stop, profit_pct, size = [dpg.get_value(item) for item in user_data[0]]
        side = user_data[1]
        
        print(price, stop, profit_pct, size, side)
        # Set the color based on the value of 'side'
        if side == "Short":
            color = (255, 0, 0, 255)  # Red color for 'Short'
        elif side == "Long":
            color = (0, 255, 0, 255)  # Green color for 'Long'
        else:
            color = (255, 255, 255, 255)  # Default to white if side is neither

        # Add a drag line with the specified color
        dpg.add_drag_line(label=f"{side}|{price}", default_value=price, vertical=False, parent=self.candlestick_plot, color=color)

    def setup_orders(self):
        orders = self.task_manager.run_task_until_complete(self.data.exchange_list['coinbasepro']['ccxt'].fetch_orders())
        
        with dpg.window(label="Order Book", width=800, height=300):
            # Create the table and store its ID for later use
            with dpg.table(header_row=True, resizable=True) as self.order_table_id:
                dpg.add_table_column(label="Time Placed")
                dpg.add_table_column(label="Symbol")
                dpg.add_table_column(label="Type")
                dpg.add_table_column(label="Side")
                dpg.add_table_column(label="Price")
                dpg.add_table_column(label="Amount")
                dpg.add_table_column(label="% Filled")
                dpg.add_table_column(label="Total")
                dpg.add_table_column(label="Status")
                
        self.create_order_table(orders)


    def add_order_to_table(self, order):
        # Calculate % filled
        percent_filled = (order['filled'] / order['amount']) * 100 if order['amount'] else 0

        # Format price and cost
        formatted_price = f"${order['price']:.2f}" if order['price'] else "N/A"
        formatted_cost = f"${order['cost']:.2f}" if order['cost'] else "N/A"

        with dpg.table_row(parent=self.order_table_id):
            dpg.add_text(order.get('datetime', 'N/A'))
            dpg.add_text(order.get('symbol', 'N/A'))
            dpg.add_text(order.get('type', 'N/A'))
            dpg.add_text(order.get('side', 'N/A'))
            dpg.add_text(formatted_price)
            dpg.add_text(f"{order['amount']:.8f}")
            dpg.add_text(f"{percent_filled:.2f}%")
            dpg.add_text(formatted_cost)
            dpg.add_text(order.get('status', 'N/A'))


    def create_order_table(self, orders):
        # Clear any existing rows in the table
        # dpg.delete_item(self.order_table_id, children_only=True)

        # Add new orders to the table, filter for 'closed' status
        for order in orders:  # Limit to first 100 orders for performance
            if order.get('status') == 'closed':
                self.add_order_to_table(order)
