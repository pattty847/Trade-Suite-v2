import pandas as pd
import glob
from datetime import datetime
import ta   # pip install ta
import numpy as np
import os # Added import
import yaml # For YAML configuration
import operator # For mapping operator strings to functions
import asyncio # Added import
import logging # Added import for fetching
from tqdm import tqdm # Added import for fetching progress
from typing import List

from trade_suite.data.data_source import Data # Added import
from trade_suite.utils.market_utils import get_top_x_symbols_by_volume # Added import

# --- Operator mapping for dynamic condition evaluation ---
OPERATOR_MAP = {
    '>': operator.gt,
    '<': operator.lt,
    '>=': operator.ge,
    '<=': operator.le,
    '==': operator.eq,
    '!=': operator.ne
}

def load_scan_config(config_path='scan_config.yaml'):
    """Loads the scan configuration from a YAML file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(f"Error: Scan configuration file not found at {config_path}")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration file {config_path}: {e}")
        return None

def anchored_vwap(df, anchor_time):
    anchor = df[df.index >= anchor_time].iloc[0]
    num = (df.loc[anchor_time:, 'closes'] * df.loc[anchor_time:, 'volumes']).cumsum()
    denom = df.loc[anchor_time:, 'volumes'].cumsum()
    return num / denom

async def fetch_data_for_analysis(config: dict, target_timeframe: str) -> List[str] | None:
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
        else:
            logging.error(f"Unknown symbols_source: {symbols_source}. Skipping fetch.")
            # filename_formatted_symbols_result remains None due to early exit logic implies error
            # but to be explicit for this path:
            filename_formatted_symbols_result = None 
            # Jump to finally, then return filename_formatted_symbols_result (which is None)
            raise Exception(f"Unknown symbols_source: {symbols_source}") # To ensure finally runs and then return path is clean

        # Ensure Bitcoin is included
        btc_quote_curr = config.get('top_x_quote_currency', config.get('quote_currency_for_btc', 'USD'))
        btc_pair_ccxt_format = f"BTC/{btc_quote_curr}"
        if symbols_to_fetch is None: # Should only happen if get_top_x_symbols_by_volume somehow returns None
             symbols_to_fetch = []
            
        if btc_pair_ccxt_format not in symbols_to_fetch:
            print(f"Ensuring {btc_pair_ccxt_format} is included in fetch list for BTC relative analysis.")
            symbols_to_fetch.append(btc_pair_ccxt_format)

        if not symbols_to_fetch:
            logging.warning("No symbols determined for fetching (even after BTC check). Skipping candle download.")
            filename_formatted_symbols_result = [] # Successfully determined no symbols to fetch
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
        # If the exception was the one we raised for "Unknown symbols_source", don't re-log.
        if not str(e).startswith("Unknown symbols_source"):
            logging.error(f"An error occurred during data fetching: {e}")
            import traceback
            logging.error(traceback.format_exc())
        # For any exception in the try block, result is None (failure)
        filename_formatted_symbols_result = None
    finally:
        if data_handler and hasattr(data_handler, 'close_all_exchanges'):
            print("Closing exchange connections after fetching...")
            await data_handler.close_all_exchanges()
            print("Exchange connections closed.")
            
    return filename_formatted_symbols_result

def scan_folder(path="data/cache/*.csv", anchor="2024-01-01", target_timeframe="1d", symbols_to_process: List[str] | None = None, data_fetching_config: dict | None = None):
    rows = []
    if symbols_to_process is not None:
        print(f"Scanning for timeframe: {target_timeframe} in path: {path}, focusing on {len(symbols_to_process)} specific symbol(s).")
    else:
        print(f"Scanning for timeframe: {target_timeframe} in path: {path} for all matching files.")
    
    processed_symbols_count = 0

    # --- Load Bitcoin data for relative Z-score calculation ---
    btc_closes_series = None
    btc_target_symbol_name_for_comparison = None # e.g., BTC-USD

    if data_fetching_config and data_fetching_config.get('enabled', False): # Only try if fetching was enabled
        btc_exchange_name = data_fetching_config.get('exchange')
        # Use the same quote currency logic as in fetch_data_for_analysis or a dedicated one
        btc_quote_currency = data_fetching_config.get('top_x_quote_currency', data_fetching_config.get('quote_currency_for_btc', 'USD'))
        
        if btc_exchange_name and btc_quote_currency:
            btc_target_symbol_name_for_comparison = f"BTC-{btc_quote_currency}"
            # Construct path: data/cache/EXCHANGE_BTC-QUOTE_TIMEFRAME.csv
            # Ensure path variable from glob.glob is used for dirname
            # The `path` argument to scan_folder is like "data/cache/*.csv"
            cache_directory = os.path.dirname(path) # "data/cache"
            if not cache_directory: # If path was just "*.csv"
                cache_directory = "." # Assume current directory or adjust as needed

            btc_csv_filename = f"{btc_exchange_name}_{btc_target_symbol_name_for_comparison}_{target_timeframe}.csv"
            btc_csv_full_path = os.path.join(cache_directory, btc_csv_filename)

            if os.path.exists(btc_csv_full_path):
                try:
                    btc_df = pd.read_csv(btc_csv_full_path)
                    if 'dates' in btc_df.columns and 'closes' in btc_df.columns:
                        btc_df['dates'] = pd.to_numeric(btc_df['dates'], errors='coerce')
                        btc_df['dates'] = pd.to_datetime(btc_df['dates'], unit='ms', errors='coerce')
                        btc_df = btc_df.dropna(subset=['dates'])
                        btc_df = btc_df.set_index("dates").sort_index()
                        if not btc_df.empty and len(btc_df) >= 50: # Min length for reliable SMA/STD
                            btc_closes_series = btc_df['closes']
                            print(f"Successfully loaded Bitcoin data for relative analysis from: {btc_csv_full_path}")
                        else:
                            logging.warning(f"Bitcoin data file {btc_csv_full_path} has insufficient data after processing.")
                    else:
                        logging.warning(f"Bitcoin data file {btc_csv_full_path} is missing 'dates' or 'closes' column.")
                except Exception as e:
                    logging.error(f"Error loading or processing Bitcoin data from {btc_csv_full_path}: {e}")
            else:
                logging.warning(f"Bitcoin data file not found at {btc_csv_full_path}. BTC relative Z-score will not be calculated.")
        else:
            logging.warning("Bitcoin exchange or quote currency not found in data_fetching_config. Cannot load BTC data.")
    else:
        logging.info("Data fetching config not provided or not enabled; BTC relative Z-score will not be calculated.")

    for fp in glob.glob(path, recursive=True):
        filename = os.path.basename(fp)
        name_part = filename.replace(".csv", "")
        parts = name_part.split('_', 2) # Expect EXCHANGE_SYMBOL-QUOTE_TIMEFRAME

        exchange_name = "UnknownExchange"
        symbol_name = "UnknownSymbol" # Parsed symbol, e.g., BTC-USD
        file_timeframe = "UnknownTF"

        if len(parts) == 3:
            exchange_name = parts[0]
            symbol_name = parts[1] # This is BASE-QUOTE, e.g., BTC-USD
            file_timeframe = parts[2]
        else:
            # logging.debug(f"Skipping file {filename}: does not match expected format 'EXCHANGE_SYMBOL_TIMEFRAME'.")
            continue # Skip files not matching the strict format

        # Filter by target_timeframe (ensure file's timeframe matches the scan's target)
        if file_timeframe != target_timeframe:
            # logging.debug(f"Skipping {filename}: its timeframe '{file_timeframe}' ('{symbol_name}') does not match target '{target_timeframe}'.")
            continue
        
        # Filter by symbols_to_process if provided
        # symbol_name is parsed in BASE-QUOTE format (e.g., BTC-USD)
        if symbols_to_process is not None and symbol_name not in symbols_to_process:
            # print(f"Skipping {filename}, symbol '{symbol_name}' not in the process list for this run.")
            continue

        print(f"Processing: {filename} (Exchange: {exchange_name}, Symbol: {symbol_name}, Parsed TF: {file_timeframe})")
        processed_symbols_count += 1

        # Read CSV and handle dates more robustly
        df = pd.read_csv(fp)
        if 'dates' not in df.columns:
            print(f"Warning: 'dates' column not found in {fp}. Skipping.")
            continue
        
        df['dates'] = pd.to_numeric(df['dates'], errors='coerce')
        df['dates'] = pd.to_datetime(df['dates'], unit='ms', errors='coerce')
        df = df.dropna(subset=['dates']) # Remove rows where date conversion failed
        df = df.set_index("dates")
        df.sort_index(inplace=True)

        # Check for minimum data length
        min_length = 50  # Based on SMA50
        if len(df) < min_length:
            print(f"Warning: Not enough data in {fp} to calculate all indicators (have {len(df)}, need {min_length}). Skipping.")
            continue

        # --- indicators ---
        rsi = ta.momentum.RSIIndicator(df['closes']).rsi()
        sma20 = df['closes'].rolling(20).mean()
        sma50 = df['closes'].rolling(50).mean()
        std50 = df['closes'].rolling(50).std()
        bb_upper = sma20 + 2*df['closes'].rolling(20).std()
        atr = ta.volatility.AverageTrueRange(df['highs'], df['lows'], df['closes']).average_true_range()
        vwap = anchored_vwap(df, pd.Timestamp(anchor))

        # --- BTC Relative Z-Score ---
        btc_relative_zscore_value = np.nan
        if btc_closes_series is not None and symbol_name != btc_target_symbol_name_for_comparison:
            try:
                # Ensure df.index is datetime before merge if not already
                if not isinstance(df.index, pd.DatetimeIndex):
                     # This should already be handled by earlier date processing for the symbol's df
                     logging.warning(f"Index for {symbol_name} is not DatetimeIndex prior to BTC merge. This is unexpected.")
                
                # Align current symbol's closes with BTC closes on the datetime index
                temp_symbol_closes = df[['closes']].copy() # Operate on a copy
                merged_df = pd.merge(temp_symbol_closes, btc_closes_series.rename('btc_closes'), 
                                     left_index=True, right_index=True, how='inner')

                if not merged_df.empty and len(merged_df) >= 50 and 'closes' in merged_df.columns and 'btc_closes' in merged_df.columns:
                    # Avoid division by zero if btc_closes has zeros, though highly unlikely for BTC price.
                    merged_df['price_ratio'] = merged_df['closes'] / merged_df['btc_closes'].replace(0, np.nan)
                    merged_df.replace([np.inf, -np.inf], np.nan, inplace=True) # Handle potential infinities
                    merged_df.dropna(subset=['price_ratio'], inplace=True) # Remove rows where ratio couldn't be computed

                    if len(merged_df) >= 50: # Check length again after potential drops from NaN ratio
                        ratio_sma = merged_df['price_ratio'].rolling(window=50, min_periods=20).mean()
                        ratio_std = merged_df['price_ratio'].rolling(window=50, min_periods=20).std()
                        
                        latest_ratio = merged_df['price_ratio'].iloc[-1]
                        latest_ratio_sma = ratio_sma.iloc[-1]
                        latest_ratio_std = ratio_std.iloc[-1]

                        if pd.notna(latest_ratio) and pd.notna(latest_ratio_sma) and pd.notna(latest_ratio_std) and latest_ratio_std != 0:
                            btc_relative_zscore_value = (latest_ratio - latest_ratio_sma) / latest_ratio_std
                        # else:
                            # logging.debug(f"Could not calculate BTC_rel_zscore for {symbol_name}: NaN in ratio SMA/STD or STD is zero.")
                    # else:
                        # logging.debug(f"Not enough overlapping data points with BTC for {symbol_name} to calculate ratio Z-score after merge ({len(merged_df)} points).")
                # else:
                    # logging.debug(f"Not enough overlapping data points with BTC for {symbol_name} to calculate ratio Z-score ({len(merged_df)} points), or missing columns.")
            except Exception as e:
                logging.error(f"Error calculating BTC relative Z-score for {symbol_name}: {e}")
                # import traceback
                # logging.error(traceback.format_exc())

        latest = df.iloc[-1]
        factors = {
            "exchange": exchange_name,
            "symbol": symbol_name, # This is BASE-QUOTE
            "timeframe": file_timeframe, # Use the timeframe parsed from the file (which matched target_timeframe)
            "close": latest.closes,
            "RSI": rsi.iloc[-1],
            "zscore": (latest.closes - sma50.iloc[-1]) / std50.iloc[-1],
            "%B": (latest.closes - bb_upper.iloc[-1]) / std50.iloc[-1],
            "ATRstretch": abs(latest.closes - sma20.iloc[-1]) / atr.iloc[-1],
            "VWAPgap": (latest.closes - vwap.iloc[-1]) / vwap.iloc[-1],
            "BTC_rel_zscore": btc_relative_zscore_value, # Add the new metric
        }
        # OI & CVD need external feeds → merge later
        rows.append(factors)
    print(f"Finished scanning. Processed {processed_symbols_count} files for the specified criteria.")
    return pd.DataFrame(rows)

async def main_analysis_workflow(config_path='scan_config.yaml', default_timeframe="1h"):
    """Main workflow to optionally fetch data and then run scans."""
    full_config = load_scan_config(config_path)
    if not full_config:
        print("Failed to load configuration. Exiting.")
        return

    data_fetching_config = full_config.get('data_fetching', {})
    scans_config = full_config.get('scans', [])
    
    # Determine timeframe: config can override default, or use script's default
    # For simplicity, we'll use default_timeframe passed to this function for both fetching and scanning.
    # A more advanced setup could allow separate timeframes in config.
    timeframe_to_process = default_timeframe 
    print(f"Analysis workflow starting for timeframe: {timeframe_to_process}")

    symbols_targeted_by_fetch = None # Initialize
    if data_fetching_config.get('enabled', False):
        symbols_targeted_by_fetch = await fetch_data_for_analysis(data_fetching_config, timeframe_to_process)
        if symbols_targeted_by_fetch is None:
            print("Data fetching was enabled but encountered an issue or returned no symbols. Analysis might be on existing cache data only.")
        elif not symbols_targeted_by_fetch:
             print("Data fetching was enabled but no symbols were identified for fetching (e.g., top_x returned empty). Analysis will be on existing cache data only.")
        else:
            print(f"Data fetching targeted {len(symbols_targeted_by_fetch)} symbol(s). Scan will focus on these if found.")
    else:
        print("Data fetching is disabled. Proceeding directly to analysis of all matching files in cache.")

    # Proceed with scanning the folder
    print(f"Starting folder scan for timeframe: {timeframe_to_process}...")
    df_results = scan_folder(
        target_timeframe=timeframe_to_process, 
        symbols_to_process=symbols_targeted_by_fetch, # Pass the list here
        data_fetching_config=data_fetching_config # Pass the data fetching config
    )

    if df_results.empty:
        print("No symbols found with sufficient data to calculate all indicators for the scan.")
        return # No need to proceed if no data
    
    if not scans_config:
        print("No scans defined in the configuration. Displaying all processed symbols.")
        print("\n--- All Processed Symbols & Indicators (no filtering) ---")
        print(df_results.to_markdown())
        print("-----------------------------------------------------------\n")
        return

    print("\n--- All Processed Symbols & Indicators (before scan filtering) ---")
    print(df_results.to_markdown())
    print("-----------------------------------------------------------\n")

    any_scan_passed = False
    for scan_details in scans_config: # Renamed from scan to scan_details to avoid conflict
        if not scan_details.get('enabled', False):
            print(f"Scan '{scan_details.get('name', 'Unnamed Scan')}' is disabled. Skipping.")
            continue

        scan_name = scan_details.get('name', 'Unnamed Scan')
        scan_description = scan_details.get('description', '')
        min_flags = scan_details.get('min_flags_to_pass', 1)
        conditions = scan_details.get('conditions', [])

        if not conditions:
            print(f"Scan '{scan_name}' has no conditions defined. Skipping.")
            continue

        current_scan_df = df_results.copy()
        current_scan_df['flags_met'] = 0 

        print(f"\n--- Evaluating Scan: {scan_name} ---")
        if scan_description:
            print(f"Description: {scan_description}")
        print(f"Minimum flags to pass: {min_flags}")

        for cond in conditions:
            if not cond.get('enabled', False):
                continue 
            
            metric = cond.get('metric')
            op_str = cond.get('operator')
            value = cond.get('value')

            if not all([metric, op_str, value is not None]):
                print(f"Warning: Incomplete condition in scan '{scan_name}': {cond}. Skipping condition.")
                continue
            
            if metric not in current_scan_df.columns:
                print(f"Warning: Metric '{metric}' not found in DataFrame columns for scan '{scan_name}'. Skipping condition.")
                continue
            
            op_func = OPERATOR_MAP.get(op_str)
            if not op_func:
                print(f"Warning: Invalid operator '{op_str}' in scan '{scan_name}'. Skipping condition.")
                continue
            
            try:
                condition_passed_mask = op_func(current_scan_df[metric].astype(float), float(value))
                current_scan_df['flags_met'] += condition_passed_mask.astype(int)
            except Exception as e:
                print(f"Error applying condition {cond} for metric '{metric}' in scan '{scan_name}': {e}. Skipping condition.")

        passed_this_scan_df = current_scan_df[current_scan_df['flags_met'] >= min_flags]

        if passed_this_scan_df.empty:
            print(f"No symbols met the criteria for scan: '{scan_name}'.")
        else:
            any_scan_passed = True
            print(f"\nSymbols meeting criteria for scan: '{scan_name}'")
            display_columns = [col for col in df_results.columns if col != 'flags_met'] + ['flags_met'] # Ensure flags_met is last
            print(passed_this_scan_df[display_columns].sort_values(by='flags_met', ascending=False).head(20).to_markdown())

    if not any_scan_passed:
        print("\nNo symbols passed any of the enabled scans.")

if __name__ == "__main__":
    # Setup basic logging to see the output from traceback and fetching
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

    # --- Configuration for which timeframe to scan --- 
    timeframe_to_analyze = "5m"  # This will be used for both fetching and scanning
    
    # Set the event loop policy for Windows if applicable
    if os.name == 'nt': # Check for Windows NT (covers modern Windows)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main_analysis_workflow(default_timeframe=timeframe_to_analyze))
