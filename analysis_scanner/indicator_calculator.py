import pandas as pd
import numpy as np
import ta
import logging

def anchored_vwap(df, anchor_time):
    """Calculates Anchored VWAP from the given anchor_time.
    anchor_time should be a pandas Timestamp.
    """
    # Find the first row at or after the anchor_time
    anchor_df = df[df.index >= anchor_time]
    if anchor_df.empty:
        # logging.warning(f"Anchor time {anchor_time} not found in DataFrame index. VWAP will be NaN.")
        return pd.Series([np.nan] * len(df.index), index=df.index) # Return series of NaNs matching df length

    # Slice the DataFrame from the actual anchor point found
    actual_anchor_time = anchor_df.index[0]
    
    # Calculate cumulative sum of (price * volume) and cumulative sum of volume
    num = (df.loc[actual_anchor_time:, 'closes'] * df.loc[actual_anchor_time:, 'volumes']).cumsum()
    denom = df.loc[actual_anchor_time:, 'volumes'].cumsum()
    
    # Calculate VWAP, handling potential division by zero by replacing with NaN
    vwap_series = (num / denom).reindex(df.index) # Reindex to match original df index, filling with NaNs before anchor
    return vwap_series

def calculate_technical_indicators(
    df: pd.DataFrame, 
    anchor_timestamp_for_vwap: pd.Timestamp, 
    current_symbol_name: str, # For logging/debugging purposes
    btc_closes_series: pd.Series | None = None, 
    btc_target_symbol_name_for_comparison: str | None = None
):
    """Calculates all technical indicators for the given DataFrame.
    Returns a dictionary of indicator values (factors).
    """
    factors = {}
    min_length_adx = 28 # ADX default window is 14, needs 2*window typically for stability

    latest = df.iloc[-1]

    # --- basic price & TA-Lib indicators ---
    rsi = ta.momentum.RSIIndicator(df['closes']).rsi()
    sma20 = df['closes'].rolling(20).mean()
    std20 = df['closes'].rolling(20).std() # For BB
    sma50 = df['closes'].rolling(50).mean()
    std50 = df['closes'].rolling(50).std()
    
    bb_middle = sma20 # Bollinger Middle Band is SMA20
    bb_upper = bb_middle + 2 * std20
    bb_lower = bb_middle - 2 * std20
    
    atr = ta.volatility.AverageTrueRange(df['highs'], df['lows'], df['closes']).average_true_range()
    vwap_series = anchored_vwap(df, anchor_timestamp_for_vwap)
    vwap_value = vwap_series.iloc[-1] if pd.notna(vwap_series.iloc[-1]) else np.nan

    # --- Calculate Daily VWAP ---
    daily_anchor_ts = df.index[-1].normalize() # 00:00 UTC of the latest day in the (potentially tailed) df
    vwap_daily_series = anchored_vwap(df, daily_anchor_ts)
    vwap_daily_value = vwap_daily_series.iloc[-1] if pd.notna(vwap_daily_series.iloc[-1]) else np.nan
    # ---------------------------

    # --- New Indicators ---
    volume_zscore_value = np.nan
    rvol_value = np.nan
    bbw_value = np.nan
    adx_value = np.nan

    if 'volumes' in df.columns and df['volumes'].notna().sum() > 20: # Need enough volume data
        vol_sma20 = df['volumes'].rolling(20, min_periods=10).mean()
        vol_std20 = df['volumes'].rolling(20, min_periods=10).std()
        current_volume = df['volumes'].iloc[-1]
        latest_vol_sma20 = vol_sma20.iloc[-1]
        latest_vol_std20 = vol_std20.iloc[-1]

        if pd.notna(current_volume) and pd.notna(latest_vol_sma20) and pd.notna(latest_vol_std20) and latest_vol_std20 != 0:
            volume_zscore_value = (current_volume - latest_vol_sma20) / latest_vol_std20
        
        if pd.notna(current_volume) and pd.notna(latest_vol_sma20) and latest_vol_sma20 != 0:
            rvol_value = current_volume / latest_vol_sma20
    
    # Bollinger Bandwidth (Normalized)
    if pd.notna(bb_upper.iloc[-1]) and pd.notna(bb_lower.iloc[-1]) and pd.notna(bb_middle.iloc[-1]) and bb_middle.iloc[-1] != 0:
        bbw_value = (bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_middle.iloc[-1]

    # ADX
    try:
        if df['highs'].notna().sum() >= min_length_adx and \
           df['lows'].notna().sum() >= min_length_adx and \
           df['closes'].notna().sum() >= min_length_adx:
            adx_indicator = ta.trend.ADXIndicator(df['highs'], df['lows'], df['closes'], window=14)
            adx_series = adx_indicator.adx()
            if adx_series is not None and not adx_series.empty and pd.notna(adx_series.iloc[-1]):
                adx_value = adx_series.iloc[-1]
        # else:
            # logging.debug(f"Skipping ADX for {current_symbol_name} due to insufficient non-NaN data for ADX window.")
    except Exception as e:
        logging.warning(f"Could not calculate ADX for {current_symbol_name}: {e}")

    # --- BTC Relative Z-Score ---
    btc_relative_zscore_value = np.nan
    if btc_closes_series is not None and current_symbol_name != btc_target_symbol_name_for_comparison:
        try:
            if not isinstance(df.index, pd.DatetimeIndex):
                 logging.warning(f"Index for {current_symbol_name} is not DatetimeIndex prior to BTC merge. This is unexpected.")
            
            temp_symbol_closes = df[['closes']].copy()
            merged_df = pd.merge(temp_symbol_closes, btc_closes_series.rename('btc_closes'), 
                                 left_index=True, right_index=True, how='inner')

            if not merged_df.empty and len(merged_df) >= 50 and 'closes' in merged_df.columns and 'btc_closes' in merged_df.columns:
                merged_df['price_ratio'] = merged_df['closes'] / merged_df['btc_closes'].replace(0, np.nan)
                merged_df.replace([np.inf, -np.inf], np.nan, inplace=True)
                merged_df.dropna(subset=['price_ratio'], inplace=True)

                if len(merged_df) >= 50:
                    ratio_sma = merged_df['price_ratio'].rolling(window=50, min_periods=20).mean()
                    ratio_std = merged_df['price_ratio'].rolling(window=50, min_periods=20).std()
                    
                    latest_ratio = merged_df['price_ratio'].iloc[-1]
                    latest_ratio_sma = ratio_sma.iloc[-1]
                    latest_ratio_std = ratio_std.iloc[-1]

                    if pd.notna(latest_ratio) and pd.notna(latest_ratio_sma) and pd.notna(latest_ratio_std) and latest_ratio_std != 0:
                        btc_relative_zscore_value = (latest_ratio - latest_ratio_sma) / latest_ratio_std
                    # else:
                        # logging.debug(f"Could not calculate BTC_rel_zscore for {current_symbol_name}: NaN in ratio SMA/STD or STD is zero.")
                # else:
                    # logging.debug(f"Not enough overlapping data points with BTC for {current_symbol_name} to calculate ratio Z-score after merge ({len(merged_df)} points).")
            # else:
                # logging.debug(f"Not enough overlapping data points with BTC for {current_symbol_name} to calculate ratio Z-score ({len(merged_df)} points), or missing columns.")
        except Exception as e:
            logging.error(f"Error calculating BTC relative Z-score for {current_symbol_name}: {e}")

    factors = {
        "close": latest.closes,
        "volume": latest.volumes if 'volumes' in latest else np.nan,
        "RSI": rsi.iloc[-1] if pd.notna(rsi.iloc[-1]) else np.nan,
        "zscore": (latest.closes - sma50.iloc[-1]) / std50.iloc[-1] if pd.notna(sma50.iloc[-1]) and pd.notna(std50.iloc[-1]) and std50.iloc[-1] != 0 else np.nan,
        "%B": (latest.closes - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) if pd.notna(bb_upper.iloc[-1]) and pd.notna(bb_lower.iloc[-1]) and (bb_upper.iloc[-1] - bb_lower.iloc[-1]) != 0 else np.nan, # Corrected %B definition
        "ATRstretch": abs(latest.closes - sma20.iloc[-1]) / atr.iloc[-1] if pd.notna(atr.iloc[-1]) and atr.iloc[-1] != 0 else np.nan,
        "VWAPgap": (latest.closes - vwap_value) / vwap_value if pd.notna(vwap_value) and vwap_value != 0 else np.nan,
        "VWAPgap_daily": (latest.closes - vwap_daily_value) / vwap_daily_value if pd.notna(vwap_daily_value) and vwap_daily_value != 0 else np.nan, # Added daily VWAP gap
        "BTC_rel_zscore": btc_relative_zscore_value,
        "VolumeZScore": volume_zscore_value,
        "RVOL": rvol_value,
        "BBW": bbw_value,
        "ADX": adx_value,
    }
    return factors 