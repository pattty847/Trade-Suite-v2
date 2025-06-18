import asyncio
import logging
import traceback
from tqdm import tqdm
from trade_suite.data.data_source import Data
from trade_suite.utils.market_utils import get_top_x_symbols_by_volume

class OhlcvDownloader:
    def __init__(self, force_public=True):
        self.data_handler = Data(influx=None, emitter=None, force_public=force_public)
        self.logger = logging.getLogger(__name__)

    async def load_exchanges(self, exchanges):
        self.data_handler.exchanges = exchanges
        self.logger.info(f"Attempting to load exchanges: {exchanges}...")
        await self.data_handler.load_exchanges(exchanges=exchanges)
        self.logger.info("Exchanges loaded successfully.")

    async def get_top_symbols(self, exchange_name, quote_currency, count, volume_field='volume_24h'):
        if exchange_name not in self.data_handler.exchange_list:
            self.logger.error(f"Exchange {exchange_name} not loaded.")
            return []
        
        exchange_obj = self.data_handler.exchange_list[exchange_name]
        self.logger.info(f"Attempting to fetch top {count} symbols from {exchange_name} by {quote_currency} volume...")
        
        top_symbols = await get_top_x_symbols_by_volume(
            exchange=exchange_obj,
            quote_currency=quote_currency,
            count=count,
            volume_field=volume_field
        )

        if not top_symbols:
            self.logger.warning(f"Could not retrieve top {count} symbols from {exchange_name}.")
        elif len(top_symbols) < count:
            self.logger.warning(f"Fetched only {len(top_symbols)} symbols, less than the desired {count}.")
        
        return top_symbols

    async def fetch_ohlcv_data(self, exchanges_to_fetch_from, symbols_to_fetch, timeframes_to_fetch, since_date, write_to_db=False):
        self.logger.info(f"Fetching candles for {len(symbols_to_fetch)} symbols on {exchanges_to_fetch_from}")
        self.logger.info(f"Timeframes: {timeframes_to_fetch}, Since: {since_date}")

        await self.data_handler.fetch_candles(
            exchanges=exchanges_to_fetch_from,
            symbols=tqdm(symbols_to_fetch, desc="Fetching candles per symbol"),
            since=since_date,
            timeframes=timeframes_to_fetch,
            write_to_db=write_to_db
        )
        self.logger.info("\nCandle data fetching complete.")
        self.logger.info(f"CSV files should be saved in the '{self.data_handler.cache_store.cache_dir}' directory.")

    async def close_connections(self):
        if hasattr(self.data_handler, 'close_all_exchanges'):
            self.logger.info("Closing exchange connections...")
            await self.data_handler.close_all_exchanges()
            self.logger.info("Exchange connections closed.")

async def download_ohlcv(exchanges, symbols, timeframes, since, get_top_symbols_config=None, downloader_instance=None):
    """
    High-level function to download OHLCV data.

    Args:
        exchanges (list): List of exchange names (e.g., ['coinbase']).
        symbols (list): List of symbols to fetch (e.g., ["BTC/USD", "ETH/USD"]). 
                        If get_top_symbols_config is provided, this can be an empty list 
                        or will be appended to the top symbols found.
        timeframes (list): List of timeframes (e.g., ['1h', '4h']).
        since (str): Start date for fetching data (e.g., '2023-01-01T00:00:00Z').
        get_top_symbols_config (dict, optional): Configuration to fetch top symbols.
            Example: {
                'exchange_name': 'coinbase', 
                'quote_currency': 'USD', 
                'count': 20,
                'volume_field': 'volume_24h' # Specific to Coinbase for USD volume
            }
    """
    # Use provided downloader_instance or create a new one
    downloader = downloader_instance if downloader_instance else OhlcvDownloader()

    try:
        # Determine all unique exchanges needed for loading
        all_exchanges_to_load = set(exchanges)
        if get_top_symbols_config and 'exchange_name' in get_top_symbols_config:
            all_exchanges_to_load.add(get_top_symbols_config['exchange_name'])
        
        await downloader.load_exchanges(list(all_exchanges_to_load))
        
        if get_top_symbols_config:
            logging.info("Using top symbols config mode. Manual symbols will be ignored.")
            fetched_symbols = await downloader.get_top_symbols(
                exchange_name=get_top_symbols_config['exchange_name'],
                quote_currency=get_top_symbols_config['quote_currency'],
                count=get_top_symbols_config['count'],
                volume_field=get_top_symbols_config.get('volume_field', 'volume_24h')
            )
        else:
            fetched_symbols = list(symbols)  # Use manually provided symbols
        
        if not fetched_symbols:
            logging.error("No symbols to fetch. Exiting.")
            return
        
        await downloader.fetch_ohlcv_data(
            exchanges_to_fetch_from=exchanges,  # Fetch OHLCV from the exchanges specified in the 'exchanges' param
            symbols_to_fetch=fetched_symbols,
            timeframes_to_fetch=timeframes,
            since_date=since
        )
    except Exception as e:
        logging.error(f"An unexpected error occurred in OhlcvDownloader: {e}")
        logging.error(traceback.format_exc())
    finally:
        # Connection closing will be handled by the calling function (run_download_process)
        # if downloader_instance is None: # Only close if this function created the instance
        #     await downloader.close_connections()
        pass

def run_download_process(exchanges, symbols, timeframes, since, get_top_symbols_config=None):
    """
    Sets up the environment, runs the OHLCV download process, and handles cleanup.
    """
    import sys # Moved import here
    from dotenv import load_dotenv # Moved import here
    
    load_dotenv(override=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    downloader = OhlcvDownloader() # Create instance here to manage its lifecycle

    async def main_async_logic():
        try:
            await download_ohlcv(
                exchanges, 
                symbols, 
                timeframes, 
                since, 
                get_top_symbols_config,
                downloader_instance=downloader # Pass the instance
            )
        finally:
            await downloader.close_connections() # Ensure connections are closed

    asyncio.run(main_async_logic())

if __name__ == '__main__':
    # Example usage (optional, for testing the downloader directly)
    # logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
    
    # async def run_example():
    #     # Configuration for fetching top symbols
    #     top_symbols_config = {
    #         'exchange_name': 'coinbase',
    #         'quote_currency': 'USD',
    #         'count': 5, # Fetch top 5 symbols
    #         'volume_field': 'volume_24h'
    #     }

    #     await download_ohlcv(
    #         exchanges=['coinbase'], # Exchange to download OHLCV data from
    #         symbols=["PEPE/USD"], # Manually specified symbols
    #         timeframes=['1h'],
    #         since='2024-01-01T00:00:00Z',
    #         get_top_symbols_config=top_symbols_config # Enable fetching top symbols
    #     )

    # To run this example:
    # if sys.platform == "win32":
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # asyncio.run(run_example())
    
    # Example of using the new run_download_process function
    print("Running example using run_download_process...")
    example_top_symbols_config = {
        'exchange_name': 'coinbase',
        'quote_currency': 'USD',
        'count': 2, 
        'volume_field': 'volume_24h'
    }
    run_download_process(
        exchanges=['coinbase'],
        symbols=["DOGE/USD"], 
        timeframes=['5m'],
        since='2024-03-01T00:00:00Z',
        get_top_symbols_config=example_top_symbols_config
    )
    print("Example finished.")
    pass 