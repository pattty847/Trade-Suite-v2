import math
import logging
import numpy as np


class OrderBookProcessor:
    def __init__(self, price_precision, initial_tick_size=None):
        self.aggregation_enabled = True
        self.tick_size = initial_tick_size or price_precision
        self.price_precision = price_precision
        self.spread_percentage = 0.01
        self.min_visible_levels = 20
        # Internal pre-allocated buffers (will resize on demand)
        self._bid_buf = None  # shape (N, 2) -> price, qty
        self._ask_buf = None  # shape (N, 2)
        self._bid_len = 0
        self._ask_len = 0
        
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
            
        # Convert to numpy arrays for faster processing (reuse buffers)
        bids_arr = self._copy_into_buffer('bid', raw_bids)
        asks_arr = self._copy_into_buffer('ask', raw_asks)
            
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

        # Group by tick size. Bids bucket down, asks bucket up, otherwise
        # adjacent levels collapse onto the same displayed price in the DOM.
        if descending:
            ticks = np.floor(side_raw[:, 0] / self.tick_size) * self.tick_size
        else:
            ticks = np.ceil(side_raw[:, 0] / self.tick_size) * self.tick_size

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
        minimum_tick = float(self.price_precision)
        presets = {minimum_tick}

        # If current price is invalid, estimate based on precision.
        if current_price is None or current_price <= 0:
            if self.price_precision < 0.01:
                current_price = 10000
            else:
                current_price = 1
            logging.debug(
                "No orderbook data for estimating presets, using estimated price: %s",
                current_price,
            )

        # Build a canonical "nice ticks" ladder anchored to the instrument precision.
        # This yields a stable sequence like:
        # 0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, ...
        mantissas = [1.0, 2.0, 2.5, 5.0]
        max_tick = max(float(current_price) * 0.05, minimum_tick * 4)
        exponent = 0

        while True:
            scale = 10 ** exponent
            added_any = False
            for mantissa in mantissas:
                preset = minimum_tick * mantissa * scale
                if preset < (minimum_tick * 0.999999):
                    continue
                if preset > max_tick:
                    continue
                presets.add(round(preset, 10))
                added_any = True
            if not added_any and (minimum_tick * scale) > max_tick:
                break
            exponent += 1
            if exponent > 16:
                break

        return sorted(presets)

    def build_dom_ladder(self, raw_bids, raw_asks, levels_per_side: int, current_price=None):
        """
        Build a DOM ladder centered on a discrete mid-price row.

        Returns:
            dict with:
                - rows: list[dict]
                - best_bid
                - best_ask
                - midpoint
        """
        processed = self.process_orderbook(raw_bids, raw_asks, current_price)
        if not processed:
            return None

        bids = processed["bids_processed"]
        asks = processed["asks_processed"]
        if not bids or not asks:
            return None

        best_bid = float(processed["best_bid"])
        best_ask = float(processed["best_ask"])
        midpoint = float(processed["midpoint"])
        tick = float(self.tick_size)
        center_price = self._normalize_price(round(midpoint / tick) * tick)

        ask_rows_inside_out = [
            row for row in asks if self._normalize_price(float(row[0])) > center_price and float(row[1]) > 0
        ][:levels_per_side]
        bid_rows_inside_out = [
            row for row in bids if self._normalize_price(float(row[0])) < center_price and float(row[1]) > 0
        ][:levels_per_side]

        ask_rows = []
        for row in reversed(ask_rows_inside_out):
            ask_rows.append(
                {
                    "kind": "ask",
                    "price": self._normalize_price(float(row[0])),
                    "bid_qty": 0.0,
                    "bid_cum": 0.0,
                    "ask_cum": float(row[2]),
                    "ask_qty": float(row[1]),
                }
            )

        mid_row = {
            "kind": "mid",
            "price": midpoint,
            "bid_qty": 0.0,
            "bid_cum": 0.0,
            "ask_cum": 0.0,
            "ask_qty": 0.0,
        }

        bid_rows = []
        for row in bid_rows_inside_out:
            bid_rows.append(
                {
                    "kind": "bid",
                    "price": self._normalize_price(float(row[0])),
                    "bid_qty": float(row[1]),
                    "bid_cum": float(row[2]),
                    "ask_cum": 0.0,
                    "ask_qty": 0.0,
                }
            )

        return {
            "rows": ask_rows + [mid_row] + bid_rows,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "midpoint": midpoint,
        }

    def build_visible_ladder(
        self,
        raw_bids,
        raw_asks,
        *,
        price_min: float,
        price_max: float,
        current_price=None,
    ):
        """
        Build a visible price-aligned ladder for the composite chart/orderflow view.
        Rows are populated levels only plus a center row when it falls inside the
        visible range.
        """
        processed = self.process_orderbook(raw_bids, raw_asks, current_price)
        if not processed:
            return None

        bids = processed["bids_processed"]
        asks = processed["asks_processed"]
        if not bids or not asks:
            return None

        best_bid = float(processed["best_bid"])
        best_ask = float(processed["best_ask"])
        midpoint = float(processed["midpoint"])
        lower = min(price_min, price_max)
        upper = max(price_min, price_max)

        ask_rows = [
            {
                "kind": "ask",
                "price": self._normalize_price(float(row[0])),
                "size": float(row[1]),
                "total": float(row[2]),
            }
            for row in asks
            if lower <= float(row[0]) <= upper and float(row[1]) > 0
        ]
        bid_rows = [
            {
                "kind": "bid",
                "price": self._normalize_price(float(row[0])),
                "size": float(row[1]),
                "total": float(row[2]),
            }
            for row in bids
            if lower <= float(row[0]) <= upper and float(row[1]) > 0
        ]

        rows = sorted(ask_rows + bid_rows, key=lambda row: row["price"], reverse=True)
        if lower <= midpoint <= upper:
            rows.append(
                {
                    "kind": "mid",
                    "price": midpoint,
                    "size": 0.0,
                    "total": 0.0,
                }
            )
            rows.sort(key=lambda row: row["price"], reverse=True)

        return {
            "rows": rows,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "midpoint": midpoint,
        }

    def _normalize_price(self, price: float) -> float:
        return round(float(price), 10)
    
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

    def _copy_into_buffer(self, side: str, data_list):
        """Copy raw list [[price, qty], ...] into (potentially pre-allocated) NumPy buffer.

        Args:
            side: 'bid' or 'ask'
            data_list: list[ [price, qty] ]

        Returns:
            view of the underlying buffer containing exactly len(data_list) rows.
        """
        import numpy as np  # local import to avoid global import issues

        # Determine which buffer to use
        if side == 'bid':
            buf_attr = '_bid_buf'
            len_attr = '_bid_len'
        else:
            buf_attr = '_ask_buf'
            len_attr = '_ask_len'

        curr_len = len(data_list)
        # Lazily allocate / resize buffer if needed
        buf = getattr(self, buf_attr)
        if buf is None or buf.shape[0] < curr_len:
            new_size = max(curr_len, 1024 if buf is None else buf.shape[0] * 2)
            buf = np.empty((new_size, 2), dtype=np.float64)
            setattr(self, buf_attr, buf)

        # Fast path: no data → return empty view
        if curr_len == 0:
            setattr(self, len_attr, 0)
            return buf[:0]

        # Copy into buffer – use vectorised assignment for speed
        view = np.asarray(data_list, dtype=np.float64)
        buf[:curr_len, :] = view
        setattr(self, len_attr, curr_len)
        return buf[:curr_len]
