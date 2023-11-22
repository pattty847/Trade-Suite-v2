import logging
from typing import Dict, List
import ccxt
import numpy as np
import pandas as pd

def get_highest_volume_symbols(exchange_id: str, top_x: int):
    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()

    ticker_info = exchange.fetch_tickers()

    # Prepare a list of tuples where each tuple is (symbol, 24h volume)
    # Only add to the list if quoteVolume is not None
    volume_list = [(symbol, ticker['quoteVolume']) for symbol, ticker in ticker_info.items() if ticker['quoteVolume'] is not None]

    # Sort the list by volume in descending order
    volume_list.sort(key=lambda x: x[1], reverse=True)

    # Return the symbols of the top X markets by volume
    return [symbol for symbol, volume in volume_list[:top_x]]

def create_correlation_heatmap(exchange_id: str):
    # Initialize a dictionary to hold our data.
    data = {}

    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()

    symbols = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'PEPE/USDT', 'SOL/USDT', 'XMR/USDT', 'BCH/USDT', 'TOMI/USDT', 'BNB/USDT', 'AAVE/USDT', 'SHIB/USDT', 'LINK/USDT', 'DOGE/USDT']

    # Fetch the closing prices for each symbol.
    for symbol in symbols:
        logging.info(f'Fetching {symbol}')
        ohlcv = exchange.fetch_ohlcv(symbol, '1h')  # Get daily data
        df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms')  # Convert timestamp to datetime
        data[symbol] = df['Close']

    # Create a DataFrame from our dictionary.
    df = pd.DataFrame(data)

    # Calculate the correlations.
    corr = df.corr()

    # Plot the correlations as a heatmap.
    plt.figure(figsize=(10,10))
    sns.heatmap(corr, annot=True, cmap='coolwarm')
    plt.show()

def create_dataframe(exchanges: List, symbols: List, timeframe: str):
    all_dataframes = {}
    for exchange_id in exchanges:
        for symbol in symbols:
            exchange = getattr(ccxt, exchange_id)()

            base, quote = symbol.split('/')

            base_volume_title = f'Base Volume {base}'
            quote_volume_title = f'Quote Volume {quote}'

            # Fetch daily OHLCV data. 1D denotes 1 day. You can adjust this as needed.
            data = exchange.fetch_ohlcv(symbol, timeframe)

            df = pd.DataFrame(data, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', base_volume_title])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms') # Convert timestamp to datetime.

            # Quote volume
            df[quote_volume_title] = (df[base_volume_title] * df['Close']).apply(lambda x: '{:,.2f}'.format(x))
            
            df = ITrend(df)
            
            # Compute log returns
            df['LOG_RETURN'] = np.log(df['Close'] / df['Close'].shift(1))
            df.insert(df.columns.get_loc('Close')+1, 'LOG_RETURNS', df['LOG_RETURN'])
            
            df['CUM_LOG_RETURN'] = df['LOG_RETURN'].cumsum()
            df.insert(df.columns.get_loc('LOG_RETURNS')+1, 'CUM_LOG_RETURNS', df['CUM_LOG_RETURN'])

            pct_return = df['Close'].pct_change() * 100
            df.insert(df.columns.get_loc('Close')+1, 'PCT_RETURN', pct_return)
            
            df['HULL-55'] = hull_moving_average(df, 55, insert_next_to='CUM_LOG_RETURN')
            df['HULL-180'] = hull_moving_average(df, 180, insert_next_to='HULL_55')
            
            df.insert(df.columns.get_loc('CUM_LOG_RETURN')+1, 'HULL_55', df['HULL-55'])
            df.insert(df.columns.get_loc('HULL_55')+1, 'HULL_180', df['HULL-180'])
            
            df.insert(df.columns.get_loc('HULL_180')+1, 'HULL_55_TREND', np.where(df['HULL_55'] >= df['HULL_55'].shift(1), 'Bull', 'Bear'))
            df.insert(df.columns.get_loc('HULL_55_TREND')+1, 'HULL_180_TREND', np.where(df['HULL_180'] >= df['HULL_180'].shift(1), 'Bull', 'Bear'))
            
            df.drop(columns=['LOG_RETURN', 'CUM_LOG_RETURN', 'HULL-55', 'HULL-180'], inplace=True)

            # Calculate the moving averages.
            df['SMA_20'] = df['Close'].rolling(window=20).mean() # 20-day SMA
            df['SMA_50'] = df['Close'].rolling(window=50).mean() # 50-day SMA
            df['SMA_100'] = df['Close'].rolling(window=100).mean() # 50-day SMA
            df['SMA_200'] = df['Close'].rolling(window=200).mean() # 200-day SMA

            # Determine the trend.
            df['SMA_Short_Term_Trend'] = df['SMA_20'] > df['SMA_50']
            df['SMA_Long_Term_Trend'] = df['SMA_50'] > df['SMA_200']

            df['SMA_Short_Term_Trend'] = df['SMA_Short_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')
            df['SMA_Long_Term_Trend'] = df['SMA_Long_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')

            df['SMA_Trend_Strength'] = abs(df['SMA_20'] - df['SMA_50'])
            df['SMA_Trend_Strength'] = pd.cut(df['SMA_Trend_Strength'], bins=5, labels=['Neutral', 'Weak', 'Moderate', 'Strong', 'Very Strong'])

            # Calculate the moving averages.
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['EMA_100'] = df['Close'].ewm(span=100, adjust=False).mean()
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

            # Determine the trend.
            df['EMA_Short_Term_Trend'] = df['EMA_20'] > df['EMA_50']
            df['EMA_Long_Term_Trend'] = df['EMA_50'] > df['EMA_200']

            df['EMA_Short_Term_Trend'] = df['EMA_Short_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')
            df['EMA_Long_Term_Trend'] = df['EMA_Long_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')

            df['EMA_Trend_Strength'] = abs(df['EMA_20'] - df['EMA_50'])
            df['EMA_Trend_Strength'] = pd.cut(df['EMA_Trend_Strength'], bins=5, labels=['Neutral', 'Weak', 'Moderate', 'Strong', 'Very Strong'])
            
            df.dropna(inplace=True)

            save_symbol = symbol.replace('/', '-')
            df.to_csv(f'{exchange_id} - {save_symbol} - {timeframe}.csv')

            all_dataframes[(exchange_id, symbol)] = df

    return all_dataframes

def ITrend(data, window=10):
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
        
    price = data['Close']
    value1 = pd.Series(np.zeros(len(price)), index=price.index)
    value2 = pd.Series(np.zeros(len(price)), index=price.index)
    trendline = pd.Series(np.zeros(len(price)), index=price.index)
    smooth_price = pd.Series(np.zeros(len(price)), index=price.index)

    for i in range(3, len(price)):
        value1[i] = 0.0542 * price[i] + 0.021 * price[i - 1] + 0.021 * price[i - 2] + 0.0542 * price[i - 3] + \
                    1.9733 * value1[i - 1] - 1.6067 * value1[i - 2] + 0.4831 * value1[i - 3]
        
        value2[i] = 0.8 * (value1[i] - 2 * np.cos(np.deg2rad(360 / window)) * value1[i - 1] + value1[i - 2]) + \
                    1.6 * np.cos(np.deg2rad(360 / window)) * value2[i - 1] - 0.6 * value2[i - 2]
        
        trendline[i] = 0.9 * (value2[i] - 2 * np.cos(np.deg2rad(360 / window)) * value2[i - 1] + value2[i - 2]) + \
                       1.8 * np.cos(np.deg2rad(360 / window)) * trendline[i - 1] - 0.8 * trendline[i - 2]
        
        smooth_price[i] = (4 * price[i] + 3 * price[i - 1] + 2 * price[i - 2] + price[i - 3]) / 10

    data['Trendline'] = trendline
    data['SmoothPrice'] = smooth_price
    return data

# Let's define a helper function to calculate WMA
def weighted_moving_average(data, period, column='Close'):
    weights = np.arange(1, period + 1)
    return data[column].rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def hull_moving_average(data, period, insert_next_to, column='Close'):
    # Calculate the square root of the period
    sqrt_period = int(np.sqrt(period))
    
    # Calculate the WMA for period n/2
    half_period_wma = weighted_moving_average(data, int(period/2), column=column)
    
    # Calculate the WMA for full period
    full_period_wma = weighted_moving_average(data, period, column=column)
    
    # Subtract half period WMA from full period WMA
    diff_wma = 2 * half_period_wma - full_period_wma
    
    # Create a DataFrame from diff_wma
    diff_wma_df = diff_wma.to_frame()
    
    # Use the column name of the diff_wma_df DataFrame for calculating the HMA
    hma = weighted_moving_average(diff_wma_df, sqrt_period, column=diff_wma_df.columns[0])
    
    return hma

def calculate_exhaustion(df, show_sr=True, swing_len=40, bars_back=4, bar_count=10, src='close'):
    # Initialize the counters and return values
    df['bullCount'] = 0
    df['bearCount'] = 0
    df['trend'] = 0
    df['resistance'] = pd.NA
    df['support'] = pd.NA

    # Calculate bull and bear counts
    df['bullCount'] = df[src].gt(df[src].shift(bars_back)).cumsum()
    df['bearCount'] = df[src].lt(df[src].shift(bars_back)).cumsum()
    
    # Identify exhaustion points
    df['lowest'] = df['low'].rolling(window=swing_len).min()
    df['highest'] = df['high'].rolling(window=swing_len).max()
    
    # Set trend values based on exhaustion points
    df.loc[(df['bullCount'] >= bar_count) & (df['close'] < df['open']) & (df['high'] >= df['highest']), 'trend'] = -1
    df.loc[(df['bearCount'] >= bar_count) & (df['close'] > df['open']) & (df['low'] <= df['lowest']), 'trend'] = 1

    # Reset count when conditions are met
    df.loc[df['bullCount'] >= bar_count, 'bullCount'] = 0
    df.loc[df['bearCount'] >= bar_count, 'bearCount'] = 0

    # Calculate Support and Resistance without shifting
    df.loc[(df['close'] < df['open']) & (df['trend'] == -1), 'resistance'] = df['high']
    df.loc[(df['close'] > df['open']) & (df['trend'] == 1), 'support'] = df['low']
    df['resistance'] = df['resistance'].ffill().shift(1)
    df['support'] = df['support'].ffill().shift(1)

    # Return only the necessary columns
    return df


def scan_multiple_assets(all_candles, bars_back=25, hyperparam=False):
    """
    The scan_multiple_assets function takes a dictionary of dataframes, and returns a list of dictionaries.
    Each dictionary in the returned list contains information about an asset that has triggered an exhaustion signal.
    The function will only return signals that have occurred within the last 'bars_back' bars.
    
    :param all_candles: Pass the dataframe containing all candles to the function
    :param bars_back: Specify how many bars back in time we want to check for a signal
    :param hyperparam: Determine whether the function is being used to scan for hyperparameters or not
    :return: A list of dictionaries
    :doc-author: Trelent
    """
    results = []

    for exchange_name, candles in all_candles.items():
        for key, df in candles.items():
            symbol, timeframe = key.split('-')
            df_with_signal = calculate_exhaustion(df)

            # Check if there was a signal 'bars_back' bars ago
            if df_with_signal.iloc[-bars_back]['trend'] != 0:
                results.append({
                    'exchange': exchange_name,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'trend': df_with_signal.iloc[-bars_back]['trend'],
                    'signal_time': df_with_signal.index[-bars_back]
                })
    
    return results