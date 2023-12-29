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
