import asyncio
import sys
import logging # Added for detailed error logging
import traceback # Added for detailed error logging
from dotenv import load_dotenv
from tqdm import tqdm # Import tqdm

from trade_suite.utils.market_utils import get_top_x_symbols_by_volume # Import the new function

load_dotenv(override=True)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from trade_suite.data.data_source import Data

async def main():
    # Initialize the Data class for Coinbase, forcing public mode
    data_handler = Data(influx=None, emitter=None, exchanges=['coinbase'], force_public=True)
    
    try:
        print("Attempting to load exchanges...")
        await data_handler.load_exchanges()
        print("Exchanges loaded successfully.")

        # Get the Coinbase exchange object
        coinbase_exchange = data_handler.exchange_list['coinbase']

        # Get the top 200 symbols using the utility function
        print("Attempting to fetch top X symbols from Coinbase by USD volume...")
        top_20_symbols = await get_top_x_symbols_by_volume(
            exchange=coinbase_exchange, 
            quote_currency='USD', 
            count=20,
            volume_field='volume_24h' # Specific to Coinbase for USD volume
        )

        if not top_20_symbols:
            print("Could not retrieve top 200 symbols. There might be an issue with market data or filtering. Exiting.")
            return
        elif len(top_20_symbols) < 200:
            print(f"Warning: Fetched only {len(top_20_symbols)} symbols, less than the desired 200.")


        # Define the symbols, timeframes, and the start date for fetching data
        symbols_to_fetch = top_20_symbols
        timeframes_to_fetch = ['1h'] # Changed to 1m
        since_date = '2024-01-01T00:00:00Z'

        print(f"Fetching 1m candles for top {len(symbols_to_fetch)} symbols on Coinbase (by 24h USD volume)")
        print(f"Timeframes: {timeframes_to_fetch}, Since: {since_date}")

        # Fetch the candles. The Data class will handle saving them to CSV in 'data/cache/'
        # Wrap symbols_to_fetch with tqdm for a progress bar
        await data_handler.fetch_candles(
            exchanges=['coinbase'],
            symbols=tqdm(symbols_to_fetch, desc="Fetching candles per symbol"),
            since=since_date,
            timeframes=timeframes_to_fetch,
            write_to_db=False  # Set to False as we are not using InfluxDB here
        )

        print("\nCandle data fetching complete.")
        print(f"CSV files should be saved in the '{data_handler.cache_dir}' directory.")

    except IndexError as e:
        logging.error(f"IndexError occurred in download_candles.py: {e}")
        logging.error(traceback.format_exc())
    except Exception as e:
        logging.error(f"An unexpected error occurred in download_candles.py: {e}")
        logging.error(traceback.format_exc())
    finally:
        if hasattr(data_handler, 'close_all_exchanges'):
            print("Closing exchange connections...")
            await data_handler.close_all_exchanges()
            print("Exchange connections closed.")

if __name__ == "__main__":
    # Setup basic logging to see the output from traceback
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
    asyncio.run(main()) 