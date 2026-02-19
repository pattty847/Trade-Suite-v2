# sentinel/schema.py
from typing import List, Tuple, Dict

# Expected trade data structure from data_source.watch_trades
# trade_event = {
#     'exchange': str, # e.g., 'coinbase'
#     'trade_data': {
#         'id': str, # Trade ID
#         'timestamp': int, # Milliseconds since epoch
#         'datetime': str, # ISO8601 datetime string
#         'symbol': str, # e.g., 'BTC/USD'
#         'side': str, # 'buy' or 'sell'
#         'price': float,
#         'amount': float,
#         'cost': float, # price * amount
#         # 'takerOrMaker': str, (optional)
#         # 'fee': { 'cost': float, 'currency': str }, (optional)
#         # 'info': dict (original exchange response)
#     }
# }

def build_trade_lp(exchange: str, symbol: str, side: str, size: float, price: float, trade_id: str, timestamp_ns: int) -> str:
    """
    Builds a InfluxDB Line Protocol string for a single trade.

    Args:
        exchange: Name of the exchange (e.g., 'coinbase').
        symbol: Trading symbol (e.g., 'BTC-USD', sanitized for InfluxDB).
        side: 'buy' or 'sell'.
        size: Quantity of the trade.
        price: Price of the trade.
        trade_id: Unique identifier for the trade from the exchange.
        timestamp_ns: Timestamp of the trade in nanoseconds.

    Returns:
        A string formatted for InfluxDB Line Protocol.
        Example: trades,exchange=coinbase,symbol=BTC-USD,side=buy trade_id="12345",price=50000.1,size=0.01 1678886400000000000
    """
    # Sanitize symbol: CCXT uses 'BTC/USD', InfluxDB prefers 'BTC-USD' or similar for tags
    safe_symbol = symbol.replace("/", "-")
    # Fields must be float, int, bool, or string. Strings need to be double-quoted.
    # Tags are not quoted.
    lp = f"trades,exchange={exchange},symbol={safe_symbol},side={side} " \
         f"trade_id=\"{trade_id}\",price={float(price)},size={float(size)} " \
         f"{timestamp_ns}"
    return lp


# Expected order book data structure from data_source.watch_orderbook
# orderbook_event = {
#     'exchange': str, # e.g., 'coinbase'
#     'orderbook': {
#         'symbol': str, # e.g., 'BTC/USD'
#         'timestamp': int, # Milliseconds since epoch for the snapshot
#         'datetime': str, # ISO8601 string
#         'bids': List[Tuple[float, float]], # List of [price, amount]
#         'asks': List[Tuple[float, float]], # List of [price, amount]
#         # 'nonce': int (optional)
#         # 'info': { 'sequence': int } (for Coinbase Pro, sequence is often in info for snapshots from REST)
#     }
# }

from sentinel import config # For binning constants
import math # For rounding

def build_book_lp(
    exchange: str, 
    symbol: str, 
    bids: List[Tuple[float, float]], 
    asks: List[Tuple[float, float]], 
    timestamp_ns: int,
    sequence: int | None = None # Optional: sequence number for the book snapshot
) -> List[str]:
    """
    Builds InfluxDB Line Protocol strings for an order book snapshot, binned by basis points (bps) from mid-price.
    Generates a fixed number of points based on config.ORDER_BOOK_MAX_BINS_PER_SIDE.

    Args:
        exchange: Name of the exchange.
        symbol: Trading symbol (e.g., 'BTC-USD').
        bids: Raw list of [price, amount] for bids, sorted best (highest price) first.
        asks: Raw list of [price, amount] for asks, sorted best (lowest price) first.
        timestamp_ns: Timestamp of the snapshot in nanoseconds.
        sequence: Optional sequence number of this order book state.

    Returns:
        A list of strings formatted for InfluxDB Line Protocol for binned book data.
        Example: order_book,exchange=cb,symbol=BTC-USD,side=bid,bin_bps_offset=-1 total_qty=1.23 1678886400000000000
    """
    lines = []
    safe_symbol = symbol.replace("/", "-")

    if not bids or not asks or not bids[0] or not asks[0]:
        # logging.warning(f"[{exchange}-{safe_symbol}] Insufficient data for binned order book: bids or asks empty or invalid.")
        return [] # Cannot calculate mid-price or meaningful book

    mid_price = (bids[0][0] + asks[0][0]) / 2.0
    if mid_price == 0: # Avoid division by zero
        # logging.warning(f"[{exchange}-{safe_symbol}] Mid price is zero, cannot bin order book.")
        return []

    # Initialize bins: keys are bps offsets from -MAX_BINS to +MAX_BINS (relative to BIN_BPS)
    # e.g., if MAX_BINS_PER_SIDE = 5, bins from -5 to 5.
    # Bin 0 represents quotes closest to mid-price within +/- (BIN_BPS/2).
    num_bins_total = config.ORDER_BOOK_MAX_BINS_PER_SIDE * 2 + 1 # e.g., 5 for bids, 5 for asks, 1 for zero-offset
    # bins will store total quantity for each bps_offset bin
    # We will create MAX_BINS_PER_SIDE on bid side (negative offsets) and MAX_BINS_PER_SIDE on ask side (positive offsets)
    # Bin 0 represents the very center (e.g. -2.5bps to +2.5bps if BIN_BPS is 5)
    # Let's use MAX_BINS_PER_SIDE for each side, so -5 to -1 for bids, 1 to 5 for asks, bin 0 for center.
    
    # bins dict: key is integer bps_offset_index, value is aggregated quantity.
    # bps_offset_index ranges from -config.ORDER_BOOK_MAX_BINS_PER_SIDE to +config.ORDER_BOOK_MAX_BINS_PER_SIDE.
    binned_quantities = {i: 0.0 for i in range(-config.ORDER_BOOK_MAX_BINS_PER_SIDE, config.ORDER_BOOK_MAX_BINS_PER_SIDE + 1)}

    # Process bids
    for price, qty in bids:
        if price <= 0: continue
        # bps_offset = (price - mid_price) / mid_price * 10000 # Raw BPS offset
        # bps_offset_index = math.floor(bps_offset / config.ORDER_BOOK_BIN_BPS) # Gist example used round
        # Let's follow the gist's rounding logic: int(round((price - mid) / mid * 1e4 / BIN_BPS))
        bps_offset_index = int(round((price - mid_price) / mid_price * 10000 / config.ORDER_BOOK_BIN_BPS))
        
        # Clamp to the defined bin range
        if bps_offset_index < -config.ORDER_BOOK_MAX_BINS_PER_SIDE:
            bps_offset_index = -config.ORDER_BOOK_MAX_BINS_PER_SIDE
        elif bps_offset_index > config.ORDER_BOOK_MAX_BINS_PER_SIDE: # This case mainly for asks, but good to be robust
            bps_offset_index = config.ORDER_BOOK_MAX_BINS_PER_SIDE
        
        if -config.ORDER_BOOK_MAX_BINS_PER_SIDE <= bps_offset_index <= config.ORDER_BOOK_MAX_BINS_PER_SIDE:
            binned_quantities[bps_offset_index] += qty

    # Process asks
    for price, qty in asks:
        if price <= 0: continue
        bps_offset_index = int(round((price - mid_price) / mid_price * 10000 / config.ORDER_BOOK_BIN_BPS))
        
        if bps_offset_index < -config.ORDER_BOOK_MAX_BINS_PER_SIDE:
            bps_offset_index = -config.ORDER_BOOK_MAX_BINS_PER_SIDE
        elif bps_offset_index > config.ORDER_BOOK_MAX_BINS_PER_SIDE:
            bps_offset_index = config.ORDER_BOOK_MAX_BINS_PER_SIDE

        if -config.ORDER_BOOK_MAX_BINS_PER_SIDE <= bps_offset_index <= config.ORDER_BOOK_MAX_BINS_PER_SIDE:
            binned_quantities[bps_offset_index] += qty
    
    # Generate Line Protocol for each bin that has quantity or all defined bins
    # The gist implies emitting all defined bins, even if quantity is 0, for constant cardinality.
    for bps_offset_idx, total_qty in binned_quantities.items():
        # Determine side based on offset. Bin 0 can be considered neutral or assigned based on convention.
        # For simplicity, let's say negative is bid, positive is ask. Bin 0 can be split or reported as 'mid'.
        # The gist example: side = "bid" if off_bp < 0 else "ask"
        # This means bin 0 is 'ask'. If that's not desired, adjust.
        # Let's adjust so bin 0 is 'mid', <0 is 'bid', >0 is 'ask' for clarity in tags.
        if bps_offset_idx < 0:
            side = "bid"
        elif bps_offset_idx > 0:
            side = "ask"
        else: # bps_offset_idx == 0
            side = "mid_bin" # A neutral bin at the center
        
        # Measurement: order_book_binned (or just order_book if only one type of book data per bucket)
        lp = f"order_book,exchange={exchange},symbol={safe_symbol},side={side},bps_offset_idx={bps_offset_idx} " \
             f"total_qty={total_qty:.8f},mid_price={mid_price:.2f}" # Added mid_price, formatted to 2 decimal places
        if sequence is not None:
            lp += f",sequence={sequence}i" # Add sequence as an integer field
        lp += f" {timestamp_ns}"
        lines.append(lp)

    return lines


def build_raw_book_lp(
    exchange: str, 
    symbol: str, 
    bids: List[Tuple[float, float]], 
    asks: List[Tuple[float, float]], 
    timestamp_ns: int,
    top_n: int = config.RAW_BOOK_TOP_N, # Use constant from config
    sequence: int | None = None # Optional: sequence number
) -> List[str]:
    """
    Builds InfluxDB Line Protocol strings for the top N raw levels of an order book snapshot.

    Args:
        exchange: Name of the exchange.
        symbol: Trading symbol (e.g., 'BTC-USD').
        bids: Raw list of [price, amount] for bids, sorted best (highest price) first.
        asks: Raw list of [price, amount] for asks, sorted best (lowest price) first.
        timestamp_ns: Timestamp of the snapshot in nanoseconds.
        top_n: Number of top bid and ask levels to include.
        sequence: Optional sequence number of this order book state.

    Returns:
        A list of strings formatted for InfluxDB Line Protocol for raw book data.
        Example: raw_order_book,exchange=cb,symbol=BTC-USD,side=bid,level=0 price=49999.0,amount=0.5 1678886400000000000
    """
    lines = []
    safe_symbol = symbol.replace("/", "-")

    # Process top N bids
    for i, (price, amount) in enumerate(bids[:top_n]):
        lp = f"raw_order_book,exchange={exchange},symbol={safe_symbol},side=bid,level={i} " \
             f"price={float(price)},amount={float(amount):.8f}" # Format amount
        if sequence is not None:
            lp += f",sequence={sequence}i"
        lp += f" {timestamp_ns}"
        lines.append(lp)

    # Process top N asks
    for i, (price, amount) in enumerate(asks[:top_n]):
        lp = f"raw_order_book,exchange={exchange},symbol={safe_symbol},side=ask,level={i} " \
             f"price={float(price)},amount={float(amount):.8f}" # Format amount
        if sequence is not None:
            lp += f",sequence={sequence}i"
        lp += f" {timestamp_ns}"
        lines.append(lp)
        
    return lines 