import math
import logging
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
            
        # Filter orderbook to reasonable range to avoid processing entire book
        price_range_percentage = 0.10  # 10% range to capture
        if current_price is None and raw_bids and raw_asks:
            best_bid = raw_bids[0][0]
            best_ask = raw_asks[0][0]
            current_price = (best_bid + best_ask) / 2
            
        if current_price:
            min_price = current_price * (1 - price_range_percentage)
            max_price = current_price * (1 + price_range_percentage)
            
            # Filter bids and asks within the range
            limited_bids = [order for order in raw_bids if order[0] >= min_price]
            limited_asks = [order for order in raw_asks if order[0] <= max_price]
        else:
            # Fallback if we can't calculate midpoint
            limited_bids = raw_bids[:100]
            limited_asks = raw_asks[:100]
            
        # Process the filtered orderbook
        bids_processed, asks_processed = self._aggregate_and_group_order_book(
            limited_bids, limited_asks
        )
        
        # Return early if processing resulted in empty lists
        if not bids_processed or not asks_processed:
            logging.debug(f"Processing resulted in empty order book. Skipping.")
            return None
            
        # Calculate visualization parameters
        best_bid = bids_processed[0][0] if bids_processed else 0
        best_ask = asks_processed[0][0] if asks_processed else 0
        
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
        
        # Return all processed data in a single dictionary
        return {
            "bids_processed": bids_processed,
            "asks_processed": asks_processed,
            "x_axis_limits": x_axis_limits,
            "y_axis_limits": y_axis_limits,
            "bid_ask_ratio": bid_ask_ratio,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "midpoint": midpoint
        }
        
    def _aggregate_and_group_order_book(self, bids_raw, asks_raw):
        """
        Processes raw bid/ask lists, aggregates if requested, and calculates cumulative sums.
        
        Args:
            bids_raw (list): Raw bid data as [[price, quantity], ...]
            asks_raw (list): Raw ask data as [[price, quantity], ...]
            
        Returns:
            tuple: (bids_processed, asks_processed) with processed data
        """
        if self.aggregation_enabled:
            # Aggregate bids
            bids_grouped = defaultdict(float)
            for price, quantity in bids_raw:
                if self.tick_size > 0:
                    group = math.floor(price / self.tick_size) * self.tick_size
                    bids_grouped[group] += quantity
                else: # Avoid division by zero if tick_size is invalid
                    bids_grouped[price] += quantity
            # Sort descending by price, calculate cumulative
            bids_sorted = sorted(bids_grouped.items(), key=lambda item: item[0], reverse=True)
            bids_processed = []
            cumulative_qty = 0
            for price, quantity in bids_sorted:
                cumulative_qty += quantity
                bids_processed.append([price, quantity, cumulative_qty]) # [price, individual_qty, cumulative_qty]

            # Aggregate asks
            asks_grouped = defaultdict(float)
            for price, quantity in asks_raw:
                 if self.tick_size > 0:
                     group = math.floor(price / self.tick_size) * self.tick_size
                     asks_grouped[group] += quantity
                 else:
                     asks_grouped[price] += quantity
            # Sort ascending by price, calculate cumulative
            asks_sorted = sorted(asks_grouped.items(), key=lambda item: item[0])
            asks_processed = []
            cumulative_qty = 0
            for price, quantity in asks_sorted:
                cumulative_qty += quantity
                asks_processed.append([price, quantity, cumulative_qty]) # [price, individual_qty, cumulative_qty]

        else:
            # Non-aggregated: just sort
            # Sort bids descending by price
            bids_processed = sorted(bids_raw, key=lambda item: item[0], reverse=True)
             # Ensure format consistency: [price, quantity] (no cumulative here)
            bids_processed = [[p, q] for p, q in bids_processed]

            # Sort asks ascending by price
            asks_processed = sorted(asks_raw, key=lambda item: item[0])
             # Ensure format consistency: [price, quantity]
            asks_processed = [[p, q] for p, q in asks_processed]

        return bids_processed, asks_processed
        
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
        
        # Extract price lists
        if self.aggregation_enabled:
            bid_prices = [item[0] for item in bids_processed]
            ask_prices = [item[0] for item in asks_processed]
        else:
            bid_prices = [item[0] for item in bids_processed]
            ask_prices = [item[0] for item in asks_processed]
        
        # Find price levels that would be visible with these limits
        visible_bids = [p for p in bid_prices if p >= x_min]
        visible_asks = [p for p in ask_prices if p <= x_max]
        
        # Make sure we have enough levels visible on each side
        if len(visible_bids) < self.min_visible_levels and bid_prices:
            # Not enough bid levels visible, adjust x_min to show more bids
            target_level = min(self.min_visible_levels, len(bid_prices) - 1)
            x_min = bid_prices[target_level]  # Remember bids are sorted descending
            
        if len(visible_asks) < self.min_visible_levels and ask_prices:
            # Not enough ask levels visible, adjust x_max to show more asks
            target_level = min(self.min_visible_levels, len(ask_prices) - 1)
            x_max = ask_prices[target_level]  # Remember asks are sorted ascending
        
        # Make sure spread is centered on midpoint by adjusting limits symmetrically
        current_spread = x_max - x_min
        half_spread = current_spread / 2
        # Recenter around midpoint
        x_min = midpoint - half_spread
        x_max = midpoint + half_spread
        
        # Update visible bid/ask lists based on new limits
        visible_bids = [p for p in bid_prices if p >= x_min]
        visible_asks = [p for p in ask_prices if p <= x_max]
        
        return (x_min, x_max), visible_bids, visible_asks
        
    def _calculate_y_axis_and_ratio(self, bids_processed, asks_processed, x_limits):
        """
        Calculate y-axis limits and bid/ask ratio based on visible data.
        
        Returns:
            tuple: ((y_min, y_max), bid_ask_ratio)
        """
        x_min, x_max = x_limits
        
        # Calculate visible quantities based on aggregation mode
        if self.aggregation_enabled:
            visible_bids_qty = [item[2] for item in bids_processed if item[0] >= x_min]
            visible_asks_qty = [item[2] for item in asks_processed if item[0] <= x_max]
            visible_bids_indiv_qty_sum = sum(item[1] for item in bids_processed if item[0] >= x_min)
            visible_asks_indiv_qty_sum = sum(item[1] for item in asks_processed if item[0] <= x_max)
        else:
            visible_bids_qty = [item[1] for item in bids_processed if item[0] >= x_min]
            visible_asks_qty = [item[1] for item in asks_processed if item[0] <= x_max]
            visible_bids_indiv_qty_sum = sum(visible_bids_qty)
            visible_asks_indiv_qty_sum = sum(visible_asks_qty)

        # Calculate max height
        max_bid_y = max(visible_bids_qty) if visible_bids_qty else 0
        max_ask_y = max(visible_asks_qty) if visible_asks_qty else 0
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
