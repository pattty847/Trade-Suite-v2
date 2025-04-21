import os
import sys
import pandas as pd
import dearpygui.dearpygui as dpg
import numpy as np
from pathlib import Path

# Add the project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from trade_suite.gui.utils import timeframe_to_dpg_time_unit

class ChartBarWidthTest:
    """Test harness to explore candle and volume bar width consistency across timeframes."""
    
    def __init__(self):
        self.data_cache_dir = project_root / "data" / "cache"
        self.timeframes = ["1m", "5m", "1h", "1d"]
        self.candle_series_tags = {}
        self.volume_series_tags = {}
        self.current_width_factor = 0.7  # Default starting width factor
        
        # Window & plot tags
        self.window_tag = "chart_width_test_window"
        self.plot_tag = "chart_width_test_plot"
        self.volume_plot_tag = "volume_width_test_plot"
        self.width_slider_tag = "width_factor_slider"
    
    def load_data(self, timeframe):
        """Load data for the specified timeframe."""
        file_path = self.data_cache_dir / f"coinbase_BTC-USD_{timeframe}.csv"
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return None
        
        df = pd.read_csv(file_path)
        # Convert timestamps to seconds if needed
        if df['dates'].max() > 2_000_000_000:
            df['dates'] = df['dates'] / 1000
        
        # For testing, limit to recent 100 candles
        if len(df) > 100:
            df = df.tail(100).reset_index(drop=True)
        
        return df
    
    def resample_data(self, source_df, source_tf, target_tf):
        """Resample data from source timeframe to target timeframe."""
        # Convert timestamps to datetime
        df = source_df.copy()
        df['datetime'] = pd.to_datetime(df['dates'], unit='s')
        df.set_index('datetime', inplace=True)
        
        # Determine the resampling frequency
        freq_map = {
            "1m": "1T",
            "5m": "5T",
            "15m": "15T",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }
        
        # Resample the data
        resampled = df.resample(freq_map[target_tf]).agg({
            'opens': 'first',
            'highs': 'max',
            'lows': 'min',
            'closes': 'last',
            'volumes': 'sum',
            'dates': 'first'  # Keep the original timestamp
        })
        
        # Reset index and format
        resampled.reset_index(inplace=True)
        resampled['dates'] = resampled['datetime'].astype(np.int64) // 10**9  # Convert to seconds
        resampled.drop('datetime', axis=1, inplace=True)
        
        return resampled
    
    def create_ui(self):
        """Create the DearPyGUI UI for testing."""
        dpg.create_context()
        dpg.create_viewport(title="Chart Bar Width Test", width=1200, height=800)
        dpg.setup_dearpygui()
        
        with dpg.window(tag=self.window_tag, width=1200, height=800):
            # Controls
            with dpg.group(horizontal=True):
                dpg.add_text("Width Factor:")
                dpg.add_slider_float(
                    tag=self.width_slider_tag,
                    default_value=self.current_width_factor,
                    min_value=0.1,
                    max_value=3.0,
                    callback=self.update_width_factor
                )
                dpg.add_button(label="Reset View", callback=self.fit_plots)
            
            # Add tabs for different timeframes
            with dpg.tab_bar():
                for tf in self.timeframes:
                    with dpg.tab(label=f"{tf} Chart"):
                        # Create plot with candles and volume subplots
                        with dpg.subplots(
                            rows=2, 
                            columns=1, 
                            row_ratios=[0.8, 0.2], 
                            link_all_x=True,
                            height=-1,
                            width=-1
                        ):
                            # Candle chart
                            with dpg.plot(label=f"Price - {tf}"):
                                dpg.add_plot_legend()
                                
                                # X Axis (hidden for price chart)
                                x_axis = dpg.add_plot_axis(
                                    dpg.mvXAxis, 
                                    scale=dpg.mvPlotScale_Time,
                                    no_tick_marks=True,
                                    no_tick_labels=True
                                )
                                
                                # Y Axis for price
                                with dpg.plot_axis(dpg.mvYAxis, label="Price"):
                                    # Candle series
                                    self.candle_series_tags[tf] = dpg.add_candle_series(
                                        dates=[], opens=[], highs=[], lows=[], closes=[],
                                        label=f"BTC/USD {tf}",
                                        time_unit=timeframe_to_dpg_time_unit(tf),
                                        weight=self.current_width_factor
                                    )
                            
                            # Volume chart
                            with dpg.plot(label=f"Volume - {tf}"):
                                # X Axis (visible for volume chart)
                                dpg.add_plot_axis(dpg.mvXAxis, time=True)
                                
                                # Y Axis for volume
                                with dpg.plot_axis(dpg.mvYAxis, label="Volume"):
                                    # Volume series
                                    self.volume_series_tags[tf] = dpg.add_bar_series(
                                        x=[], y=[],
                                        label=f"Volume {tf}",
                                        weight=self.current_width_factor
                                    )
        
        dpg.show_viewport()
    
    def update_charts(self):
        """Update all charts with data."""
        # Load and display base data for each timeframe
        for tf in self.timeframes:
            df = self.load_data(tf)
            if df is not None:
                # Update the candle series
                dpg.configure_item(
                    self.candle_series_tags[tf],
                    dates=df["dates"].tolist(),
                    opens=df["opens"].tolist(),
                    highs=df["highs"].tolist(),
                    lows=df["lows"].tolist(),
                    closes=df["closes"].tolist(),
                    weight=self.current_width_factor
                )
                
                # Update the volume series
                dpg.configure_item(
                    self.volume_series_tags[tf],
                    x=df["dates"].tolist(),
                    y=df["volumes"].tolist(),
                    weight=self.current_width_factor
                )
            else:
                print(f"No data available for timeframe {tf}")
                
                # Try to resample from another timeframe if available
                if tf != "1m" and "1m" in self.timeframes:
                    minute_data = self.load_data("1m")
                    if minute_data is not None:
                        print(f"Resampling 1m data to {tf}")
                        resampled = self.resample_data(minute_data, "1m", tf)
                        
                        # Update charts with resampled data
                        dpg.configure_item(
                            self.candle_series_tags[tf],
                            dates=resampled["dates"].tolist(),
                            opens=resampled["opens"].tolist(),
                            highs=resampled["highs"].tolist(),
                            lows=resampled["lows"].tolist(),
                            closes=resampled["closes"].tolist(),
                            weight=self.current_width_factor
                        )
                        
                        dpg.configure_item(
                            self.volume_series_tags[tf],
                            x=resampled["dates"].tolist(),
                            y=resampled["volumes"].tolist(),
                            weight=self.current_width_factor
                        )
        
        # Fit the view
        self.fit_plots()
    
    def update_width_factor(self, sender, value):
        """Update width factor for all series based on slider value."""
        self.current_width_factor = value
        
        # Update all candle series
        for tf, tag in self.candle_series_tags.items():
            dpg.configure_item(tag, weight=self.current_width_factor)
        
        # Update all volume series
        for tf, tag in self.volume_series_tags.items():
            dpg.configure_item(tag, weight=self.current_width_factor)
    
    def fit_plots(self):
        """Fit all plots to data."""
        for parent in dpg.get_item_children(self.window_tag, slot=1):
            if dpg.get_item_type(parent) == "mvAppItemType::TabBar":
                for tab in dpg.get_item_children(parent, slot=1):
                    for subplot in dpg.get_item_children(tab, slot=1):
                        for plot in dpg.get_item_children(subplot, slot=1):
                            for axis in dpg.get_item_children(plot, slot=1):
                                if dpg.get_item_type(axis) == "mvAppItemType::PlotAxis":
                                    dpg.fit_axis_data(axis)
    
    def run(self):
        """Run the test application."""
        try:
            self.create_ui()
            self.update_charts()
            dpg.start_dearpygui()
        finally:
            dpg.destroy_context()


if __name__ == "__main__":
    test = ChartBarWidthTest()
    test.run() 