Analysis workflow starting for timeframe: 5m
Starting data fetch/update for coinbase, timeframe: 5m, since: 2024-01-01T00:00:00Z
Fetching symbols from predefined group 'majors': ['PEPE/USD']
Ensuring BTC/USD is included in fetch list for BTC relative analysis.
Proceeding to fetch/update candles for 2 symbols: ['PEPE/USD', 'BTC/USD']
Candle data fetching/updating complete.
Closing exchange connections after fetching...
Exchange connections closed.
Data fetching targeted 2 symbol(s). Scan will focus on these if found.
Starting folder scan for timeframe: 5m...
Scanning for timeframe: 5m in path: data/cache/*.csv, focusing on 2 specific symbol(s).
Successfully loaded Bitcoin data for relative analysis from: data/cache\coinbase_BTC-USD_5m.csv
Processing: coinbase_BTC-USD_5m.csv (Exchange: coinbase, Symbol: BTC-USD, Parsed TF: 5m)
Processing: coinbase_PEPE-USD_5m.csv (Exchange: coinbase, Symbol: PEPE-USD, Parsed TF: 5m)
Finished scanning. Processed 2 files for the specified criteria.
Calculating deltas from previous run...
Delta calculation complete.
Current results saved to results_last.parquet for next run.

--- All Processed Symbols & Indicators (before scan filtering) ---
| exchange   | symbol   | timeframe   |       %B |     ADX |   ATRstretch |       BBW |   BTC_rel_zscore |     RSI |     RVOL |     VWAPgap |   VWAPgap_daily |   VolumeZScore |          close |   delta_%B |   delta_ADX |   delta_ATRstretch |   delta_BBW |   delta_BTC_rel_zscore |   delta_RSI |   delta_RVOL |   delta_VWAPgap |   delta_VWAPgap_daily |   delta_VolumeZScore |   delta_zscore |       volume |    zscore |
|:-----------|:---------|:------------|---------:|--------:|-------------:|----------:|-----------------:|--------:|---------:|------------:|----------------:|---------------:|---------------:|-----------:|------------:|-------------------:|------------:|-----------------------:|------------:|-------------:|----------------:|----------------------:|---------------------:|---------------:|-------------:|----------:|
| coinbase   | BTC-USD  | 5m          | 0.531138 | 42.024  |     0.218812 | 0.0205712 |       nan        | 47.6856 | 0.344367 | -0.0158557  |      -0.0167516 |       -1.11687 | 101952         |  0.0776742 |    -4.07183 |          -0.139646 | -0.00426222 |             nan        |     1.03539 |     0.166155 |     0.000514588 |           0.000637951 |             0.149053 |       0.17937  | 21.6894      | -0.866197 |
| coinbase   | PEPE-USD | 5m          | 0.674426 | 44.3627 |     1.00171  | 0.0610134 |        -0.598446 | 50.8531 | 0.349373 |  0.00339732 |      -0.059505  |       -0.99685 |      1.339e-05 |  0.263879  |    -5.99695 |           0.351557 | -0.019641   |               0.767767 |     7.98278 |    -0.294513 |     0.0128101   |           0.0131756   |            -0.495594 |       0.640065 |  1.38368e+10 | -0.673629 |
-----------------------------------------------------------


--- Evaluating Scan: Overbought_Extreme_V1 ---
Description: Looks for symbols that are highly overbought on multiple indicators.
Minimum flags to pass: 2
No symbols met the criteria for scan: 'Overbought_Extreme_V1'.

--- Evaluating Scan: Potential_Mean_Reversion_Short ---
Description: Similar to Overbought_Extreme_V1 but might use slightly different thresholds or fewer flags.
Minimum flags to pass: 1
No symbols met the criteria for scan: 'Potential_Mean_Reversion_Short'.

--- Evaluating Scan: Oversold_Interest ---
Description: Looks for potentially oversold conditions.
Minimum flags to pass: 1
No symbols met the criteria for scan: 'Oversold_Interest'.

--- Evaluating Scan: BTC_Strong_Outperformers ---
Description: Looks for symbols significantly outperforming Bitcoin and showing own strength.
Minimum flags to pass: 2
No symbols met the criteria for scan: 'BTC_Strong_Outperformers'.

--- Evaluating Scan: BTC_Potential_Catch_Up ---
Description: Looks for symbols that might be starting to outperform BTC after a period of underperformance, or are showing general strength aligned with BTC.
Minimum flags to pass: 2

Symbols meeting criteria for scan: 'BTC_Potential_Catch_Up'
| exchange   | symbol   | timeframe   |     close |      volume |     RSI |    zscore |       %B |   ATRstretch |    VWAPgap |   VWAPgap_daily |   BTC_rel_zscore |   VolumeZScore |     RVOL |       BBW |     ADX |   delta_RSI |   delta_zscore |   delta_RVOL |   delta_VWAPgap |   delta_VWAPgap_daily |   delta_BBW |   delta_BTC_rel_zscore |   delta_VolumeZScore |   delta_%B |   delta_ATRstretch |   delta_ADX |   flags_met |
|:-----------|:---------|:------------|----------:|------------:|--------:|----------:|---------:|-------------:|-----------:|----------------:|-----------------:|---------------:|---------:|----------:|--------:|------------:|---------------:|-------------:|----------------:|----------------------:|------------:|-----------------------:|---------------------:|-----------:|-------------------:|------------:|------------:|
| coinbase   | PEPE-USD | 5m          | 1.339e-05 | 1.38368e+10 | 50.8531 | -0.673629 | 0.674426 |      1.00171 | 0.00339732 |       -0.059505 |        -0.598446 |       -0.99685 | 0.349373 | 0.0610134 | 44.3627 |     7.98278 |       0.640065 |    -0.294513 |       0.0128101 |             0.0131756 |   -0.019641 |               0.767767 |            -0.495594 |   0.263879 |           0.351557 |    -5.99695 |           2 |

--- Evaluating Scan: BTC_Extreme_Underperformers ---
Description: Looks for symbols significantly underperforming Bitcoin. Could be for fading or bottom fishing if other metrics align.
Minimum flags to pass: 1
No symbols met the criteria for scan: 'BTC_Extreme_Underperformers'.

--- Evaluating Scan: Volatility_Squeeze_Alert ---
Description: Identifies symbols with very low Bollinger Band Width, indicating a potential for a volatility expansion.
Minimum flags to pass: 1

Symbols meeting criteria for scan: 'Volatility_Squeeze_Alert'
| exchange   | symbol   | timeframe   |   close |   volume |     RSI |    zscore |       %B |   ATRstretch |    VWAPgap |   VWAPgap_daily |   BTC_rel_zscore |   VolumeZScore |     RVOL |       BBW |    ADX |   delta_RSI |   delta_zscore |   delta_RVOL |   delta_VWAPgap |   delta_VWAPgap_daily |   delta_BBW |   delta_BTC_rel_zscore |   delta_VolumeZScore |   delta_%B |   delta_ATRstretch |   delta_ADX |   flags_met |
|:-----------|:---------|:------------|--------:|---------:|--------:|----------:|---------:|-------------:|-----------:|----------------:|-----------------:|---------------:|---------:|----------:|-------:|------------:|---------------:|-------------:|----------------:|----------------------:|------------:|-----------------------:|---------------------:|-----------:|-------------------:|------------:|------------:|
| coinbase   | BTC-USD  | 5m          |  101952 |  21.6894 | 47.6856 | -0.866197 | 0.531138 |     0.218812 | -0.0158557 |      -0.0167516 |              nan |       -1.11687 | 0.344367 | 0.0205712 | 42.024 |     1.03539 |        0.17937 |     0.166155 |     0.000514588 |           0.000637951 | -0.00426222 |                    nan |             0.149053 |  0.0776742 |          -0.139646 |    -4.07183 |           1 |
