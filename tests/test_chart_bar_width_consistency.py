import dearpygui.dearpygui as dpg
import pandas as pd
import numpy as np
import time
from pathlib import Path
import sys

# Add the project root to path for imports if necessary
# (Assuming the script is run from the project root or tests directory)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Attempt to import from trade_suite, handle if not found
try:
    from trade_suite.gui.utils import timeframe_to_dpg_time_unit
except ImportError:
    print("Warning: trade_suite.gui.utils not found. Using basic time unit mapping.")
    # Basic fallback mapping
    def timeframe_to_dpg_time_unit(tf_str):
        if "m" in tf_str: return dpg.mvTimeUnit_Min
        if "H" in tf_str or "h" in tf_str: return dpg.mvTimeUnit_Hr
        if "D" in tf_str or "d" in tf_str: return dpg.mvTimeUnit_Day
        return dpg.mvTimeUnit_Min # Default

class ChartBarWidthConsistencyTest:
    """Test harness to visualize candle and volume bar width consistency across timeframes."""

    def __init__(self):
        self.data_cache_dir = project_root / "data" / "cache"
        self.timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"] # Timeframes to test
        self.ohlc_data = {} # Stores {'tf': df, ...}
        self.candle_series_tags = {}
        self.volume_series_tags = {}
        self.plot_tags = {} # Store plot tags for fitting axes
        self.volume_plot_tags = {} # Store volume plot tags

        self.current_weight = 0.15 # Default starting weight (often good for 1m)
        self.max_candles_display = 200 # Limit display for clarity

        # DPG Tags
        self.window_tag = "consistency_test_window"
        self.weight_slider_tag = "consistency_weight_slider"
        self.tab_bar_tag = "consistency_tab_bar"

    def load_and_prepare_data(self):
        """Loads data from cache or resamples from 1m data."""
        print("Loading and preparing data...")
        base_1m_df = None
        base_1m_file = self.data_cache_dir / "coinbase_BTC-USD_1m.csv"

        if base_1m_file.exists():
            try:
                base_1m_df = pd.read_csv(base_1m_file)
                # Convert ms timestamps to seconds
                if base_1m_df['dates'].max() > 2_000_000_000: # Check if likely milliseconds
                     base_1m_df['dates'] = base_1m_df['dates'] / 1000
                base_1m_df['datetime'] = pd.to_datetime(base_1m_df['dates'], unit='s', utc=True)
                base_1m_df.set_index('datetime', inplace=True)
                base_1m_df = base_1m_df.sort_index()
                self.ohlc_data["1m"] = base_1m_df.copy() # Store the loaded 1m data
                print("Loaded 1m data.")
            except Exception as e:
                print(f"Error loading base 1m data: {e}")
                base_1m_df = None # Ensure it's None if loading failed

        else:
             print(f"Base 1m data file not found: {base_1m_file}")


        # Define resampling rules and frequency map
        ohlc_dict = {
            'opens': 'first',
            'highs': 'max',
            'lows': 'min',
            'closes': 'last',
            'volumes': 'sum'
        }
        freq_map = {
            # "1m": "1min", # Already loaded
            "5m": "5min",
            "15m": "15min",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }

        for tf in self.timeframes:
            if tf == "1m" and "1m" in self.ohlc_data:
                continue # Skip 1m if already loaded

            print(f"Processing {tf}...")
            # Option 1: Load directly if available
            tf_file = self.data_cache_dir / f"coinbase_BTC-USD_{tf}.csv"
            loaded_directly = False
            if tf_file.exists():
                try:
                    df_tf = pd.read_csv(tf_file)
                    if df_tf['dates'].max() > 2_000_000_000:
                        df_tf['dates'] = df_tf['dates'] / 1000
                    df_tf['datetime'] = pd.to_datetime(df_tf['dates'], unit='s', utc=True)
                    df_tf.set_index('datetime', inplace=True)
                    df_tf = df_tf.sort_index()
                    self.ohlc_data[tf] = df_tf
                    print(f"Loaded {tf} data directly.")
                    loaded_directly = True
                except Exception as e:
                    print(f"Error loading {tf} data directly: {e}. Will attempt resampling.")

            # Option 2: Resample from 1m if direct load failed or file doesn't exist AND base_1m_df exists
            if not loaded_directly and base_1m_df is not None and tf in freq_map:
                print(f"Resampling 1m data to {tf}...")
                try:
                    resampled_df = base_1m_df.resample(freq_map[tf], label='right', closed='right').agg(ohlc_dict)
                    if tf == "4h": print(f"--- DEBUG 4h: Rows after resample().agg(): {len(resampled_df)}") # DEBUG
                    resampled_df.dropna(inplace=True)
                    if tf == "4h": print(f"--- DEBUG 4h: Rows after dropna(): {len(resampled_df)}") # DEBUG
                    # Convert index back to epoch seconds for DPG plots
                    resampled_df['dates'] = resampled_df.index.astype(np.int64) // 10**9
                    self.ohlc_data[tf] = resampled_df
                    print(f"Resampled {tf} data.")
                except Exception as e:
                    print(f"Error resampling 1m to {tf}: {e}")
            elif not loaded_directly:
                 print(f"Could not load or resample data for {tf}.")
            elif loaded_directly and tf == "4h": # Add check if loaded directly
                 print(f"--- DEBUG 4h: Loaded directly. Rows: {len(self.ohlc_data[tf])}") # DEBUG


        # Final check and trim data for display
        for tf, df in self.ohlc_data.items():
            if tf == "4h": print(f"--- DEBUG 4h: Rows BEFORE final trim: {len(df)}") # DEBUG
            if 'dates' not in df.columns and df.index.name == 'datetime':
                 # If we loaded directly and didn't resample, ensure 'dates' column exists
                 self.ohlc_data[tf]['dates'] = df.index.astype(np.int64) // 10**9

            if len(df) > self.max_candles_display:
                if tf == "4h": print(f"--- DEBUG 4h: Applying tail({self.max_candles_display})") # DEBUG
                self.ohlc_data[tf] = df.tail(self.max_candles_display)
            elif tf == "4h": # Also print if no trim needed
                 print(f"--- DEBUG 4h: No final trim needed (rows <= {self.max_candles_display})") # DEBUG

            # Add date range print for 4h
            if tf == "4h":
                if not df.empty:
                    print(f"--- DEBUG 4h: Final date range: {df.index.min()} to {df.index.max()}")
                else:
                    print(f"--- DEBUG 4h: Final dataframe is empty.")


        print("Data preparation complete.")


    def create_ui(self):
        """Create the DearPyGUI UI for testing."""
        dpg.create_context()
        dpg.create_viewport(title="Candle Width Consistency Test", width=1400, height=900)
        dpg.setup_dearpygui()

        with dpg.window(tag=self.window_tag, width=-1, height=-1):
            # Controls
            with dpg.group(horizontal=True):
                dpg.add_text("Universal Weight:")
                dpg.add_slider_float(
                    tag=self.weight_slider_tag,
                    default_value=self.current_weight,
                    min_value=0.01,
                    max_value=1.0, # Adjusted max based on observation
                    callback=self.update_weight_callback,
                    width=200
                )
                dpg.add_text(f"{self.current_weight:.3f}", tag="weight_display")
                dpg.add_button(label="Fit All Plots", callback=self.fit_all_plots)

            # Tabs for each timeframe
            with dpg.tab_bar(tag=self.tab_bar_tag):
                for tf in self.timeframes:
                    with dpg.tab(label=f"{tf} Chart"):
                        price_plot_tag = f"price_plot_{tf}"
                        volume_plot_tag = f"volume_plot_{tf}"
                        candle_series_tag = f"candle_series_{tf}"
                        volume_series_tag = f"volume_series_{tf}"
                        price_yaxis_tag = f"price_yaxis_{tf}"
                        volume_yaxis_tag = f"volume_yaxis_{tf}"
                        xaxis_tag = f"xaxis_{tf}" # Shared X-axis within subplot

                        self.plot_tags[tf] = price_plot_tag
                        self.volume_plot_tags[tf] = volume_plot_tag
                        self.candle_series_tags[tf] = candle_series_tag
                        self.volume_series_tags[tf] = volume_series_tag

                        # Create plot with candles and volume subplots
                        with dpg.subplots(
                            rows=2,
                            columns=1,
                            row_ratios=[0.75, 0.25], # Give more space to price
                            link_all_x=True,
                            height=-1,
                            width=-1
                        ):
                            # Candle chart
                            with dpg.plot(tag=price_plot_tag, no_title=True):
                                dpg.add_plot_legend()
                                # Price Y Axis
                                dpg.add_plot_axis(dpg.mvYAxis, label="Price", tag=price_yaxis_tag)
                                # Shared X Axis (Time) - only add it once
                                dpg.add_plot_axis(dpg.mvXAxis, label="Time", time=True, tag=xaxis_tag, parent=price_plot_tag)

                                # Add Candle Series (empty initially)
                                dpg.add_candle_series(
                                    dates=[], opens=[], highs=[], lows=[], closes=[],
                                    label=f"BTC/USD {tf}",
                                    tag=candle_series_tag,
                                    parent=price_yaxis_tag, # Attach to the correct Y axis
                                    time_unit=timeframe_to_dpg_time_unit(tf),
                                    weight=self.current_weight
                                )

                            # Volume chart
                            with dpg.plot(tag=volume_plot_tag, no_title=True):
                                # Volume Y Axis
                                dpg.add_plot_axis(dpg.mvYAxis, label="Volume", tag=volume_yaxis_tag)
                                # Link X axis implicitly via subplot link_all_x=True

                                # Add Volume Series (empty initially)
                                dpg.add_bar_series(
                                    x=[], y=[],
                                    label=f"Volume {tf}",
                                    tag=volume_series_tag,
                                    parent=volume_yaxis_tag, # Attach to the correct Y axis
                                    weight=self.current_weight
                                )

        dpg.show_viewport()

    def update_charts_with_data(self):
        """Populate the created chart series with loaded/resampled data."""
        print("Updating charts with data...")
        for tf in self.timeframes:
            if tf in self.ohlc_data:
                df = self.ohlc_data[tf]
                # Ensure required columns exist
                required_cols = ['dates', 'opens', 'highs', 'lows', 'closes', 'volumes']
                if not all(col in df.columns for col in required_cols):
                    print(f"Skipping {tf}: Missing required columns in DataFrame.")
                    print(f"Columns present: {df.columns.tolist()}")
                    continue

                # Get data as lists
                dates = df["dates"].tolist()
                opens = df["opens"].tolist()
                highs = df["highs"].tolist()
                lows = df["lows"].tolist()
                closes = df["closes"].tolist()
                volumes = df["volumes"].tolist()

                if not dates: # Skip if no data after potential trimming/resampling
                    print(f"Skipping {tf}: No data points.")
                    continue

                # Update the candle series
                if dpg.does_item_exist(self.candle_series_tags[tf]):
                    dpg.configure_item(
                        self.candle_series_tags[tf],
                        dates=dates,
                        opens=opens,
                        highs=highs,
                        lows=lows,
                        closes=closes,
                        weight=self.current_weight
                    )
                else:
                    print(f"Error: Candle series tag {self.candle_series_tags[tf]} does not exist.")


                # Update the volume series
                if tf in self.volume_series_tags and dpg.does_item_exist(self.volume_series_tags[tf]):
                    print(f"--- DEBUG: Configuring volume series {self.volume_series_tags[tf]} with weight {self.current_weight:.3f}") # DEBUG
                    dpg.configure_item(self.volume_series_tags[tf], weight=self.current_weight)
                else:
                    print(f"Error: Volume series tag {self.volume_series_tags[tf]} does not exist.")

            else:
                print(f"No data loaded for timeframe {tf}, chart will be empty.")
        print("Chart data update complete.")
        # Fit plots after data is loaded
        self.fit_all_plots()

    def update_weight_callback(self, sender, app_data, user_data):
        """Callback when the weight slider is changed."""
        self.current_weight = app_data
        dpg.set_value("weight_display", f"{self.current_weight:.3f}") # Update text display

        # Update weight for all existing series
        for tf in self.timeframes:
            if tf in self.candle_series_tags and dpg.does_item_exist(self.candle_series_tags[tf]):
                dpg.configure_item(self.candle_series_tags[tf], weight=self.current_weight)
            if tf in self.volume_series_tags and dpg.does_item_exist(self.volume_series_tags[tf]):
                dpg.configure_item(self.volume_series_tags[tf], weight=self.current_weight)

    def fit_all_plots(self):
        """Fit all axes of all plots across all tabs."""
        print("Fitting all plot axes...")
        for tf in self.timeframes:
            if tf in self.plot_tags and dpg.does_item_exist(self.plot_tags[tf]):
                 # Iterate through axes of the price plot
                 for axis in dpg.get_item_children(self.plot_tags[tf], slot=1): # Slot 1 is usually axes
                    if dpg.get_item_info(axis)["type"] == "mvAppItemType::PlotAxis":
                         dpg.fit_axis_data(axis)
            if tf in self.volume_plot_tags and dpg.does_item_exist(self.volume_plot_tags[tf]):
                 # Iterate through axes of the volume plot
                 for axis in dpg.get_item_children(self.volume_plot_tags[tf], slot=1):
                    if dpg.get_item_info(axis)["type"] == "mvAppItemType::PlotAxis":
                         dpg.fit_axis_data(axis)
        print("Axis fitting complete.")


    def run(self):
        """Load data, create UI, populate charts, and run the DPG app."""
        try:
            self.load_and_prepare_data()
            self.create_ui()
            # Defer data update until after the first frame to ensure UI exists
            dpg.set_frame_callback(1, self.update_charts_with_data)
            # dpg.show_item_registry() # Optional: for debugging tags
            dpg.start_dearpygui()
        finally:
            if dpg.is_dearpygui_running():
                dpg.stop_dearpygui()
            dpg.destroy_context()

if __name__ == "__main__":
    test = ChartBarWidthConsistencyTest()
    test.run() 