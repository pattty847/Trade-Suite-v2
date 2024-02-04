import json
import logging
import dearpygui.dearpygui as dpg
import pandas as pd

from gui.signals import SignalEmitter, Signals
from data.data_source import Data

class TestOB:
    def __init__(self, tab, data: Data, emitter: SignalEmitter) -> None:
        self.tab = tab
        self.data = data
        self.emitter = emitter
        self.table_id = None
        
        self.order_book_state = {}  # Maps price levels to (amount, row index)
        self.row_widget_ids = {}  # Maps row indices to widget IDs
        self.price_to_row_index = {}  # Maps price levels to row indices
        
        self.tick_size = 100
        
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
    
    def launch(self):
        # Your main window setup
        with dpg.window(label="Order Book", width=250, height=775, pos=[25, 25]):
            # Add other controls and widgets as needed here
            dpg.add_slider_float(label="Tick Size", format='%.3f', default_value=self.tick_size, callback=self._on_tick_size_change)
            
            with dpg.table() as self.table_id:

                # Add columns for the order book
                dpg.add_table_column(label="Quantity", parent=self.table_id)  # Bid/Ask quantities
                dpg.add_table_column(label="Price", parent=self.table_id)     # Price levels
                

    # Callback function to update the table with new data
    def __on_order_book_update(self, tab, exchange, orderbook):

        if tab == self.tab:
            tick_size = self.tick_size # Adjust as needed

            # Aggregate the order book
            aggregated_order_book = self._aggregate_order_book(orderbook, tick_size)

            # Clear the existing table rows
            dpg.delete_item(self.table_id, children_only=True)

            # Update the table with new rows
            num_rows = 15  # Adjust the number of rows as desired

            # Highlight the best ask
            best_ask_price, best_ask_amount = aggregated_order_book['asks_agg'][0]
            # Highlight the best bid
            best_bid_price, best_bid_amount = aggregated_order_book['bids_agg'][0]

            # Add columns for the order book
            dpg.add_table_column(label="Quantity", parent=self.table_id)  # Bid/Ask quantities
            dpg.add_table_column(label="Price", parent=self.table_id)     # Price levels
            
            # Display asks
            for price, amount in reversed(aggregated_order_book['asks_agg'][0:num_rows]):
                with dpg.table_row(parent=self.table_id):
                    if price == best_ask_price:
                        # TODO: Format needs to be based on the symbols min tick size or smtg
                        dpg.add_text(format(amount, '.3f'), color=[255, 0, 0])  # Red color for best ask
                        dpg.add_text(format(price, '.3f'), color=[255, 0, 0])
                    else:
                        dpg.add_text(format(amount, '.3f'))
                        dpg.add_text(format(price, '.3f'))
            
            with dpg.table_row(parent=self.table_id):
                dpg.add_text("Spread")
                dpg.add_text(f"{orderbook['asks'][0][0] - orderbook['bids'][0][0]:.4f}")

            # Display bids
            for price, amount in aggregated_order_book['bids_agg'][0:num_rows]:
                with dpg.table_row(parent=self.table_id):
                    if price == best_bid_price:
                        dpg.add_text(format(amount, '.3f'), color=[0, 255, 0])  # Green color for best bid
                        dpg.add_text(format(price, '.3f'), color=[0, 255, 0])
                    else:
                        dpg.add_text(format(amount, '.3f'))
                        dpg.add_text(format(price, '.3f'))

    def _on_order_book_update(self, tab, exchange, orderbook):
        
        if tab != self.tab:
            return
        
        levels = 15

        # Aggregate the order book
        aggregated_order_book = self._aggregate_order_book(orderbook, self.tick_size)
        
        # Process the asks
        for i, (price, amount) in enumerate(reversed(aggregated_order_book['asks_agg'][0:levels])):
            self.update_or_create_row(i, price, amount, is_ask=True)
            
        spread =  orderbook['asks'][0][0] - orderbook['bids'][0][0]
        spread_row_index = len(aggregated_order_book['asks_agg'][0:levels])
        self.draw_spread_row(spread_row_index, spread)
            
        # Process the bids
        start_index_for_bids = len(aggregated_order_book['asks_agg'][0:levels]) + 1  # +1 for the spread row
        for j, (price, amount) in enumerate(aggregated_order_book['bids_agg'][0:levels]):
            row_index = start_index_for_bids + j
            self.update_or_create_row(row_index, price, amount, is_ask=False)

        # Remove any extra rows if the order book has shrunk
        self.remove_extra_rows(len(aggregated_order_book['asks_agg'][0:levels]) + len(aggregated_order_book['bids_agg'][0:levels]) + 1)
    
    
    def draw_spread_row(self, row_index, spread):
        # Check if there's already a spread row, update it, or create a new one
        if row_index in self.row_widget_ids:
            # Assuming the spread row only has one widget for displaying the spread
            spread_widget_id = self.row_widget_ids[row_index][0]
            dpg.set_value(spread_widget_id, f"Spread: {spread:.2f}")
        else:
            # Create a new row for the spread
            with dpg.table_row(parent=self.table_id) as row_id:
                # You might want to span this across multiple columns or have custom styling
                spread_widget_id = dpg.add_text(f"Spread: {spread:.2f}")
                self.row_widget_ids[row_index] = (spread_widget_id,)


    def update_or_create_row(self, row_index, price, amount, is_ask):
        # Check if the price level already exists and update
        if price in self.price_to_row_index:
            current_row_index = self.price_to_row_index[price]
            quantity_widget_id, price_widget_id = self.row_widget_ids[current_row_index]
            
            # Update widgets with new data
            dpg.set_value(quantity_widget_id, f"{amount:.8f}")  # Formatting for consistency
            dpg.set_value(price_widget_id, f"${price:.2f}")
        else:
            # Create new row for this price level
            with dpg.table_row(parent=self.table_id) as row_id:
                quantity_widget_id = dpg.add_text(f"{amount:.8f}")
                price_widget_id = dpg.add_text(f"${price:.2f}")
                self.row_widget_ids[row_index] = (quantity_widget_id, price_widget_id)
                self.price_to_row_index[price] = row_index

    def remove_extra_rows(self, total_rows_expected):
        # Get current row count
        current_row_count = max(self.row_widget_ids.keys(), default=-1) + 1
        
        if current_row_count > total_rows_expected:
            # Remove rows if there are too many
            for row_index in range(total_rows_expected, current_row_count):
                quantity_widget_id, price_widget_id = self.row_widget_ids[row_index]
                dpg.delete_item(quantity_widget_id)
                dpg.delete_item(price_widget_id)
                # Remove the row from our maps
                del self.row_widget_ids[row_index]
                # Also, remove the price level mapping if necessary
                price_level_to_remove = [price for price, index in self.price_to_row_index.items() if index == row_index]
                for price in price_level_to_remove:
                    del self.price_to_row_index[price]

    def _aggregate_order_book(self, orderbook, tick_size):
        def aggregate(orders):
            aggregated = {}
            for price, amount in orders:
                grouped_price = round(price / tick_size) * tick_size
                if grouped_price in aggregated:
                    aggregated[grouped_price] += amount
                else:
                    aggregated[grouped_price] = amount
            return [[price, amount] for price, amount in aggregated.items()]

        orderbook['bids_agg'] = aggregate(orderbook['bids'])
        orderbook['asks_agg'] = aggregate(orderbook['asks'])
        return orderbook

    def _on_tick_size_change(self, sender, app_data, user_data):
        self.tick_size = app_data
        
        dpg.delete_item(self.table_id, children_only=True)
        self.order_book_state = {}  
        self.row_widget_ids = {}  
        self.price_to_row_index = {}  
        # Add columns for the order book
        dpg.add_table_column(label="Quantity", parent=self.table_id)  # Bid/Ask quantities
        dpg.add_table_column(label="Price", parent=self.table_id)     # Price levels