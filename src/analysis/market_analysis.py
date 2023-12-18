import logging
from typing import Dict
import ccxt
import numpy as np
import pandas as pd


def wavetrend_with_signals(
    df,
    wtChannelLen=9,
    wtAverageLen=12,
    wtMALen=3,
    obLevel1=40,
    obLevel2=60,
    obLevel3=75,
    osLevel1=-40,
    osLevel2=-60,
    osLevel3=-75,
):
    """
    The wavetrend_with_signals function calculates the WaveTrend Oscillator and generates buy/sell signals.

    :param df: Pass the dataframe to the function
    :param wtChannelLen: Set the length of the channel
    :param wtAverageLen: Set the length of the moving average used to smooth out the wavetrend oscillator
    :param wtMALen: Calculate the wavetrend oscillator
    :param obLevel1: Set the overbought level 1
    :param obLevel2: Set the overbought level 2
    :param obLevel3: Set the overbought level 3
    :param osLevel1: Determine when to buy
    :param osLevel2: Set the level at which a sell signal is generated
    :param osLevel3: Determine the level of oversold condition
    :return: A dataframe with the following columns:
                                 open      high       low     close     volume  lev1Buy  lev1Sell  lev2Buy  lev2Sell  lev3Buy  lev3Sell  signal
        timestamp
        2023-11-21 23:01:00  36344.23  36376.55  36309.76  36309.85  21.249519    False     False    False     False    False     False       0
        2023-11-21 23:02:00  36309.85  36348.83  36282.36  36307.45  19.253833    False     False    False     False    False     False       0
        2023-11-21 23:03:00  36307.45  36365.63  36282.74  36349.87  23.374930    False     False    False     False    False     False       0
        2023-11-21 23:04:00  36350.00  36362.49  36282.53  36290.37  40.188286    False     False    False     False     True     False       3
        2023-11-22 04:00:00  36387.88  36393.70  36378.90  36378.90   5.201228    False      True    False     False    False     False      -1
    :doc-author: Trelent
    """

    hlc3 = (df["high"] + df["low"] + df["close"]) / 3

    # WaveTrend Oscillator Calculation
    esa = hlc3.ewm(span=wtChannelLen, adjust=False).mean()
    de = abs(hlc3 - esa).ewm(span=wtChannelLen, adjust=False).mean()
    ci = (hlc3 - esa) / (0.015 * de)
    wt1 = ci.ewm(span=wtAverageLen, adjust=False).mean()
    wt2 = wt1.rolling(window=wtMALen).mean()

    # Buy and Sell Signal Logic
    df["lev1Buy"] = (
        ((wt1 - wt2) > 0) & (wt1.shift() <= osLevel1) & (wt1.shift() > osLevel2)
    )
    df["lev1Sell"] = (
        ((wt1 - wt2) < 0) & (wt1.shift() >= obLevel1) & (wt1.shift() < obLevel2)
    )
    df["lev2Buy"] = (
        ((wt1 - wt2) > 0) & (wt1.shift() <= osLevel2) & (wt1.shift() > osLevel3)
    )
    df["lev2Sell"] = (
        ((wt1 - wt2) < 0) & (wt1.shift() >= obLevel2) & (wt1.shift() < obLevel3)
    )
    df["lev3Buy"] = ((wt1 - wt2) > 0) & (wt1.shift() <= osLevel3)
    df["lev3Sell"] = ((wt1 - wt2) < 0) & (wt1.shift() >= obLevel3)

    # Assign numerical values for plotting
    df["signal"] = 0
    df.loc[df["lev1Buy"], "signal"] = 1  # I
    df.loc[df["lev1Sell"], "signal"] = -1  # I
    df.loc[df["lev2Buy"], "signal"] = 2  # II
    df.loc[df["lev2Sell"], "signal"] = -2  # II
    df.loc[df["lev3Buy"], "signal"] = 3  # III
    df.loc[df["lev3Sell"], "signal"] = -3  # III

    return df


def calculate_exhaustion(
    df, show_sr=True, swing_len=40, bars_back=4, bar_count=10, src="close"
):
    """
    The calculate_exhaustion function calculates exhaustion points for a given dataframe.

        Args:
            df (pandas.DataFrame): The dataframe to calculate exhaustion points on.
            show_sr (bool, optional): Whether or not to return support and resistance values in the outputted DataFrame. Defaults to True.
            swing_len (int, optional): The length of the swing used when calculating exhaustion points and support/resistance levels.. Defaults to 40 bars back from current bar's date index value..

    :param df: Pass the dataframe to the function
    :param show_sr: Show the support and resistance lines on the chart
    :param swing_len: Calculate the highest and lowest values in a given range of bars
    :param bars_back: Determine the number of bars to look back
    :param bar_count: Determine the number of bars that need to be in a trend before it is considered an exhaustion point
    :param src: Specify the source of data to be used for calculating exhaustion points
    :return:
                                open     high      low    close      volume  bullCount  bearCount  trend resistance support   lowest  highest
        timestamp
        2023-11-22 04:51:00  1988.10  1988.40  1985.62  1986.60  163.779227          0          0     -1     1986.2     NaN  1981.22  1988.40
    :doc-author: Trelent
    """

    # Initialize the counters and return values
    df["bullCount"] = 0
    df["bearCount"] = 0
    df["trend"] = 0
    df["resistance"] = pd.NA
    df["support"] = pd.NA

    # Calculate bull and bear counts
    df["bullCount"] = df[src].gt(df[src].shift(bars_back)).cumsum()
    df["bearCount"] = df[src].lt(df[src].shift(bars_back)).cumsum()

    # Identify exhaustion points
    df["lowest"] = df["low"].rolling(window=swing_len).min()
    df["highest"] = df["high"].rolling(window=swing_len).max()

    # Set trend values based on exhaustion points
    df.loc[
        (df["bullCount"] >= bar_count)
        & (df["close"] < df["open"])
        & (df["high"] >= df["highest"]),
        "trend",
    ] = -1
    df.loc[
        (df["bearCount"] >= bar_count)
        & (df["close"] > df["open"])
        & (df["low"] <= df["lowest"]),
        "trend",
    ] = 1

    # Reset count when conditions are met
    df.loc[df["bullCount"] >= bar_count, "bullCount"] = 0
    df.loc[df["bearCount"] >= bar_count, "bearCount"] = 0

    # Calculate Support and Resistance without shifting
    df.loc[(df["close"] < df["open"]) & (df["trend"] == -1), "resistance"] = df["high"]
    df.loc[(df["close"] > df["open"]) & (df["trend"] == 1), "support"] = df["low"]
    df["resistance"] = df["resistance"].ffill().shift(1)
    df["support"] = df["support"].ffill().shift(1)

    return df


def scan_multiple_assets(
    all_candles: Dict[str, Dict[str, pd.DataFrame]], bars_back=200, hyperparam=False
):
    """
    The scan_multiple_assets function takes in a dictionary of dataframes, and returns a list of dictionaries.
    Each dictionary contains the following keys:
        - exchange: The name of the exchange that this signal was found on.
        - symbol: The symbol for which this signal was found on.
        - timeframe: The timeframe for which this signal was found on (e.g., '5m', '15m', etc.)
        - trend: 1 if it's an exhaustion buy, or 2 if it's an exhaustion sell

    :param all_candles: ExchangeOHLCVData: Pass in the dataframe containing all of the candles
    :param bars_back: Determine how many bars back to look for a signal
    :param hyperparam: Determine if the function is being called from a hyperparameter scan or not
    :return: A list of dictionaries
    :doc-author: Trelent
    """
    results = []

    for exchange_name, candles in all_candles.items():
        for key, df in candles.items():
            symbol, timeframe = key.split("-")
            df_with_signal = calculate_exhaustion(df)

            # Iterate through the DataFrame and check each row
            for i in range(len(df_with_signal) - bars_back, len(df_with_signal)):
                if df_with_signal.iloc[i]["trend"] != 0:
                    results.append(
                        {
                            "exchange": exchange_name,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "trend": df_with_signal.iloc[i]["trend"],
                            "support": df_with_signal.iloc[i]["support"],
                            "resistance": df_with_signal.iloc[i]["resistance"],
                            "signal_time": df_with_signal.index[i],
                        }
                    )

    return results
