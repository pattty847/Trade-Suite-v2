import math
import logging
import numpy as np
from collections import defaultdict


class OrderBookProcessor:
    def __init__(self, price_precision, initial_tick_size=None):
        self.aggregation_enabled = True
        self.tick_size = initial_tick_size or price_precision
        self.price_precision = price_precision
        self.spread_percentage = 0.01
        self.min_visible_levels = 20
        
    def process_orderbook(self, raw_bids, raw_asks, current_price=None):
        """
        Process the raw orderbook data based on current settings.
        
        Args:
            raw_bids (list): Raw bid data as [[price, quantity], ...]
            raw_asks (list): Raw ask data as [[price, quantity], ...]
            current_price (float, optional): Current market price, used for calculations
        
        Returns:
            dict: A dictionary containing:
                - bids_processed/asks_processed: Processed bid/ask data
                - x_axis_limits: Suggested x-axis limits (min, max)
                - y_axis_limits: Suggested y-axis limits (min, max)
                - bid_ask_ratio: Current bid/ask volume ratio
                - best_bid/best_ask: Best bid and ask prices
        """
        # Check if lists are empty
        if not raw_bids or not raw_asks:
            logging.debug(f"Empty order book data received. Skipping processing.")
            return None
            
        # Convert to numpy arrays for faster processing
        bids_arr = np.array(raw_bids, dtype=float)
        asks_arr = np.array(raw_asks, dtype=float)
            
        # Filter orderbook to reasonable range to avoid processing entire book
        price_range_percentage = 0.25  # 25% range to capture
        if current_price is None and raw_bids and raw_asks:
            best_bid = bids_arr[0, 0]
            best_ask = asks_arr[0, 0]
            current_price = (best_bid + best_ask) / 2
            
        if current_price:
            min_price = current_price * (1 - price_range_percentage)
            max_price = current_price * (1 + price_range_percentage)
            
            # Filter bids and asks within the range using vectorized operations
            bids_mask = bids_arr[:, 0] >= min_price
            asks_mask = asks_arr[:, 0] <= max_price
            limited_bids = bids_arr[bids_mask]
            limited_asks = asks_arr[asks_mask]
        else:
            # Fallback if we can't calculate midpoint
            limited_bids = bids_arr[:100]
            limited_asks = asks_arr[:100]
            
        # Process the filtered orderbook
        bids_processed, asks_processed = self._aggregate_and_group_order_book(
            limited_bids, limited_asks
        )
        
        # Return early if processing resulted in empty lists
        if len(bids_processed) == 0 or len(asks_processed) == 0:
            logging.debug(f"Processing resulted in empty order book. Skipping.")
            return None
            
        # Calculate visualization parameters
        best_bid = bids_processed[0][0] if bids_processed.size > 0 else 0
        best_ask = asks_processed[0][0] if asks_processed.size > 0 else 0
        
        # Handle equal bid/ask edge case (usually from aggregation)
        if best_ask <= best_bid:
            logging.debug(f"Equal bid/ask ({best_bid}/{best_ask}) detected - likely due to aggregation.")
            best_ask = best_bid * 1.000001  # Add tiny artificial spread
            
        # Calculate midpoint
        midpoint = (best_bid + best_ask) / 2
        
        # Calculate axis limits and visible data
        x_axis_limits, visible_bids, visible_asks = self._calculate_axis_limits(
            midpoint, bids_processed, asks_processed
        )
        
        # Calculate y-axis limits based on visible data
        y_axis_limits, bid_ask_ratio = self._calculate_y_axis_and_ratio(
            bids_processed, asks_processed, x_axis_limits
        )
        
        # Convert NumPy arrays to lists for compatibility with existing code
        bids_processed_list = bids_processed.tolist() if isinstance(bids_processed, np.ndarray) else bids_processed
        asks_processed_list = asks_processed.tolist() if isinstance(asks_processed, np.ndarray) else asks_processed
        
        # Return all processed data in a single dictionary
        return {
            "bids_processed": bids_processed_list,
            "asks_processed": asks_processed_list,
            "x_axis_limits": x_axis_limits,
            "y_axis_limits": y_axis_limits,
            "bid_ask_ratio": bid_ask_ratio,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "midpoint": midpoint
        }
        
    def _aggregate_and_group_order_book(self, bids_raw, asks_raw):
        """
        Processes raw bid/ask arrays, aggregates if requested, and calculates cumulative sums.
        
        Args:
            bids_raw (ndarray): Raw bid data as [[price, quantity], ...]
            asks_raw (ndarray): Raw ask data as [[price, quantity], ...]
            
        Returns:
            tuple: (bids_processed, asks_processed) with processed data as numpy arrays
        """
        if self.aggregation_enabled and self.tick_size > 0:
            # Vectorized aggregation for bids
            bids_processed = self._vector_aggregate(bids_raw, descending=True)
            
            # Vectorized aggregation for asks
            asks_processed = self._vector_aggregate(asks_raw, descending=False)
        else:
            # Non-aggregated: just sort
            if len(bids_raw) > 0:
                # Sort bids descending by price
                bid_order = np.argsort(-bids_raw[:, 0])  # Descending sort
                bids_sorted = bids_raw[bid_order]
                
                # Add cumulative column
                if bids_sorted.size > 0:
                    cum_qty = np.cumsum(bids_sorted[:, 1])
                    bids_processed = np.column_stack([bids_sorted, cum_qty])
                else:
                    bids_processed = np.array([])
            else:
                bids_processed = np.array([])
                
            if len(asks_raw) > 0:
                # Sort asks ascending by price
                ask_order = np.argsort(asks_raw[:, 0])  # Ascending sort
                asks_sorted = asks_raw[ask_order]
                
                # Add cumulative column
                if asks_sorted.size > 0:
                    cum_qty = np.cumsum(asks_sorted[:, 1])
                    asks_processed = np.column_stack([asks_sorted, cum_qty])
                else:
                    asks_processed = np.array([])
            else:
                asks_processed = np.array([])

        return bids_processed, asks_processed
    
    def _vector_aggregate(self, side_raw, descending=False):
        """
        Vectorized version of order book aggregation using NumPy.
        
        Args:
            side_raw (ndarray): Raw price/qty data as [[price, quantity], ...]
            descending (bool): Sort order (True for bids, False for asks)
            
        Returns:
            ndarray: Processed data as [[price, qty, cumulative_qty], ...]
        """
        if side_raw.size == 0:
            return np.array([])
            
        # Group by tick size
        ticks = np.floor(side_raw[:, 0] / self.tick_size) * self.tick_size
        
        # Find unique price levels and their indices
        uniq_prices, inverse_indices = np.unique(ticks, return_inverse=True)
        
        # Sum quantities at each price level
        qty_sum = np.bincount(inverse_indices, weights=side_raw[:, 1])
        
        # Sort by price
        if descending:
            order = np.argsort(-uniq_prices)  # Descending for bids
        else:
            order = np.argsort(uniq_prices)   # Ascending for asks
            
        prices = uniq_prices[order]
        quantities = qty_sum[order]
        
        # Calculate cumulative quantities
        cumulative = np.cumsum(quantities)
        
        # Stack into final result
        return np.column_stack([prices, quantities, cumulative])
        
    def _calculate_axis_limits(self, midpoint, bids_processed, asks_processed):
        """
        Calculate appropriate x-axis limits based on spread percentage and visible levels.
        
        Returns:
            tuple: (x_min, x_max), visible_bids, visible_asks
        """
        # Calculate dynamic spread based on the spread percentage and midpoint
        dynamic_spread = midpoint * self.spread_percentage
        
        # Calculate initial x-axis limits based on the spread
        x_min = midpoint - dynamic_spread
        x_max = midpoint + dynamic_spread
        
        # Extract price arrays
        if isinstance(bids_processed, np.ndarray) and bids_processed.size > 0:
            bid_prices = bids_processed[:, 0]
        else:
            bid_prices = np.array([])
            
        if isinstance(asks_processed, np.ndarray) and asks_processed.size > 0:
            ask_prices = asks_processed[:, 0]
        else:
            ask_prices = np.array([])
        
        # Find price levels that would be visible with these limits using vectorized operations
        visible_bids = bid_prices[bid_prices >= x_min] if bid_prices.size > 0 else np.array([])
        visible_asks = ask_prices[ask_prices <= x_max] if ask_prices.size > 0 else np.array([])
        
        # Make sure we have enough levels visible on each side
        if len(visible_bids) < self.min_visible_levels and bid_prices.size > 0:
            # Not enough bid levels visible, adjust x_min to show more bids
            target_level = min(self.min_visible_levels, bid_prices.size - 1)
            if target_level >= 0 and target_level < bid_prices.size:
                x_min = bid_prices[target_level]  # Remember bids are sorted descending
            
        if len(visible_asks) < self.min_visible_levels and ask_prices.size > 0:
            # Not enough ask levels visible, adjust x_max to show more asks
            target_level = min(self.min_visible_levels, ask_prices.size - 1)
            if target_level >= 0 and target_level < ask_prices.size:
                x_max = ask_prices[target_level]  # Remember asks are sorted ascending
        
        # Make sure spread is centered on midpoint by adjusting limits symmetrically
        current_spread = x_max - x_min
        half_spread = current_spread / 2
        # Recenter around midpoint
        x_min = midpoint - half_spread
        x_max = midpoint + half_spread
        
        # Update visible bid/ask lists based on new limits
        visible_bids = bid_prices[bid_prices >= x_min] if bid_prices.size > 0 else np.array([])
        visible_asks = ask_prices[ask_prices <= x_max] if ask_prices.size > 0 else np.array([])
        
        return (x_min, x_max), visible_bids, visible_asks
        
    def _calculate_y_axis_and_ratio(self, bids_processed, asks_processed, x_limits):
        """
        Calculate y-axis limits and bid/ask ratio based on visible data.
        
        Returns:
            tuple: ((y_min, y_max), bid_ask_ratio)
        """
        x_min, x_max = x_limits
        
        # Calculate visible quantities based on aggregation mode
        if isinstance(bids_processed, np.ndarray) and bids_processed.size > 0:
            # Use vectorized operations with boolean masks
            bids_mask = bids_processed[:, 0] >= x_min
            visible_bids_qty = bids_processed[bids_mask, 2] if np.any(bids_mask) else np.array([])
            visible_bids_indiv_qty = bids_processed[bids_mask, 1] if np.any(bids_mask) else np.array([])
            visible_bids_indiv_qty_sum = np.sum(visible_bids_indiv_qty) if visible_bids_indiv_qty.size > 0 else 0
        else:
            visible_bids_qty = np.array([])
            visible_bids_indiv_qty_sum = 0
            
        if isinstance(asks_processed, np.ndarray) and asks_processed.size > 0:
            # Use vectorized operations with boolean masks
            asks_mask = asks_processed[:, 0] <= x_max
            visible_asks_qty = asks_processed[asks_mask, 2] if np.any(asks_mask) else np.array([])
            visible_asks_indiv_qty = asks_processed[asks_mask, 1] if np.any(asks_mask) else np.array([])
            visible_asks_indiv_qty_sum = np.sum(visible_asks_indiv_qty) if visible_asks_indiv_qty.size > 0 else 0
        else:
            visible_asks_qty = np.array([])
            visible_asks_indiv_qty_sum = 0

        # Calculate max height
        max_bid_y = np.max(visible_bids_qty) if visible_bids_qty.size > 0 else 0
        max_ask_y = np.max(visible_asks_qty) if visible_asks_qty.size > 0 else 0
        max_y_value = max(max_bid_y, max_ask_y, 0.1)
        
        # Add buffer for better visual appearance
        buffer = max_y_value * 0.1
        y_min = 0
        y_max = max_y_value + buffer
        
        # Calculate bid-ask ratio for displayed data
        if visible_asks_indiv_qty_sum > 0:
            bid_ask_ratio = visible_bids_indiv_qty_sum / visible_asks_indiv_qty_sum
        elif visible_bids_indiv_qty_sum > 0:
            bid_ask_ratio = float('inf')
        else:
            bid_ask_ratio = 1.0
            
        return (y_min, y_max), bid_ask_ratio
        
    def toggle_aggregation(self):
        """
        Toggle the aggregation mode.
        
        Returns:
            bool: The new aggregation state
        """
        self.aggregation_enabled = not self.aggregation_enabled
        return self.aggregation_enabled
        
    def set_tick_size(self, new_tick_size):
        """
        Set the tick size for aggregation.
        
        Args:
            new_tick_size (float): The new tick size value
            
        Returns:
            float: The updated tick size
        """
        if new_tick_size > 0:
            self.tick_size = new_tick_size
        return self.tick_size
    
    def set_spread_percentage(self, percentage):
        """
        Set the percentage spread to display.
        
        Args:
            percentage (float): The new spread percentage
            
        Returns:
            float: The updated spread percentage
        """
        self.spread_percentage = percentage
        return self.spread_percentage
        
    def calculate_tick_presets(self, current_price):
        """
        Calculate appropriate tick size presets based on asset precision and price.
        
        Args:
            current_price (float): Current price of the asset
            
        Returns:
            list: Sorted list of tick size presets
        """
        presets = []
        # Start with the base precision (smallest possible increment)
        presets.append(self.price_precision)
        
        # If current price is invalid, estimate based on precision
        if current_price is None or current_price <= 0:
            # Estimate a reasonable price based on precision
            # For BTC-like assets (small precision), assume higher price
            if self.price_precision < 0.01:
                current_price = 10000  # Default high value like BTC
            else:
                current_price = 1  # Default low value like smaller altcoins
            logging.debug(f"No orderbook data for estimating presets, using estimated price: {current_price}")
        
        # Add multiples: 2x, 5x, 10x, 50x, 100x, 500x, 1000x
        multipliers = [2, 5, 10, 50, 100, 500, 1000]
        for mult in multipliers:
            preset = self.price_precision * mult
            # Only add if it makes sense for this asset
            # (e.g., don't add a 1000x preset if that would be > 5% of the price)
            if preset < current_price * 0.05:  # Cap at 5% of current price
                presets.append(preset)
        
        # Add some "round number" presets based on asset price magnitude
        magnitude = 10 ** math.floor(math.log10(current_price))  # Order of magnitude
        round_numbers = [0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50, 100]
        
        for num in round_numbers:
            round_preset = num * magnitude
            if round_preset >= self.price_precision * 2:  # Ensure larger than base
                presets.append(round_preset)
        
        # Sort and remove duplicates
        return sorted(list(set(presets)))
    
    def increase_tick_size(self, current_price):
        """
        Increase tick size to the next preset value.
        
        Args:
            current_price (float): Current price, used for preset calculation
            
        Returns:
            float: The new tick size
        """
        presets = self.calculate_tick_presets(current_price)
        idx = presets.index(self.tick_size) if self.tick_size in presets else 0
        if idx < len(presets) - 1:  # Only increase if not already at maximum
            self.tick_size = presets[idx+1]
        return self.tick_size
    
    def decrease_tick_size(self, current_price):
        """
        Decrease tick size to the previous preset value.
        
        Args:
            current_price (float): Current price, used for preset calculation
            
        Returns:
            float: The new tick size
        """
        presets = self.calculate_tick_presets(current_price)
        idx = presets.index(self.tick_size) if self.tick_size in presets else 0
        if idx > 0:  # Only decrease if not already at minimum
            self.tick_size = presets[idx-1]
        return self.tick_size
