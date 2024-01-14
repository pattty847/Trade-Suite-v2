from typing import Dict
import pandas as pd
import pandas_ta as pta
import numpy as np


def calculate_indicators(
    exchange_id: str, symbol: str, timeframe: str, data: pd.DataFrame, csv: bool
):

    base, quote = symbol.split("/")

    base_volume_title = f"Base Volume {base}"
    quote_volume_title = f"Quote Volume {quote}"

    data.rename(columns={"volumes": base_volume_title}, inplace=True)

    # Quote volume
    data[quote_volume_title] = (data[base_volume_title] * data["closes"]).apply(
        lambda x: "{:,.2f}".format(x)
    )

    data = ITrend(data)

    # Compute log returns
    data["LOG_RETURN"] = np.log(data["closes"] / data["closes"].shift(1))
    data.insert(data.columns.get_loc("closes") + 1, "LOG_RETURNS", data["LOG_RETURN"])

    data["CUM_LOG_RETURN"] = data["LOG_RETURN"].cumsum()
    data.insert(
        data.columns.get_loc("LOG_RETURNS") + 1,
        "CUM_LOG_RETURNS",
        data["CUM_LOG_RETURN"],
    )

    pct_return = data["closes"].pct_change() * 100
    data.insert(data.columns.get_loc("closes") + 1, "PCT_RETURN", pct_return)

    data["HULL-55"] = hull_moving_average(
        data, 55, insert_next_to="CUM_LOG_RETURN"
    )
    data["HULL-180"] = hull_moving_average(data, 180, insert_next_to="HULL_55")

    data.insert(data.columns.get_loc("CUM_LOG_RETURN") + 1, "HULL_55", data["HULL-55"])
    data.insert(data.columns.get_loc("HULL_55") + 1, "HULL_180", data["HULL-180"])

    data.insert(
        data.columns.get_loc("HULL_180") + 1,
        "HULL_55_TREND",
        np.where(data["HULL_55"] >= data["HULL_55"].shift(1), "Bull", "Bear"),
    )
    data.insert(
        data.columns.get_loc("HULL_55_TREND") + 1,
        "HULL_180_TREND",
        np.where(data["HULL_180"] >= data["HULL_180"].shift(1), "Bull", "Bear"),
    )

    data.drop(
        columns=["LOG_RETURN", "CUM_LOG_RETURN", "HULL-55", "HULL-180"],
        inplace=True,
    )

    # Calculate the moving averages.
    data["SMA_20"] = data["closes"].rolling(window=20).mean()  # 20-day SMA
    data["SMA_50"] = data["closes"].rolling(window=50).mean()  # 50-day SMA
    data["SMA_100"] = data["closes"].rolling(window=100).mean()  # 50-day SMA
    data["SMA_200"] = data["closes"].rolling(window=200).mean()  # 200-day SMA

    # Determine the trend.
    data["SMA_Short_Term_Trend"] = data["SMA_20"] > data["SMA_50"]
    data["SMA_Long_Term_Trend"] = data["SMA_50"] > data["SMA_200"]

    data["SMA_Short_Term_Trend"] = data["SMA_Short_Term_Trend"].apply(
        lambda x: "Bull" if x else "Bear"
    )
    data["SMA_Long_Term_Trend"] = data["SMA_Long_Term_Trend"].apply(
        lambda x: "Bull" if x else "Bear"
    )

    data["SMA_Trend_Strength"] = abs(data["SMA_20"] - data["SMA_50"])
    data["SMA_Trend_Strength"] = pd.cut(
        data["SMA_Trend_Strength"],
        bins=5,
        labels=["Neutral", "Weak", "Moderate", "Strong", "Very Strong"],
    )

    # Calculate the moving averages.
    data["EMA_20"] = data["closes"].ewm(span=20, adjust=False).mean()
    data["EMA_50"] = data["closes"].ewm(span=50, adjust=False).mean()
    data["EMA_100"] = data["closes"].ewm(span=100, adjust=False).mean()
    data["EMA_200"] = data["closes"].ewm(span=200, adjust=False).mean()

    # Determine the trend.
    data["EMA_Short_Term_Trend"] = data["EMA_20"] > data["EMA_50"]
    data["EMA_Long_Term_Trend"] = data["EMA_50"] > data["EMA_200"]

    data["EMA_Short_Term_Trend"] = data["EMA_Short_Term_Trend"].apply(
        lambda x: "Bull" if x else "Bear"
    )
    data["EMA_Long_Term_Trend"] = data["EMA_Long_Term_Trend"].apply(
        lambda x: "Bull" if x else "Bear"
    )

    data["EMA_Trend_Strength"] = abs(data["EMA_20"] - data["EMA_50"])
    data["EMA_Trend_Strength"] = pd.cut(
        data["EMA_Trend_Strength"],
        bins=5,
        labels=["Neutral", "Weak", "Moderate", "Strong", "Very Strong"],
    )

    data.dropna(inplace=True)

    save_symbol = symbol.replace("/", "-")
    data.to_csv(f"{exchange_id} - {save_symbol} - {timeframe}.csv") if csv else None

    return data

def ITrend(data: pd.DataFrame, window: int = 10):
    price = data["closes"]
    value1 = pd.Series(np.zeros(len(price)), index=price.index)
    value2 = pd.Series(np.zeros(len(price)), index=price.index)
    trendline = pd.Series(np.zeros(len(price)), index=price.index)
    smooth_price = pd.Series(np.zeros(len(price)), index=price.index)

    for i in range(3, len(price)):
        value1[i] = (
            0.0542 * price[i]
            + 0.021 * price[i - 1]
            + 0.021 * price[i - 2]
            + 0.0542 * price[i - 3]
            + 1.9733 * value1[i - 1]
            - 1.6067 * value1[i - 2]
            + 0.4831 * value1[i - 3]
        )

        value2[i] = (
            0.8
            * (
                value1[i]
                - 2 * np.cos(np.deg2rad(360 / window)) * value1[i - 1]
                + value1[i - 2]
            )
            + 1.6 * np.cos(np.deg2rad(360 / window)) * value2[i - 1]
            - 0.6 * value2[i - 2]
        )

        trendline[i] = (
            0.9
            * (
                value2[i]
                - 2 * np.cos(np.deg2rad(360 / window)) * value2[i - 1]
                + value2[i - 2]
            )
            + 1.8 * np.cos(np.deg2rad(360 / window)) * trendline[i - 1]
            - 0.8 * trendline[i - 2]
        )

        smooth_price[i] = (
            4 * price[i] + 3 * price[i - 1] + 2 * price[i - 2] + price[i - 3]
        ) / 10

    data["Trendline"] = trendline
    data["SmoothPrice"] = smooth_price
    return data

# Let's define a helper function to calculate WMA
def weighted_moving_average(data: pd.DataFrame, period: int, column="closes"):
    weights = np.arange(1, period + 1)
    return (
        data[column]
        .rolling(period)
        .apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    )

def hull_moving_average(data: pd.DataFrame, period: int, column="closes"):
    # Calculate the square root of the period
    sqrt_period = int(np.sqrt(period))

    # Calculate the WMA for period n/2
    half_period_wma = weighted_moving_average(
        data, int(period / 2), column=column
    )

    # Calculate the WMA for full period
    full_period_wma = weighted_moving_average(data, period, column=column)

    # Subtract half period WMA from full period WMA
    diff_wma = 2 * half_period_wma - full_period_wma

    # Create a DataFrame from diff_wma
    diff_wma_df = diff_wma.to_frame()

    # Use the column name of the diff_wma_df DataFrame for calculating the HMA
    hma = weighted_moving_average(
        diff_wma_df, sqrt_period, column=diff_wma_df.columns[0]
    )

    return hma


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
