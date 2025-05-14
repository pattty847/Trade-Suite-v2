import asyncio
import logging
from tqdm import tqdm
from typing import List

from trade_suite.data.data_source import Data
from trade_suite.utils.market_utils import get_top_x_symbols_by_volume

async def fetch_data_for_analysis(config: dict, target_timeframe: str, full_config: dict | None = None) -> List[str] | None:
    """Fetches or updates candle data based on the provided configuration.
    Returns a list of symbol names (in filename format, e.g., BASE-QUOTE) that were targeted for fetching, 
    an empty list if no symbols were fetched, or None if fetching was disabled or a critical error occurred.
    """
    if not config.get('enabled', False):
        print("Data fetching is disabled in the configuration.")
        return None

    exchange_name = config.get('exchange')
    since_date = config.get('since_date')
    symbols_source = config.get('symbols_source')

    if not all([exchange_name, since_date, symbols_source]):
        logging.error("Data fetching configuration is incomplete (exchange, since_date, symbols_source). Skipping fetch.")
        return None

    print(f"Starting data fetch/update for {exchange_name}, timeframe: {target_timeframe}, since: {since_date}")

    data_handler = None
    # Initialize to None; will be set to list on success, or remain None on error, or empty list if no symbols.
    filename_formatted_symbols_result: List[str] | None = None 
    
    try:
        data_handler = Data(influx=None, emitter=None, exchanges=[exchange_name], force_public=True)
        await data_handler.load_exchanges()
        exchange_object = data_handler.exchange_list[exchange_name]

        symbols_to_fetch = []
        if symbols_source == "top_x":
            count = config.get('top_x_count', 20)
            quote_currency = config.get('top_x_quote_currency', 'USD')
            volume_field = config.get('top_x_volume_field', 'volume_24h')
            print(f"Fetching top {count} symbols from {exchange_name} by {quote_currency} volume (field: {volume_field})...")
            symbols_to_fetch = await get_top_x_symbols_by_volume(
                exchange=exchange_object,
                quote_currency=quote_currency,
                count=count,
                volume_field=volume_field
            )
        elif symbols_source == "explicit_list":
            symbols_to_fetch = config.get('symbols_list', [])
            print(f"Fetching specified list of symbols: {symbols_to_fetch}")
        elif symbols_source.startswith("group:") and full_config:
            group_name = symbols_source.split(":", 1)[1]
            asset_groups = full_config.get('asset_groups', {})
            if group_name in asset_groups:
                symbols_to_fetch = asset_groups[group_name]
                print(f"Fetching symbols from predefined group '{group_name}': {symbols_to_fetch}")
            else:
                logging.error(f"Asset group '{group_name}' not found in configuration. Skipping fetch.")
                filename_formatted_symbols_result = None
                raise Exception(f"Asset group '{group_name}' not found")
        else:
            logging.error(f"Unknown or misconfigured symbols_source: {symbols_source}. Check config or group syntax ('group:name'). Skipping fetch.")
            filename_formatted_symbols_result = None 
            raise Exception(f"Unknown symbols_source: {symbols_source}")

        btc_quote_curr = config.get('top_x_quote_currency', config.get('quote_currency_for_btc', 'USD'))
        btc_pair_ccxt_format = f"BTC/{btc_quote_curr}"
        if symbols_to_fetch is None: 
             symbols_to_fetch = []
            
        if btc_pair_ccxt_format not in symbols_to_fetch:
            print(f"Ensuring {btc_pair_ccxt_format} is included in fetch list for BTC relative analysis.")
            symbols_to_fetch.append(btc_pair_ccxt_format)

        if not symbols_to_fetch:
            logging.warning("No symbols determined for fetching (even after BTC check). Skipping candle download.")
            filename_formatted_symbols_result = []
        else:
            print(f"Proceeding to fetch/update candles for {len(symbols_to_fetch)} symbols: {symbols_to_fetch}")
            await data_handler.fetch_candles(
                exchanges=[exchange_name],
                symbols=tqdm(symbols_to_fetch, desc=f"Fetching {target_timeframe} candles"),
                since=since_date,
                timeframes=[target_timeframe],
                write_to_db=False 
            )
            print("Candle data fetching/updating complete.")
            filename_formatted_symbols_result = [s.replace('/', '-') for s in symbols_to_fetch]

    except Exception as e:
        if not str(e).startswith("Unknown symbols_source"):
            logging.error(f"An error occurred during data fetching: {e}")
            import traceback
            logging.error(traceback.format_exc())
        filename_formatted_symbols_result = None
    finally:
        if data_handler and hasattr(data_handler, 'close_all_exchanges'):
            print("Closing exchange connections after fetching...")
            await data_handler.close_all_exchanges()
            print("Exchange connections closed.")
            
    return filename_formatted_symbols_result 