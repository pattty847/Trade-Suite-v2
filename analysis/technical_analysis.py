import pandas as pd
import pandas_ta as pta
import numpy as np

class TA:
    def __init__(self) -> None:
        pass
    
    def calculate_indicators(self, exchange_id: str, symbol: str, timeframe: str, df: dict, csv: bool):
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
            
        base, quote = symbol.split('/')

        base_volume_title = f'Base Volume {base}'
        quote_volume_title = f'Quote Volume {quote}'
        
        df.rename(columns={'volumes': base_volume_title}, inplace=True)

        # Quote volume
        df[quote_volume_title] = (df[base_volume_title] * df['closes']).apply(lambda x: '{:,.2f}'.format(x))
        
        df = self.ITrend(df)
        
        # Compute log returns
        df['LOG_RETURN'] = np.log(df['closes'] / df['closes'].shift(1))
        df.insert(df.columns.get_loc('closes')+1, 'LOG_RETURNS', df['LOG_RETURN'])
        
        df['CUM_LOG_RETURN'] = df['LOG_RETURN'].cumsum()
        df.insert(df.columns.get_loc('LOG_RETURNS')+1, 'CUM_LOG_RETURNS', df['CUM_LOG_RETURN'])

        pct_return = df['closes'].pct_change() * 100
        df.insert(df.columns.get_loc('closes')+1, 'PCT_RETURN', pct_return)
        
        df['HULL-55'] = self.hull_moving_average(df, 55, insert_next_to='CUM_LOG_RETURN')
        df['HULL-180'] = self.hull_moving_average(df, 180, insert_next_to='HULL_55')
        
        df.insert(df.columns.get_loc('CUM_LOG_RETURN')+1, 'HULL_55', df['HULL-55'])
        df.insert(df.columns.get_loc('HULL_55')+1, 'HULL_180', df['HULL-180'])
        
        df.insert(df.columns.get_loc('HULL_180')+1, 'HULL_55_TREND', np.where(df['HULL_55'] >= df['HULL_55'].shift(1), 'Bull', 'Bear'))
        df.insert(df.columns.get_loc('HULL_55_TREND')+1, 'HULL_180_TREND', np.where(df['HULL_180'] >= df['HULL_180'].shift(1), 'Bull', 'Bear'))
        
        df.drop(columns=['LOG_RETURN', 'CUM_LOG_RETURN', 'HULL-55', 'HULL-180'], inplace=True)

        # Calculate the moving averages.
        df['SMA_20'] = df['closes'].rolling(window=20).mean() # 20-day SMA
        df['SMA_50'] = df['closes'].rolling(window=50).mean() # 50-day SMA
        df['SMA_100'] = df['closes'].rolling(window=100).mean() # 50-day SMA
        df['SMA_200'] = df['closes'].rolling(window=200).mean() # 200-day SMA

        # Determine the trend.
        df['SMA_Short_Term_Trend'] = df['SMA_20'] > df['SMA_50']
        df['SMA_Long_Term_Trend'] = df['SMA_50'] > df['SMA_200']

        df['SMA_Short_Term_Trend'] = df['SMA_Short_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')
        df['SMA_Long_Term_Trend'] = df['SMA_Long_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')

        df['SMA_Trend_Strength'] = abs(df['SMA_20'] - df['SMA_50'])
        df['SMA_Trend_Strength'] = pd.cut(df['SMA_Trend_Strength'], bins=5, labels=['Neutral', 'Weak', 'Moderate', 'Strong', 'Very Strong'])

        # Calculate the moving averages.
        df['EMA_20'] = df['closes'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['closes'].ewm(span=50, adjust=False).mean()
        df['EMA_100'] = df['closes'].ewm(span=100, adjust=False).mean()
        df['EMA_200'] = df['closes'].ewm(span=200, adjust=False).mean()

        # Determine the trend.
        df['EMA_Short_Term_Trend'] = df['EMA_20'] > df['EMA_50']
        df['EMA_Long_Term_Trend'] = df['EMA_50'] > df['EMA_200']

        df['EMA_Short_Term_Trend'] = df['EMA_Short_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')
        df['EMA_Long_Term_Trend'] = df['EMA_Long_Term_Trend'].apply(lambda x: 'Bull' if x else 'Bear')

        df['EMA_Trend_Strength'] = abs(df['EMA_20'] - df['EMA_50'])
        df['EMA_Trend_Strength'] = pd.cut(df['EMA_Trend_Strength'], bins=5, labels=['Neutral', 'Weak', 'Moderate', 'Strong', 'Very Strong'])
        
        df.dropna(inplace=True)

        save_symbol = symbol.replace('/', '-')
        df.to_csv(f'{exchange_id} - {save_symbol} - {timeframe}.csv') if csv else None

        return df
    
    def ITrend(self, data, window=10):
        price = data['closes']
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
    def weighted_moving_average(self, data, period, column='closes'):
        weights = np.arange(1, period + 1)
        return data[column].rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    def hull_moving_average(self, data, period, insert_next_to, column='closes'):
        # Calculate the square root of the period
        sqrt_period = int(np.sqrt(period))
        
        # Calculate the WMA for period n/2
        half_period_wma = self.weighted_moving_average(data, int(period/2), column=column)
        
        # Calculate the WMA for full period
        full_period_wma = self.weighted_moving_average(data, period, column=column)
        
        # Subtract half period WMA from full period WMA
        diff_wma = 2 * half_period_wma - full_period_wma
        
        # Create a DataFrame from diff_wma
        diff_wma_df = diff_wma.to_frame()
        
        # Use the column name of the diff_wma_df DataFrame for calculating the HMA
        hma = self.weighted_moving_average(diff_wma_df, sqrt_period, column=diff_wma_df.columns[0])
        
        return hma