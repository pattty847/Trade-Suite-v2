import sys
import os

# Adjust sys.path to include the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now that sys.path is adjusted, we can import from the new location
from scripts.ohlcv_downloader.downloader import run_download_process

if __name__ == "__main__":
    # --- Begin User-defined parameters ---
    # Set use_top_symbols to True to fetch top symbols, or False to use your manually provided symbol list.
    use_top_symbols = False
    exchanges_to_use = ['coinbase']
    
    if use_top_symbols:
        top_symbols_config = {
            'exchange_name': 'coinbase', 
            'quote_currency': 'USD', 
            'count': 20,  # Fetch top 20 symbols
            'volume_field': 'volume_24h'  
        }
        symbols_to_fetch = []  # This will be ignored when top_symbols_config is used.
    else:
        top_symbols_config = None
        symbols_to_fetch = ["PEPE/USD", "BTC/USD"]
    
    timeframes_to_use = ['1d']
    since_date_to_use = '2024-07-01T00:00:00Z'
    # --- End User-defined parameters ---

    print(f"Starting OHLCV download for exchanges: {exchanges_to_use}")
    if top_symbols_config:
        print(f"Using top symbols config mode: Fetching top {top_symbols_config['count']} symbols from {top_symbols_config['exchange_name']}.\nManual symbols will be ignored.")
    else:
        print(f"Using predefined symbols: {symbols_to_fetch}")
    print(f"Timeframes: {timeframes_to_use}, Since: {since_date_to_use}")

    run_download_process(
        exchanges=exchanges_to_use,
        symbols=symbols_to_fetch,
        timeframes=timeframes_to_use,
        since=since_date_to_use,
        get_top_symbols_config=top_symbols_config 
    )

    print("\nScript finished.") 