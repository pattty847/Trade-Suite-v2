import pandas as pd
import glob
from datetime import datetime
import ta   # pip install ta
import numpy as np
import os # Added import
import yaml # For YAML configuration
import operator # For mapping operator strings to functions

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

def scan_folder(path="data/cache/*_1d.csv", anchor="2024-01-01"):
    rows = []
    for fp in glob.glob(path, recursive=True):
        # Parse filename for exchange, symbol, and timeframe
        filename = os.path.basename(fp)
        name_part = filename.replace(".csv", "")
        parts = name_part.split('_', 2) # Split into at most 3 parts: EXCHANGE_SYMBOL_TIMEFRAME
        
        exchange_name = "UnknownExchange"
        symbol_name = name_part # Default to whole name part if parsing fails
        timeframe_name = "UnknownTF"

        if len(parts) == 3:
            exchange_name = parts[0]
            symbol_name = parts[1]
            timeframe_name = parts[2]
        elif len(parts) == 2: # Might be SYMBOL_TIMEFRAME or EXCHANGE_SYMBOL (less likely for this project)
            # Assuming EXCHANGE_SYMBOL if only one underscore, and timeframe is implicit from path filter
            exchange_name = parts[0]
            symbol_name = parts[1]
            # timeframe_name could be set based on path filter logic if needed, e.g. if "_1d" is in path
            if "_1d" in name_part: timeframe_name = "1d"
            elif "_1h" in name_part: timeframe_name = "1h" # example for other TFs
        else:
            print(f"Warning: Could not accurately parse filename {filename}. Using defaults.")

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

        latest = df.iloc[-1]
        factors = {
            "exchange": exchange_name,
            "symbol": symbol_name,
            "timeframe": timeframe_name,
            "close": latest.closes,
            "RSI": rsi.iloc[-1],
            "zscore": (latest.closes - sma50.iloc[-1]) / std50.iloc[-1],
            "%B": (latest.closes - bb_upper.iloc[-1]) / std50.iloc[-1],
            "ATRstretch": abs(latest.closes - sma20.iloc[-1]) / atr.iloc[-1],
            "VWAPgap": (latest.closes - vwap.iloc[-1]) / vwap.iloc[-1],
        }
        # OI & CVD need external feeds → merge later
        rows.append(factors)
    return pd.DataFrame(rows)

if __name__ == "__main__":
    df_results = scan_folder()
    scan_config = load_scan_config()

    if df_results.empty:
        print("No symbols found with sufficient data to calculate all indicators.")
    elif not scan_config or 'scans' not in scan_config:
        print("Scan configuration is missing or invalid. Cannot proceed with filtering.")
    else:
        print("\n--- All Processed Symbols & Indicators (before filtering) ---")
        print(df_results.to_markdown())
        print("-----------------------------------------------------------\n")

        any_scan_passed = False
        for scan in scan_config['scans']:
            if not scan.get('enabled', False):
                print(f"Scan '{scan.get('name', 'Unnamed Scan')}' is disabled. Skipping.")
                continue

            scan_name = scan.get('name', 'Unnamed Scan')
            scan_description = scan.get('description', '')
            min_flags = scan.get('min_flags_to_pass', 1)
            conditions = scan.get('conditions', [])

            if not conditions:
                print(f"Scan '{scan_name}' has no conditions defined. Skipping.")
                continue

            # Create a Series to count how many conditions each row (symbol) meets for this scan
            # Ensure we're working with a copy if df_results is going to be reused across scans without modification
            current_scan_df = df_results.copy()
            current_scan_df['flags_met'] = 0 

            print(f"\n--- Evaluating Scan: {scan_name} ---")
            if scan_description:
                print(f"Description: {scan_description}")
            print(f"Minimum flags to pass: {min_flags}")

            for cond in conditions:
                if not cond.get('enabled', False):
                    continue # Skip disabled conditions
                
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
                    # Apply condition and update flags_met count
                    # Ensure data types are compatible for comparison if necessary
                    condition_passed_mask = op_func(current_scan_df[metric].astype(float), float(value))
                    current_scan_df['flags_met'] += condition_passed_mask.astype(int)
                except Exception as e:
                    print(f"Error applying condition {cond} for metric '{metric}' in scan '{scan_name}': {e}. Skipping condition.")

            # Filter DataFrame for symbols that met the minimum number of flags for this scan
            passed_this_scan_df = current_scan_df[current_scan_df['flags_met'] >= min_flags]

            if passed_this_scan_df.empty:
                print(f"No symbols met the criteria for scan: '{scan_name}'.")
            else:
                any_scan_passed = True
                print(f"\nSymbols meeting criteria for scan: '{scan_name}'")
                # Select relevant columns to display (original columns + flags_met for this scan)
                display_columns = [col for col in df_results.columns] + ['flags_met']
                # Ensure 'flags_met' is in passed_this_scan_df before trying to display it
                if 'flags_met' not in passed_this_scan_df.columns:
                     # This case should not happen with current_scan_df['flags_met'] = 0 logic
                     print("Error: 'flags_met' column missing unexpectedly.")
                     print(passed_this_scan_df.head(20).to_markdown())
                else:
                     print(passed_this_scan_df[display_columns].sort_values(by='flags_met', ascending=False).head(20).to_markdown())

        if not any_scan_passed:
            print("\nNo symbols passed any of the enabled scans.")
