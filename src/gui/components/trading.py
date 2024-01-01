import datetime
import json
import dearpygui.dearpygui as dpg

from src.config import ConfigManager
from src.data.data_source import Data
from src.gui.signals import SignalEmitter
from src.gui.task_manager import TaskManager


class Orders:
    def __init__(self, emitter: SignalEmitter, data: Data, config: ConfigManager, task_manager: TaskManager) -> None:
        
        self.emitter = emitter
        self.data = data
        self.config_manager = config
        self.task_manager = task_manager

        self.order_table_id = None  # Keep track of the order table ID
        self.setup_orders()

    def setup_orders(self):
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
        
        orders = self.task_manager.run_task_until_complete(self.data.exchange_list['coinbasepro']['ccxt'].fetch_orders())
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
