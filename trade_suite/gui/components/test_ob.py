import asyncio
import logging
from typing import Dict, List

import dearpygui.dearpygui as dpg
import pandas as pd
import numpy as np
import time

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.data.data_source import Data

class TestOB:
    def __init__(self, tab, data: Data, emitter: SignalEmitter) -> None:
        self.tab = tab
        self.data = data
        self.emitter = emitter
        self.table_id = None
        
        # Configuration
        self.max_depth = 15  # Number of price levels to display on each side
        self.tick_size = 100  # Default tick size
        self.window_id = None
        
        # Cell storage: Each entry will be (price_cell_id, quantity_cell_id)
        self.ask_cells = []
        self.bid_cells = []
        self.spread_cell = None
        
        # Last seen orderbook data - store for refreshing on tick size change
        self.last_orderbook = None
        
        # Performance optimization - track last update time for rate limiting
        self.last_update_time = 0
        self.update_interval = 0.05  # Minimum time between updates (in seconds)
        
        # Dictionary to store the last color for each cell
        self.last_colors = {}
        
        # Register for orderbook updates
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)
    
    def launch(self):
        """Create the order book window and table"""
        # Generate a unique window name
        window_name = f"Order Book {self.tab}"
        window_tag = f"ob_window_{self.tab}"
        table_tag = f"ob_table_{self.tab}"
        
        # Delete existing window if it exists
        if self.window_id is not None and dpg.does_item_exist(self.window_id):
            dpg.delete_item(self.window_id)
            # Reset cell collections since they'll be recreated
            self.ask_cells = []
            self.bid_cells = []
        
        # Create the window
        with dpg.window(label=window_name, width=250, height=775, pos=[25, 25], tag=window_tag) as self.window_id:
            # Add tick size control
            dpg.add_slider_float(
                label="Tick Size", 
                default_value=self.tick_size,
                min_value=0.01,
                max_value=1000.0,
                format="%.2f",
                callback=self._on_tick_size_change
            )
            
            # Create the table with clipper=True for better performance
            with dpg.table(
                header_row=True,
                resizable=True,
                borders_innerH=True,
                borders_innerV=True,
                borders_outerH=True,
                borders_outerV=True,
                clipper=True,  # Enable clipping for better performance
                delay_search=True,  # Improve performance for tables with search functionality
                tag=table_tag
            ) as self.table_id:
                # Add columns for price and quantity
                dpg.add_table_column(label="Price")
                dpg.add_table_column(label="Quantity")
                
                # Create ask rows (will be populated top-to-bottom with highest ask at bottom)
                for i in range(self.max_depth):
                    with dpg.table_row():
                        price_cell = dpg.add_text("", color=[200, 100, 100])
                        qty_cell = dpg.add_text("", color=[200, 100, 100])
                        self.ask_cells.append((price_cell, qty_cell))
                
                # Create spread row
                with dpg.table_row(tag=f"spread_row_{self.tab}"):
                    self.spread_cell = dpg.add_text("Spread: --")
                    # Empty cell for alignment
                    dpg.add_text("")
                
                # Create bid rows (will be populated top-to-bottom with highest bid at top)
                for i in range(self.max_depth):
                    with dpg.table_row():
                        price_cell = dpg.add_text("", color=[100, 200, 100])
                        qty_cell = dpg.add_text("", color=[100, 200, 100])
                        self.bid_cells.append((price_cell, qty_cell))
    
    def _on_order_book_update(self, tab, exchange, orderbook):
        """Process an order book update from the exchange"""
        # Ignore updates for other tabs
        if tab != self.tab:
            return
        
        # Always store the latest orderbook data (even if we skip rendering)
        self.last_orderbook = orderbook
        
        # Apply rate limiting - only process updates at most once every update_interval seconds
        current_time = time.time()
        time_since_last_update = current_time - self.last_update_time
        
        if time_since_last_update < self.update_interval:
            # Too soon since last update, skip this one
            return
            
        # Update the timestamp for rate limiting
        self.last_update_time = current_time
        
        # Process and display the order book
        self._process_and_display_orderbook(orderbook)
    
    def _process_and_display_orderbook(self, orderbook):
        """Aggregate and display the order book data"""
        if not orderbook:
            return
            
        # Aggregate the order book
        aggregated_book = self._aggregate_order_book(orderbook, self.tick_size)
        
        # Extract and sort the aggregated bid and ask data
        bids_agg = aggregated_book['bids_agg']
        asks_agg = aggregated_book['asks_agg']
        
        # Sort bids in descending order (highest bid first)
        bids_agg.sort(key=lambda x: x[0], reverse=True)
        
        # Sort asks in ascending order (lowest ask first)
        asks_agg.sort(key=lambda x: x[0])
        
        # Reverse asks for display (highest ask at top)
        asks_display = list(reversed(asks_agg[:self.max_depth]))
        
        # Calculate spread
        best_bid_price = bids_agg[0][0] if bids_agg else 0
        best_ask_price = asks_agg[0][0] if asks_agg else 0
        spread = best_ask_price - best_bid_price if best_ask_price and best_bid_price else 0
        
        # Use DPG staging to batch updates more efficiently
        # This reduces the number of render passes
        dpg.push_container_stack(self.table_id)
        
        # Update ask cells (we display highest ask at top)
        for i in range(self.max_depth):
            price_cell, qty_cell = self.ask_cells[i]
            
            if i < len(asks_display):
                price, quantity = asks_display[i]
                # Highlight best ask
                is_best_ask = (i == len(asks_display) - 1)
                color = [255, 80, 80] if is_best_ask else [200, 100, 100]
                
                # Direct updates for better performance
                dpg.set_value(price_cell, f"${price:.2f}")
                dpg.set_value(qty_cell, f"{quantity:.4f}")
                
                # Check if we need to update the color using dictionary lookup
                if price_cell not in self.last_colors or self.last_colors.get(price_cell) != color:
                    dpg.configure_item(price_cell, color=color)
                    dpg.configure_item(qty_cell, color=color)
                    self.last_colors[price_cell] = color
                    self.last_colors[qty_cell] = color
            else:
                # Clear unused cells
                dpg.set_value(price_cell, "")
                dpg.set_value(qty_cell, "")
        
        # Update spread
        dpg.set_value(self.spread_cell, f"Spread: ${spread:.2f}")
        
        # Update bid cells
        for i in range(self.max_depth):
            price_cell, qty_cell = self.bid_cells[i]
            
            if i < len(bids_agg):
                price, quantity = bids_agg[i]
                # Highlight best bid
                is_best_bid = (i == 0)
                color = [80, 255, 80] if is_best_bid else [100, 200, 100]
                
                # Direct updates for better performance
                dpg.set_value(price_cell, f"${price:.2f}")
                dpg.set_value(qty_cell, f"{quantity:.4f}")
                
                # Check if we need to update the color using dictionary lookup
                if price_cell not in self.last_colors or self.last_colors.get(price_cell) != color:
                    dpg.configure_item(price_cell, color=color)
                    dpg.configure_item(qty_cell, color=color)
                    self.last_colors[price_cell] = color
                    self.last_colors[qty_cell] = color
            else:
                # Clear unused cells
                dpg.set_value(price_cell, "")
                dpg.set_value(qty_cell, "")
        
        # Pop container stack to apply all updates at once
        dpg.pop_container_stack()
    
    def _aggregate_order_book(self, orderbook, tick_size):
        """Aggregate the order book based on tick size"""
        def aggregate(orders):
            if not orders:
                return []
                
            # Use a dictionary for aggregation
            aggregated = {}
            for price, amount in orders:
                # Group prices by tick size
                grouped_price = round(price / tick_size) * tick_size
                
                # Add amount to the appropriate bucket
                if grouped_price in aggregated:
                    aggregated[grouped_price] += amount
                else:
                    aggregated[grouped_price] = amount
            
            # Convert back to list of [price, amount] pairs
            result = [[price, amount] for price, amount in aggregated.items()]
            return result

        # Create a copy to avoid modifying the original
        result = dict(orderbook)
        result['bids_agg'] = aggregate(orderbook['bids'])
        result['asks_agg'] = aggregate(orderbook['asks'])
        return result

    def _on_tick_size_change(self, sender, app_data, user_data):
        """Handle tick size slider changes"""
        # Update tick size
        self.tick_size = app_data
        
        # Reprocess the orderbook with the new tick size
        if self.last_orderbook:
            self._process_and_display_orderbook(self.last_orderbook)