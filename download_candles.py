import asyncio
import sys
import logging # Added for detailed error logging
import traceback # Added for detailed error logging
from dotenv import load_dotenv

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

        # Define the symbols, timeframes, and the start date for fetching data
        
        # 25 high-volume speculative coins on Coinbase
        # IMPORTANT: Symbols should be in BASE/QUOTE format, e.g., 'PEPE/USD'
        # Assuming USD as the quote currency. Adjust if needed.
        shitcoins_base = [
            "PEPE", "BONK", "DOGE", "WIF", "SHIB", "SUI", "ARB", "OP", 
            "WLD", "SEI", "JASMY", "RENDER", "NEAR", "TIA", "XCN", "ENA"
        ]
        blue_chips_base = ["BTC", "ETH", "SOL", "ADA", "XRP"]

        # Assuming USD as the quote currency
        quote_currency = "USD"
        symbols_to_fetch = [f"{coin}/{quote_currency}" for coin in shitcoins_base + blue_chips_base]

        timeframes_to_fetch = ['1d']
        since_date = '2024-01-01T00:00:00Z' # Adjusted to a more recent year for potentially available data

        print(f"Fetching candles for symbols: {symbols_to_fetch} on Coinbase")
        print(f"Timeframes: {timeframes_to_fetch}, Since: {since_date}")

        # Fetch the candles. The Data class will handle saving them to CSV in 'data/cache/'
        await data_handler.fetch_candles(
            exchanges=['coinbase'],
            symbols=symbols_to_fetch,
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