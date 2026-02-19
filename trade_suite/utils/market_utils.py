import ccxt.async_support as ccxt # Use async_support for the exchange object type hint
import logging
from typing import List

async def get_top_x_symbols_by_volume(
    exchange: ccxt.Exchange, 
    quote_currency: str = 'USD', 
    count: int = 200,
    volume_field: str = 'volume_24h' # Field in market['info'] that Coinbase uses for USD volume
) -> List[str]:
    """
    Fetches all markets from the given exchange, filters them by the quote currency,
    sorts them by a specified volume field (descending), and returns the top X symbols.

    Args:
        exchange: The ccxt.Exchange object (async version).
        quote_currency: The quote currency to filter by (e.g., 'USD', 'USDT').
        count: The number of top symbols to return.
        volume_field: The key in the market['info'] dictionary that contains the quote volume.
                      For Coinbase, 'volume_24h' typically represents 24h volume in the quote currency.
                      For other exchanges, this might be 'quoteVolume' directly in market or another info field.

    Returns:
        A list of the top X symbols (e.g., ['BTC/USD', 'ETH/USD']).
        Returns an empty list if markets cannot be fetched or no matching markets are found.
    """
    try:
        print(f"Fetching markets from {exchange.id}...")
        markets = await exchange.fetch_markets()
        print(f"Fetched {len(markets)} markets from {exchange.id}.")
    except Exception as e:
        logging.error(f"Error fetching markets from {exchange.id}: {e}")
        return []

    valid_markets = []
    for market in markets:
        if market.get('quote', '').upper() == quote_currency.upper() and market.get('active', True):
            volume = None
            # Try to get volume from the exchange-specific 'info' field
            if market.get('info') and market['info'].get(volume_field):
                try:
                    volume = float(market['info'][volume_field])
                except (ValueError, TypeError):
                    logging.warning(
                        f"Could not parse volume field '{volume_field}' ({market['info'][volume_field]}) "
                        f"for symbol {market['symbol']} on {exchange.id}. Skipping."
                    )
            # Fallback: Try the standardized 'quoteVolume' if the specific info field isn't good
            elif market.get('quoteVolume') is not None:
                try:
                    volume = float(market['quoteVolume'])
                except (ValueError, TypeError):
                     logging.warning(
                        f"Could not parse 'quoteVolume' ({market['quoteVolume']}) "
                        f"for symbol {market['symbol']} on {exchange.id}. Skipping."
                    )
            # Fallback: Try the standardized 'baseVolume' if 'quoteVolume' isn't good
            elif market.get('baseVolume') is not None and market.get('last') is not None: # Estimate quoteVolume
                try:
                    volume = float(market['baseVolume']) * float(market['last'])
                except (ValueError, TypeError):
                    logging.warning(
                        f"Could not estimate quoteVolume from 'baseVolume' ({market['baseVolume']}) and 'last' ({market['last']}) "
                        f"for symbol {market['symbol']} on {exchange.id}. Skipping."
                    )
            
            if volume is not None and volume > 0: # Ensure positive volume to avoid issues with sorting
                valid_markets.append({'symbol': market['symbol'], 'effectiveVolume': volume})
            elif market.get('quote', '').upper() == quote_currency.upper() and market.get('active', True): # Log if a market matches but has no usable volume
                 logging.debug(f"Market {market['symbol']} on {exchange.id} is active and matches quote currency '{quote_currency}' but has no usable volume data (tried info.{volume_field}, quoteVolume, baseVolume*last). It will not be included in top symbols.")


    if not valid_markets:
        logging.warning(f"No markets found on {exchange.id} for quote currency {quote_currency} with valid volume data.")
        return []

    # Sort by the 'effectiveVolume' we determined
    valid_markets.sort(key=lambda x: x['effectiveVolume'], reverse=True)

    top_symbols = [market['symbol'] for market in valid_markets[:count]]
    
    if len(top_symbols) < count and valid_markets: # Only warn if we found some markets but not enough
        logging.warning(
            f"Found {len(valid_markets)} valid markets for {quote_currency} on {exchange.id}, "
            f"but could only retrieve {len(top_symbols)} symbols (requested {count})."
        )
    elif not valid_markets:
         logging.warning(f"No valid markets with volume data found for {quote_currency} on {exchange.id}. Cannot retrieve top symbols.")


    return top_symbols 