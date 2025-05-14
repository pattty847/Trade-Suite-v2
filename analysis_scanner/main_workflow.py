import asyncio
import os
import logging
import pandas as pd # Added for DataFrame type hint and empty check
import numpy as np
import os # Ensure os is imported

from .config_utils import load_scan_config, OPERATOR_MAP
from .data_handler import fetch_data_for_analysis
from .file_scanner import scan_data_files
from .output_handler import write_output # Added import

# Define path for storing last results - TEMPLATE now
LAST_RESULTS_PATH_TEMPLATE = 'results_last_{timeframe}.parquet'

async def run_analysis_workflow(config_path='scan_config.yaml', default_timeframe="1h"):
    """Main workflow to optionally fetch data and then run scans."""
    full_config = load_scan_config(config_path)
    if not full_config:
        print("Failed to load configuration. Exiting.")
        return

    timeframe_to_process = default_timeframe # Use the resolved timeframe
    last_results_file = LAST_RESULTS_PATH_TEMPLATE.format(timeframe=timeframe_to_process)
    print(f"Using last results file: {last_results_file}")

    # --- Load previous results for delta calculation ---
    df_last = None
    if os.path.exists(last_results_file): # Use timeframe-specific file
        try:
            df_last = pd.read_parquet(last_results_file) # Use timeframe-specific file
            # Ensure key columns exist for indexing and comparison
            key_cols = ['exchange', 'symbol', 'timeframe']
            if not all(col in df_last.columns for col in key_cols):
                 print(f"Warning: {last_results_file} missing key columns ({key_cols}). Skipping delta calculation.")
                 df_last = None
            else:
                 # Set index for easy alignment later
                 df_last = df_last.set_index(key_cols)
        except Exception as e:
            print(f"Warning: Could not load or process {last_results_file}: {e}. Skipping delta calculation.")
            df_last = None
    # --------------------------------------------------

    data_fetching_config = full_config.get('data_fetching', {})
    scans_config = full_config.get('scans', [])
    output_configs = full_config.get('output', []) # Load output configurations
    
    # Default to markdown to stdout if no output config is provided, to maintain old behavior.
    if not output_configs:
        output_configs = [{'format': 'markdown', 'path': None}]
        print("No output configuration found in scan_config.yaml. Defaulting to Markdown to stdout.")

    print(f"Analysis workflow starting for timeframe: {timeframe_to_process}")

    # Default path pattern for scan_data_files, can be overridden by config if desired in future
    # For now, using the one from the original scan_folder default.
    # It might be better to make this configurable via scan_config.yaml too.
    path_pattern_for_scan = full_config.get('scanner_options', {}).get('path_pattern', "data/cache/*.csv")
    anchor_for_vwap = full_config.get('scanner_options', {}).get('anchor_for_vwap', "2024-01-01")
    # Read max_rows_to_load from config, default to 1000
    max_rows_to_load = full_config.get('scanner_options', {}).get('max_rows_to_load', 1000)


    symbols_targeted_by_fetch = None
    if data_fetching_config.get('enabled', False):
        # Pass full_config here for asset groups later
        symbols_targeted_by_fetch = await fetch_data_for_analysis(data_fetching_config, timeframe_to_process, full_config)
        if symbols_targeted_by_fetch is None:
            print("Data fetching was enabled but encountered an issue or returned no symbols. Analysis might be on existing cache data only.")
        elif not symbols_targeted_by_fetch:
             print("Data fetching was enabled but no symbols were identified for fetching. Analysis will be on existing cache data only.")
        else:
            print(f"Data fetching targeted {len(symbols_targeted_by_fetch)} symbol(s). Scan will focus on these if found.")
    else:
        print("Data fetching is disabled. Proceeding directly to analysis of all matching files in cache.")

    print(f"Starting folder scan for timeframe: {timeframe_to_process}...")
    df_results = scan_data_files(
        path_pattern=path_pattern_for_scan,
        anchor_str_for_vwap=anchor_for_vwap,
        target_timeframe=timeframe_to_process, 
        symbols_to_process=symbols_targeted_by_fetch,
        data_fetching_config=data_fetching_config,
        max_rows_to_load=max_rows_to_load # Pass the value here
    )

    if df_results.empty:
        print("No symbols found with sufficient data to calculate all indicators for the scan.")
        # Attempt to save an empty DataFrame to potentially clear the last state if needed? Or just return.
        # Let's just return for now. If no symbols are processed, no deltas can be calculated anyway.
        return
    
    # --- Calculate Deltas ---
    # Define columns for which to calculate deltas
    delta_metric_cols = [
        'RSI', 'zscore', 'RVOL', 'VWAPgap', 'VWAPgap_daily', 
        'BBW', 'BTC_rel_zscore', 'VolumeZScore', '%B', 'ATRstretch', 'ADX'
    ]
    # Ensure results DF has the key index columns before proceeding
    key_cols = ['exchange', 'symbol', 'timeframe']
    if all(col in df_results.columns for col in key_cols):
        df_results = df_results.set_index(key_cols)

        if df_last is not None:
            print("Calculating deltas from previous run...")
            # Find columns that actually exist in both current and last results
            valid_delta_cols = [col for col in delta_metric_cols if col in df_results.columns and col in df_last.columns]
            
            # Align indexes (use left join to keep all current results)
            df_results, df_last_aligned = df_results.align(df_last, join='left', axis=0) 

            # DEBUG: Print some values for comparison
            if valid_delta_cols:
                # Find a common index for debugging
                common_indices = df_results.index.intersection(df_last_aligned.index)
                if not common_indices.empty:
                    debug_idx = common_indices[0] # Take the first common index
                    debug_col = valid_delta_cols[0] # Take the first valid metric for delta
                    current_val = df_results.loc[debug_idx, debug_col]
                    last_val = df_last_aligned.loc[debug_idx, debug_col]
                    print(f"DEBUG: For index {debug_idx}, metric {debug_col}:")
                    print(f"DEBUG:   Current value: {current_val}")
                    print(f"DEBUG:   Last value: {last_val}")
                    if pd.isna(current_val) or pd.isna(last_val):
                        print(f"DEBUG:   One or both values are NaN. Delta will be NaN.")
                    elif current_val == last_val:
                        print(f"DEBUG:   Values are identical. Delta will be 0.")
                    else:
                        print(f"DEBUG:   Values differ. Delta should be non-zero: {current_val - last_val}")
                else:
                    print("DEBUG: No common indices found between current and last results for detailed comparison. Deltas might be NaN or 0 if new data only.")


            for col in valid_delta_cols:
                 # Ensure columns are numeric before subtraction, coercing errors to NaN
                 current_col_numeric = pd.to_numeric(df_results[col], errors='coerce')
                 last_col_numeric = pd.to_numeric(df_last_aligned[col], errors='coerce')
                 df_results[f'delta_{col}'] = current_col_numeric - last_col_numeric
            print("Delta calculation complete.")
        else:
            print("Previous results not found or invalid. Skipping delta calculation for this run.")
            # Add empty delta columns for consistent structure? Optional. For now, they just won't exist.

        # --- Save current results for the next run's delta calculation ---
        # Select only columns needed for next time's delta calculation + index cols
        cols_to_save = valid_delta_cols if df_last is not None else [col for col in delta_metric_cols if col in df_results.columns] # Use computed valid cols or check current cols
        
        # Reset index to save key cols as regular columns
        df_to_save = df_results[cols_to_save].reset_index() 
        try:
            df_to_save.to_parquet(last_results_file, index=False) # Use timeframe-specific file
            print(f"Current results saved to {last_results_file} for next run.")
        except Exception as e:
            print(f"Warning: Could not save results to {last_results_file}: {e}")
        # -----------------------------------------------------------------

        # Reset index for subsequent processing/printing
        df_results = df_results.reset_index() 
    else:
        print("Warning: Key columns missing in df_results. Skipping delta calculation and saving.")
    # --- End Delta Calculation & Saving ---

    # --- Scan Evaluation (existing logic) ---
    if not scans_config:
        print("No scans defined in the configuration. Displaying all processed symbols.")
        # Check if df_results is a DataFrame
        if isinstance(df_results, pd.DataFrame):
            display_cols = sorted([col for col in df_results.columns if col not in key_cols])
            # Use new output handler
            for out_conf in output_configs:
                write_output(df_results[key_cols + display_cols], out_conf, title="All Processed Symbols & Indicators (no filtering)")
        else:
            # Fallback for non-DataFrame results (should ideally not happen with current logic)
            print("Non-DataFrame results, printing directly:")
            print(df_results)
        print("-----------------------------------------------------------\n")
        return

    # Print all processed symbols before scan filtering using the new handler
    if isinstance(df_results, pd.DataFrame):
        display_cols_all = sorted([col for col in df_results.columns if col not in key_cols])
        df_to_output_all = df_results[key_cols + display_cols_all]
        for out_conf in output_configs:
            # Potentially use a different title or path suffix for this "all_processed" output
            # For now, let's give it a distinct title.
            # We might want specific output configs for "all_processed" vs "scan_results" later.
            conf_all = out_conf.copy() # Avoid modifying original config if we add suffixes
            if conf_all.get('path'):
                 base, ext = os.path.splitext(conf_all['path'])
                 conf_all['path'] = f"{base}_all_processed{ext}"
            write_output(df_to_output_all, conf_all, title="All Processed Symbols & Indicators (before scan filtering)")
    else:
        print("Non-DataFrame results for 'All Processed Symbols', printing directly:")
        print(df_results)
    # Removed the direct print and horizontal line as write_output handles it for text/md to stdout

    any_scan_passed = False
    for scan_details in scans_config:
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

        # Use a copy for evaluation, keeping original df_results intact
        current_scan_df = df_results.copy() 
        current_scan_df['flags_met'] = 0 

        print(f"\n--- Evaluating Scan: {scan_name} ---")
        if scan_description:
            print(f"Description: {scan_description}")
        print(f"Minimum flags to pass: {min_flags}")

        # Apply conditions to the copy
        for cond in conditions:
            if not cond.get('enabled', False):
                continue 
            
            metric = cond.get('metric')
            op_str = cond.get('operator')
            value = cond.get('value')

            if not all([metric, op_str, value is not None]):
                print(f"Warning: Incomplete condition in scan '{scan_name}': {cond}. Skipping condition.")
                continue
            
            # Check if metric exists in the copied DataFrame
            if metric not in current_scan_df.columns:
                print(f"Warning: Metric '{metric}' not found in DataFrame columns for scan '{scan_name}'. Skipping condition.")
                continue
            
            op_func = OPERATOR_MAP.get(op_str)
            if not op_func:
                print(f"Warning: Invalid operator '{op_str}' in scan '{scan_name}'. Skipping condition.")
                continue
            
            try:
                # Ensure metric column is numeric before comparison
                numeric_metric_series = pd.to_numeric(current_scan_df[metric], errors='coerce')
                # Ensure value is float for comparison
                comparison_value = float(value) 
                condition_passed_mask = op_func(numeric_metric_series, comparison_value)
                # Add to flags_met only where condition_passed_mask is True and the metric was not NaN
                # Combine masks using logical AND (&)
                valid_comparison_mask = pd.notna(numeric_metric_series) & condition_passed_mask
                current_scan_df['flags_met'] += np.where(valid_comparison_mask, 1, 0)

            except Exception as e:
                print(f"Error applying condition {cond} for metric '{metric}' in scan '{scan_name}': {e}. Skipping condition.")

        # Filter the copied DataFrame based on flags_met
        passed_this_scan_df = current_scan_df[current_scan_df['flags_met'] >= min_flags]

        if passed_this_scan_df.empty:
            print(f"No symbols met the criteria for scan: '{scan_name}'.")
        else:
            any_scan_passed = True
            print(f"\nSymbols meeting criteria for scan: '{scan_name}'")
            # Prepare display columns, ensuring flags_met is last
            base_cols = [col for col in df_results.columns if col != 'flags_met'] # Use original cols list
            display_cols = base_cols + ['flags_met']
            
            # Ensure columns exist in the filtered df before selecting and sorting
            cols_to_display_final = [col for col in display_cols if col in passed_this_scan_df.columns]
            
            if isinstance(passed_this_scan_df, pd.DataFrame) and hasattr(passed_this_scan_df, 'to_markdown'):
                 # Use new output handler
                 df_to_output_scan = passed_this_scan_df[cols_to_display_final].sort_values(by='flags_met', ascending=False).head(20)
                 for out_conf in output_configs:
                    # Potentially use different path suffixes for each scan
                    conf_scan = out_conf.copy()
                    if conf_scan.get('path'):
                        base, ext = os.path.splitext(conf_scan['path'])
                        conf_scan['path'] = f"{base}_{scan_name.replace(' ', '_')}{ext}"
                    write_output(df_to_output_scan, conf_scan, title=f"Symbols meeting criteria for scan: '{scan_name}'")
            else:
                # Fallback print for non-DataFrame or missing to_markdown (less likely with current setup)
                print(f"\nSymbols meeting criteria for scan: '{scan_name}' (fallback print)")
                print(passed_this_scan_df[cols_to_display_final].sort_values(by='flags_met', ascending=False).head(20))

    if not any_scan_passed:
        print("\nNo symbols passed any of the enabled scans.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

    # Default timeframe, consider making this an argument or part of config.
    # For now, keeping it as before for direct script execution.
    timeframe_to_analyze = os.getenv("TIMEFRAME_TO_ANALYZE", "1h")
    config_file_path = os.getenv("SCAN_CONFIG_PATH", "scan_config.yaml")

    # Ensure asyncio policy for Windows if running directly
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_analysis_workflow(config_path=config_file_path, default_timeframe=timeframe_to_analyze)) 