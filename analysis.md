Warning: Not enough data in data/cache\coinbase_WLD-USD_1d.csv to calculate all indicators (have 12, need 50). Skipping.

--- All Processed Symbols & Indicators (before filtering) ---
|    | exchange   | symbol     | timeframe   |          close |     RSI |   zscore |          %B |   ATRstretch |    VWAPgap |
|---:|:-----------|:-----------|:------------|---------------:|--------:|---------:|------------:|-------------:|-----------:|
|  0 | coinbase   | ADA-USD    | 1d          |      0.8067    | 65.7479 | 2.29222  | -0.0459193  |     1.8413   |  0.085224  |
|  1 | coinbase   | ARB-USD    | 1d          |      0.4504    | 70.5087 | 2.84185  |  0.296504   |     3.17046  | -0.519102  |
|  2 | coinbase   | BONK-USD   | 1d          |      2.192e-05 | 65.1073 | 1.95697  | -0.394768   |     1.5544   | -0.1498    |
|  3 | coinbase   | BTC-USD    | 1d          | 104353         | 74.9957 | 2.14512  | -0.00541383 |     2.74627  |  0.448464  |
|  4 | coinbase   | DOGE-USD   | 1d          |      0.23055   | 69.1054 | 2.96244  |  0.154912   |     2.83407  |  0.077781  |
|  5 | coinbase   | ETH-USD    | 1d          |   2506.55      | 79.2079 | 2.98781  |  0.274319   |     4.29239  | -0.117087  |
|  6 | coinbase   | JASMY-USD  | 1d          |      0.01905   | 64.7677 | 1.71017  | -0.143243   |     1.36427  | -0.18935   |
|  7 | coinbase   | NEAR-USD   | 1d          |      3.13      | 66.2231 | 2.04996  |  0.0171326  |     2.49504  | -0.382501  |
|  8 | coinbase   | OP-USD     | 1d          |      0.863     | 61.8557 | 1.51069  | -0.486507   |     1.75197  | -0.621698  |
|  9 | coinbase   | PEPE-USD   | 1d          |      1.35e-05  | 81.4442 | 3.36997  |  0.341874   |     3.78336  | -0.0857201 |
| 10 | coinbase   | RENDER-USD | 1d          |      5.197     | 63.8085 | 1.97116  | -0.0423476  |     1.58012  | -0.115912  |
| 11 | coinbase   | SEI-USD    | 1d          |      0.2578    | 67.8915 | 2.39508  | -0.0240472  |     2.58749  | -0.506195  |
| 12 | coinbase   | SHIB-USD   | 1d          |      1.589e-05 | 65.8728 | 2.52427  | -0.123105   |     2.13357  | -0.31678   |
| 13 | coinbase   | SOL-USD    | 1d          |    172.4       | 70.1682 | 2.12338  | -0.0519686  |     2.231    |  0.0820238 |
| 14 | coinbase   | SUI-USD    | 1d          |      4.0132    | 70.3675 | 1.88535  | -0.266431   |     1.66697  |  0.605344  |
| 15 | coinbase   | TIA-USD    | 1d          |      3.183     | 62.8796 | 0.963993 | -0.278181   |     1.80113  | -0.539353  |
| 16 | coinbase   | WIF-USD    | 1d          |      0.892     | 73.5883 | 2.8417   |  0.227343   |     3.24825  | -0.121756  |
| 17 | coinbase   | XCN-USD    | 1d          |      0.01783   | 51.9492 | 0.554648 | -0.845617   |     0.325581 |  0.198446  |
| 18 | coinbase   | XRP-USD    | 1d          |      2.3726    | 60.2053 | 1.44526  | -0.260209   |     1.18386  |  0.46723   |
-----------------------------------------------------------


--- Evaluating Scan: Overbought_Extreme_V1 ---
Description: Looks for symbols that are highly overbought on multiple indicators.
Minimum flags to pass: 2

Symbols meeting criteria for scan: 'Overbought_Extreme_V1'
|    | exchange   | symbol   | timeframe   |       close |     RSI |   zscore |       %B |   ATRstretch |    VWAPgap |   flags_met |
|---:|:-----------|:---------|:------------|------------:|--------:|---------:|---------:|-------------:|-----------:|------------:|
|  5 | coinbase   | ETH-USD  | 1d          | 2506.55     | 79.2079 |  2.98781 | 0.274319 |      4.29239 | -0.117087  |           3 |
|  9 | coinbase   | PEPE-USD | 1d          |    1.35e-05 | 81.4442 |  3.36997 | 0.341874 |      3.78336 | -0.0857201 |           3 |
|  1 | coinbase   | ARB-USD  | 1d          |    0.4504   | 70.5087 |  2.84185 | 0.296504 |      3.17046 | -0.519102  |           2 |
| 16 | coinbase   | WIF-USD  | 1d          |    0.892    | 73.5883 |  2.8417  | 0.227343 |      3.24825 | -0.121756  |           2 |
Scan 'Potential_Mean_Reversion_Short' is disabled. Skipping.

--- Evaluating Scan: Oversold_Interest ---
Description: Looks for potentially oversold conditions.
Minimum flags to pass: 1

Symbols meeting criteria for scan: 'Oversold_Interest'
|    | exchange   | symbol     | timeframe   |        close |     RSI |   zscore |         %B |   ATRstretch |    VWAPgap |   flags_met |
|---:|:-----------|:-----------|:------------|-------------:|--------:|---------:|-----------:|-------------:|-----------:|------------:|
|  1 | coinbase   | ARB-USD    | 1d          |    0.4504    | 70.5087 | 2.84185  |  0.296504  |      3.17046 | -0.519102  |           1 |
|  2 | coinbase   | BONK-USD   | 1d          |    2.192e-05 | 65.1073 | 1.95697  | -0.394768  |      1.5544  | -0.1498    |           1 |
|  5 | coinbase   | ETH-USD    | 1d          | 2506.55      | 79.2079 | 2.98781  |  0.274319  |      4.29239 | -0.117087  |           1 |
|  6 | coinbase   | JASMY-USD  | 1d          |    0.01905   | 64.7677 | 1.71017  | -0.143243  |      1.36427 | -0.18935   |           1 |
|  7 | coinbase   | NEAR-USD   | 1d          |    3.13      | 66.2231 | 2.04996  |  0.0171326 |      2.49504 | -0.382501  |           1 |
|  8 | coinbase   | OP-USD     | 1d          |    0.863     | 61.8557 | 1.51069  | -0.486507  |      1.75197 | -0.621698  |           1 |
|  9 | coinbase   | PEPE-USD   | 1d          |    1.35e-05  | 81.4442 | 3.36997  |  0.341874  |      3.78336 | -0.0857201 |           1 |
| 10 | coinbase   | RENDER-USD | 1d          |    5.197     | 63.8085 | 1.97116  | -0.0423476 |      1.58012 | -0.115912  |           1 |
| 11 | coinbase   | SEI-USD    | 1d          |    0.2578    | 67.8915 | 2.39508  | -0.0240472 |      2.58749 | -0.506195  |           1 |
| 12 | coinbase   | SHIB-USD   | 1d          |    1.589e-05 | 65.8728 | 2.52427  | -0.123105  |      2.13357 | -0.31678   |           1 |
| 15 | coinbase   | TIA-USD    | 1d          |    3.183     | 62.8796 | 0.963993 | -0.278181  |      1.80113 | -0.539353  |           1 |
| 16 | coinbase   | WIF-USD    | 1d          |    0.892     | 73.5883 | 2.8417   |  0.227343  |      3.24825 | -0.121756  |           1 |
