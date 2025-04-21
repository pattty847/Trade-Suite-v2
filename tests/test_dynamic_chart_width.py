import os
import sys
import pandas as pd
import dearpygui.dearpygui as dpg
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

# Add the project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from trade_suite.gui.utils import timeframe_to_dpg_time_unit

class DynamicChartWidthTest:
    """Test application to explore dynamic candle and volume bar width scaling based on timeframes."""
    
    def __init__(self):
        self.data_cache_dir = project_root / "data" / "cache"
        self.timeframes = ["1m", "5m", "1h", "1d"]
        self.candle_series_tags = {}
        self.volume_series_tags = {}
        
        # Window & plot tags
        self.window_tag = "dynamic_width_test_window"
        self.auto_scale_tag = "auto_scale_checkbox"
        self.base_width_tag = "base_width_slider"
        self.width_adjust_tag = "width_adjust_slider"
        
        # Width settings
        self.auto_scale_enabled = True
        self.base_width = 0.7
        self.width_adjustment = 1.0  # Multiplier for calculated widths
        
        # Timeframe time spans in seconds
        self.timeframe_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400
        }
    
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
    
    def calculate_width_factor(self, timeframe, data_df):
        """
        Calculate appropriate width factor based on timeframe and data density.
        
        This is the key function that determines how wide candles and volume bars should be
        to maintain consistent visual appearance across timeframes.
        """
        if not self.auto_scale_enabled or data_df is None or data_df.empty:
            return self.base_width
        
        # Get time unit from timeframe for reference
        time_unit = timeframe_to_dpg_time_unit(timeframe)
        
        # Get the timeframe span in seconds
        tf_seconds = self.timeframe_seconds.get(timeframe, 60)  # Default to 1m if unknown
        
        # Calculate average time between candles (should be close to tf_seconds)
        if len(data_df) > 1:
            timestamps = data_df['dates'].values
            avg_time_delta = np.mean(np.diff(timestamps))
            
            # Calculate width based on a reference timeframe (e.g., 1m)
            reference_tf = "1m"
            reference_seconds = self.timeframe_seconds.get(reference_tf, 60)
            
            # Width should scale proportionally to the timeframe ratio
            # This way, 1h candles will be 60x wider than 1m candles
            width_factor = (tf_seconds / reference_seconds) * self.base_width * self.width_adjustment
            
            # Cap width factor to prevent extremely wide candles for high timeframes
            width_factor = min(width_factor, 10.0)
            
            print(f"Timeframe: {timeframe}, Time Unit: {time_unit}, " 
                  f"Avg Time Delta: {avg_time_delta:.2f}s, Width Factor: {width_factor:.3f}")
            
            return width_factor
        
        # Fallback to base width if calculation not possible
        return self.base_width
    
    def create_ui(self):
        """Create the DearPyGUI UI for testing."""
        dpg.create_context()
        dpg.create_viewport(title="Dynamic Chart Width Test", width=1200, height=800)
        dpg.setup_dearpygui()
        
        with dpg.window(tag=self.window_tag, width=1200, height=800):
            # Controls
            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Auto-scale widths by timeframe", 
                    default_value=self.auto_scale_enabled,
                    tag=self.auto_scale_tag,
                    callback=self.toggle_auto_scale
                )
                dpg.add_spacer(width=20)
                dpg.add_text("Base Width:")
                dpg.add_slider_float(
                    tag=self.base_width_tag,
                    default_value=self.base_width,
                    min_value=0.1,
                    max_value=3.0,
                    callback=self.update_base_width
                )
                dpg.add_spacer(width=20)
                dpg.add_text("Width Adjustment:")
                dpg.add_slider_float(
                    tag=self.width_adjust_tag,
                    default_value=self.width_adjustment,
                    min_value=0.1,
                    max_value=5.0,
                    callback=self.update_width_adjustment
                )
                dpg.add_spacer(width=20)
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
                                        weight=self.base_width
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
                                        weight=self.base_width
                                    )
        
        dpg.show_viewport()
    
    def update_charts(self):
        """Update all charts with data and appropriate widths."""
        # Load and display data for each timeframe
        for tf in self.timeframes:
            df = self.load_data(tf)
            if df is not None:
                # Calculate appropriate width for this timeframe
                width_factor = self.calculate_width_factor(tf, df)
                
                # Update the candle series
                dpg.configure_item(
                    self.candle_series_tags[tf],
                    dates=df["dates"].tolist(),
                    opens=df["opens"].tolist(),
                    highs=df["highs"].tolist(),
                    lows=df["lows"].tolist(),
                    closes=df["closes"].tolist(),
                    weight=width_factor
                )
                
                # Update the volume series
                dpg.configure_item(
                    self.volume_series_tags[tf],
                    x=df["dates"].tolist(),
                    y=df["volumes"].tolist(),
                    weight=width_factor
                )
            else:
                print(f"No data available for timeframe {tf}")
        
        # Fit the view
        self.fit_plots()
    
    def toggle_auto_scale(self, sender, value):
        """Toggle auto-scaling of widths based on timeframe."""
        self.auto_scale_enabled = value
        self.update_charts()
    
    def update_base_width(self, sender, value):
        """Update base width factor."""
        self.base_width = value
        self.update_charts()
    
    def update_width_adjustment(self, sender, value):
        """Update width adjustment multiplier."""
        self.width_adjustment = value
        self.update_charts()
    
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
    test = DynamicChartWidthTest()
    test.run() 