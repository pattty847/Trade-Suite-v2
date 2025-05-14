import pandas as pd
import glob
import os
import logging
import numpy as np
from typing import List, Dict, Any

from .indicator_calculator import calculate_technical_indicators

def scan_data_files(
    path_pattern: str = "data/cache/*.csv", 
    anchor_str_for_vwap: str = "2024-01-01", 
    target_timeframe: str = "1d", 
    symbols_to_process: List[str] | None = None, 
    data_fetching_config: dict | None = None,
    max_rows_to_load: int = 1000
) -> pd.DataFrame:
    """Scans data files, calculates indicators, and returns a DataFrame of results."""
    rows = []
    if symbols_to_process is not None:
        print(f"Scanning for timeframe: {target_timeframe} in path: {path_pattern}, focusing on {len(symbols_to_process)} specific symbol(s).")
    else:
        print(f"Scanning for timeframe: {target_timeframe} in path: {path_pattern} for all matching files.")
    
    processed_symbols_count = 0
    anchor_timestamp_for_vwap = pd.Timestamp(anchor_str_for_vwap) # Convert anchor string to Timestamp once

    # --- Load Bitcoin data for relative Z-score calculation ---
    btc_closes_series = None
    btc_target_symbol_name_for_comparison = None

    if data_fetching_config and data_fetching_config.get('enabled', False):
        btc_exchange_name = data_fetching_config.get('exchange')
        btc_quote_currency = data_fetching_config.get('top_x_quote_currency', data_fetching_config.get('quote_currency_for_btc', 'USD'))
        
        if btc_exchange_name and btc_quote_currency:
            btc_target_symbol_name_for_comparison = f"BTC-{btc_quote_currency}"
            cache_directory = os.path.dirname(path_pattern)
            if not cache_directory: cache_directory = "."

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
                        if not btc_df.empty and len(btc_df) >= 50:
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

    for fp in glob.glob(path_pattern, recursive=True):
        filename = os.path.basename(fp)
        name_part = filename.replace(".csv", "")
        parts = name_part.split('_', 2)

        exchange_name, symbol_name, file_timeframe = "UnknownExchange", "UnknownSymbol", "UnknownTF"

        if len(parts) == 3:
            exchange_name, symbol_name, file_timeframe = parts[0], parts[1], parts[2]
        else:
            continue

        if file_timeframe != target_timeframe:
            continue
        
        if symbols_to_process is not None and symbol_name not in symbols_to_process:
            continue

        print(f"Processing: {filename} (Exchange: {exchange_name}, Symbol: {symbol_name}, Parsed TF: {file_timeframe})")
        
        df = pd.read_csv(fp)
        if 'dates' not in df.columns:
            print(f"Warning: 'dates' column not found in {fp}. Skipping.")
            continue
        
        # --- Apply tail loading --- 
        if len(df) > max_rows_to_load:
            df = df.tail(max_rows_to_load).copy() # Use copy to avoid SettingWithCopyWarning later if modifying df
        # ------------------------

        df['dates'] = pd.to_numeric(df['dates'], errors='coerce')
        df['dates'] = pd.to_datetime(df['dates'], unit='ms', errors='coerce')
        df = df.dropna(subset=['dates'])
        df = df.set_index("dates").sort_index()

        min_length = 50
        min_length_adx_data_check = 28 # For data presence for ADX input columns
        effective_min_length = max(min_length, min_length_adx_data_check if all(col in df.columns for col in ['highs', 'lows', 'closes']) else min_length)

        if len(df) < effective_min_length:
            print(f"Warning: Not enough data in {fp} to calculate all indicators (have {len(df)}, need {effective_min_length}). Skipping.")
            continue

        # Call the imported calculator function
        factors = calculate_technical_indicators(
            df=df, 
            anchor_timestamp_for_vwap=anchor_timestamp_for_vwap, 
            current_symbol_name=symbol_name,
            btc_closes_series=btc_closes_series, 
            btc_target_symbol_name_for_comparison=btc_target_symbol_name_for_comparison
        )

        # Add metadata that was previously part of the factors dict construction
        full_factors_row = {
            "exchange": exchange_name,
            "symbol": symbol_name,
            "timeframe": file_timeframe,
            **factors # Unpack the calculated indicators
        }
        rows.append(full_factors_row)
        processed_symbols_count += 1

    print(f"Finished scanning. Processed {processed_symbols_count} files for the specified criteria.")
    return pd.DataFrame(rows) 