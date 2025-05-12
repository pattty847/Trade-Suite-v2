Analysis workflow starting for timeframe: 5m
Starting data fetch/update for coinbase, timeframe: 5m, since: 2025-01-01T00:00:00Z
Fetching top 20 symbols from coinbase by USD volume (field: volume_24h)...
Fetching markets from coinbase...
Fetched 954 markets from coinbase.
Ensuring BTC/USD is included in fetch list for BTC relative analysis.
Proceeding to fetch/update candles for 21 symbols: ['PEPE/USD', 'MOG/USD', 'BONK/USD', 'SHIB/USD', 'TOSHI/USD', 'FLOKI/USD', 'DOGINME/USD', 'MOODENG/USD', 'KEYCAT/USD', 'SPELL/USD', 'MOBILE/USD', 'B3/USD', 'TURBO/USD', 'DEGEN/USD', 'XCN/USD', 'ZORA/USD', 'PENGU/USD', 'DOGE/USD', 'JASMY/USD', 'HONEY/USD', 'BTC/USD']
Candle data fetching/updating complete.
Closing exchange connections after fetching...
Exchange connections closed.
Data fetching targeted 21 symbol(s). Scan will focus on these if found.
Starting folder scan for timeframe: 5m...
Scanning for timeframe: 5m in path: data/cache/*.csv, focusing on 21 specific symbol(s).
Successfully loaded Bitcoin data for relative analysis from: data/cache\coinbase_BTC-USD_5m.csv
Processing: coinbasepro_BTC-USD_5m.csv (Exchange: coinbasepro, Symbol: BTC-USD, Parsed TF: 5m)
Processing: coinbase_B3-USD_5m.csv (Exchange: coinbase, Symbol: B3-USD, Parsed TF: 5m)
Processing: coinbase_BONK-USD_5m.csv (Exchange: coinbase, Symbol: BONK-USD, Parsed TF: 5m)
Processing: coinbase_BTC-USD_5m.csv (Exchange: coinbase, Symbol: BTC-USD, Parsed TF: 5m)
Processing: coinbase_DEGEN-USD_5m.csv (Exchange: coinbase, Symbol: DEGEN-USD, Parsed TF: 5m)
Processing: coinbase_DOGE-USD_5m.csv (Exchange: coinbase, Symbol: DOGE-USD, Parsed TF: 5m)
Processing: coinbase_DOGINME-USD_5m.csv (Exchange: coinbase, Symbol: DOGINME-USD, Parsed TF: 5m)
Processing: coinbase_FLOKI-USD_5m.csv (Exchange: coinbase, Symbol: FLOKI-USD, Parsed TF: 5m)
Processing: coinbase_HONEY-USD_5m.csv (Exchange: coinbase, Symbol: HONEY-USD, Parsed TF: 5m)
Processing: coinbase_JASMY-USD_5m.csv (Exchange: coinbase, Symbol: JASMY-USD, Parsed TF: 5m)
Processing: coinbase_KEYCAT-USD_5m.csv (Exchange: coinbase, Symbol: KEYCAT-USD, Parsed TF: 5m)
Processing: coinbase_MOBILE-USD_5m.csv (Exchange: coinbase, Symbol: MOBILE-USD, Parsed TF: 5m)
Processing: coinbase_MOG-USD_5m.csv (Exchange: coinbase, Symbol: MOG-USD, Parsed TF: 5m)
Processing: coinbase_MOODENG-USD_5m.csv (Exchange: coinbase, Symbol: MOODENG-USD, Parsed TF: 5m)
Processing: coinbase_PENGU-USD_5m.csv (Exchange: coinbase, Symbol: PENGU-USD, Parsed TF: 5m)
Processing: coinbase_PEPE-USD_5m.csv (Exchange: coinbase, Symbol: PEPE-USD, Parsed TF: 5m)
Processing: coinbase_SHIB-USD_5m.csv (Exchange: coinbase, Symbol: SHIB-USD, Parsed TF: 5m)
Processing: coinbase_SPELL-USD_5m.csv (Exchange: coinbase, Symbol: SPELL-USD, Parsed TF: 5m)
Processing: coinbase_TOSHI-USD_5m.csv (Exchange: coinbase, Symbol: TOSHI-USD, Parsed TF: 5m)
Processing: coinbase_TURBO-USD_5m.csv (Exchange: coinbase, Symbol: TURBO-USD, Parsed TF: 5m)
Processing: coinbase_XCN-USD_5m.csv (Exchange: coinbase, Symbol: XCN-USD, Parsed TF: 5m)
Processing: coinbase_ZORA-USD_5m.csv (Exchange: coinbase, Symbol: ZORA-USD, Parsed TF: 5m)
Processing: kraken_BTC-USD_5m.csv (Exchange: kraken, Symbol: BTC-USD, Parsed TF: 5m)
Finished scanning. Processed 23 files for the specified criteria.

--- All Processed Symbols & Indicators (before scan filtering) ---
|    | exchange    | symbol      | timeframe   |          close |     RSI |    zscore |         %B |   ATRstretch |     VWAPgap |   BTC_rel_zscore |
|---:|:------------|:------------|:------------|---------------:|--------:|----------:|-----------:|-------------:|------------:|-----------------:|
|  0 | coinbasepro | BTC-USD     | 5m          |  67363.8       | 57.7431 |  0.735155 | -0.632361  |    1.22989   |  0.0056555  |      nan         |
|  1 | coinbase    | B3-USD      | 5m          |      0.005948  | 48.0074 | -0.713965 | -1.32453   |    0.243192  | -0.0364637  |       -0.597077  |
|  2 | coinbase    | BONK-USD    | 5m          |      2.3e-05   | 62.5818 |  1.61771  | -0.194989  |    1.40836   |  0.15664    |        1.36965   |
|  3 | coinbase    | BTC-USD     | 5m          | 103948         | 47.8488 | -0.739975 | -0.834609  |    0.0502355 |  0.367427   |      nan         |
|  4 | coinbase    | DEGEN-USD   | 5m          |      0.004021  | 56.1559 |  0.902144 | -0.655885  |    0.853173  | -0.202711   |        0.549775  |
|  5 | coinbase    | DOGE-USD    | 5m          |      0.23776   | 59.6966 |  1.25674  | -0.0659958 |    0.988645  | -0.0541618  |        1.08625   |
|  6 | coinbase    | DOGINME-USD | 5m          |      0.0007354 | 42.3472 |  0.148719 | -1.21723   |    1.18132   |  0.0402669  |        0.251742  |
|  7 | coinbase    | FLOKI-USD   | 5m          |      0.0001093 | 61.624  |  1.66641  | -0.218866  |    1.27197   |  0.0846209  |        1.71024   |
|  8 | coinbase    | HONEY-USD   | 5m          |      0.0311    | 45.9725 | -0.376295 | -2.70931   |    0.709073  | -0.279662   |       -0.265072  |
|  9 | coinbase    | JASMY-USD   | 5m          |      0.01931   | 58.4819 |  1.40609  | -0.165553  |    1.26801   | -0.0705716  |        1.20337   |
| 10 | coinbase    | KEYCAT-USD  | 5m          |      0.0058    | 48.6891 |  0.663126 | -1.77628   |    0.678751  |  0.0857258  |        0.683371  |
| 11 | coinbase    | MOBILE-USD  | 5m          |      0.000507  | 45.8293 | -0.101576 | -2.10063   |    0.91846   | -0.606095   |        0.200543  |
| 12 | coinbase    | MOG-USD     | 5m          |      1.15e-06  | 48.1899 | -0.421284 | -2.0887    |    0.26346   |  0.238423   |       -0.237846  |
| 13 | coinbase    | MOODENG-USD | 5m          |      0.2777    | 54.4962 |  0.796913 | -0.496264  |    0.111714  |  1.66395    |        0.748743  |
| 14 | coinbase    | PENGU-USD   | 5m          |      0.01453   | 53.7828 |  0.965678 | -0.721007  |    0.242128  |  0.0185535  |        1.10119   |
| 15 | coinbase    | PEPE-USD    | 5m          |      1.44e-05  | 56.2662 |  0.900623 | -0.908834  |    0.0477595 |  0.384206   |        0.969908  |
| 16 | coinbase    | SHIB-USD    | 5m          |      1.622e-05 | 52.9046 |  0.647779 | -0.989652  |    0.0664055 | -0.019074   |        0.924466  |
| 17 | coinbase    | SPELL-USD   | 5m          |      0.000658  | 57.1729 |  1.32004  | -0.540194  |    1.38534   | -0.394448   |        1.67367   |
| 18 | coinbase    | TOSHI-USD   | 5m          |      0.0007087 | 50.7505 | -0.158999 | -1.1007    |    0.26741   |  0.0635337  |       -0.0189556 |
| 19 | coinbase    | TURBO-USD   | 5m          |      0.006153  | 52.1688 |  0.358791 | -0.992631  |    0.0491333 |  0.34807    |        0.181826  |
| 20 | coinbase    | XCN-USD     | 5m          |      0.01779   | 44.8714 | -1.16957  | -1.24313   |    0.353892  | -0.125377   |       -1.49533   |
| 21 | coinbase    | ZORA-USD    | 5m          |      0.01216   | 35.9017 | -1.34424  | -0.66824   |    0.827964  | -0.0433393  |       -1.35335   |
| 22 | kraken      | BTC-USD     | 5m          |  50966.5       | 46.7083 | -0.84113  | -2.5426    |    0.605161  | -0.00894588 |      nan         |
-----------------------------------------------------------


--- Evaluating Scan: Overbought_Extreme_V1 ---
Description: Looks for symbols that are highly overbought on multiple indicators.
Minimum flags to pass: 2
No symbols met the criteria for scan: 'Overbought_Extreme_V1'.

--- Evaluating Scan: Potential_Mean_Reversion_Short ---
Description: Similar to Overbought_Extreme_V1 but might use slightly different thresholds or fewer flags.
Minimum flags to pass: 1

Symbols meeting criteria for scan: 'Potential_Mean_Reversion_Short'
|    | exchange   | symbol    | timeframe   |     close |     RSI |   zscore |        %B |   ATRstretch |   VWAPgap |   BTC_rel_zscore |   flags_met |
|---:|:-----------|:----------|:------------|----------:|--------:|---------:|----------:|-------------:|----------:|-----------------:|------------:|
|  2 | coinbase   | BONK-USD  | 5m          | 2.3e-05   | 62.5818 |  1.61771 | -0.194989 |      1.40836 | 0.15664   |          1.36965 |           1 |
|  7 | coinbase   | FLOKI-USD | 5m          | 0.0001093 | 61.624  |  1.66641 | -0.218866 |      1.27197 | 0.0846209 |          1.71024 |           1 |

--- Evaluating Scan: Oversold_Interest ---
Description: Looks for potentially oversold conditions.
Minimum flags to pass: 1

Symbols meeting criteria for scan: 'Oversold_Interest'
|    | exchange   | symbol     | timeframe   |    close |     RSI |    zscore |         %B |   ATRstretch |    VWAPgap |   BTC_rel_zscore |   flags_met |
|---:|:-----------|:-----------|:------------|---------:|--------:|----------:|-----------:|-------------:|-----------:|-----------------:|------------:|
|  4 | coinbase   | DEGEN-USD  | 5m          | 0.004021 | 56.1559 |  0.902144 | -0.655885  |     0.853173 | -0.202711  |         0.549775 |           1 |
|  5 | coinbase   | DOGE-USD   | 5m          | 0.23776  | 59.6966 |  1.25674  | -0.0659958 |     0.988645 | -0.0541618 |         1.08625  |           1 |
|  8 | coinbase   | HONEY-USD  | 5m          | 0.0311   | 45.9725 | -0.376295 | -2.70931   |     0.709073 | -0.279662  |        -0.265072 |           1 |
|  9 | coinbase   | JASMY-USD  | 5m          | 0.01931  | 58.4819 |  1.40609  | -0.165553  |     1.26801  | -0.0705716 |         1.20337  |           1 |
| 11 | coinbase   | MOBILE-USD | 5m          | 0.000507 | 45.8293 | -0.101576 | -2.10063   |     0.91846  | -0.606095  |         0.200543 |           1 |
| 17 | coinbase   | SPELL-USD  | 5m          | 0.000658 | 57.1729 |  1.32004  | -0.540194  |     1.38534  | -0.394448  |         1.67367  |           1 |
| 20 | coinbase   | XCN-USD    | 5m          | 0.01779  | 44.8714 | -1.16957  | -1.24313   |     0.353892 | -0.125377  |        -1.49533  |           1 |
| 21 | coinbase   | ZORA-USD   | 5m          | 0.01216  | 35.9017 | -1.34424  | -0.66824   |     0.827964 | -0.0433393 |        -1.35335  |           1 |

--- Evaluating Scan: BTC_Strong_Outperformers ---
Description: Looks for symbols significantly outperforming Bitcoin and showing own strength.
Minimum flags to pass: 2

Symbols meeting criteria for scan: 'BTC_Strong_Outperformers'
|    | exchange   | symbol    | timeframe   |     close |     RSI |   zscore |        %B |   ATRstretch |    VWAPgap |   BTC_rel_zscore |   flags_met |
|---:|:-----------|:----------|:------------|----------:|--------:|---------:|----------:|-------------:|-----------:|-----------------:|------------:|
|  7 | coinbase   | FLOKI-USD | 5m          | 0.0001093 | 61.624  |  1.66641 | -0.218866 |      1.27197 |  0.0846209 |          1.71024 |           2 |
| 17 | coinbase   | SPELL-USD | 5m          | 0.000658  | 57.1729 |  1.32004 | -0.540194 |      1.38534 | -0.394448  |          1.67367 |           2 |

--- Evaluating Scan: BTC_Potential_Catch_Up ---
Description: Looks for symbols that might be starting to outperform BTC after a period of underperformance, or are showing general strength aligned with BTC.
Minimum flags to pass: 2

Symbols meeting criteria for scan: 'BTC_Potential_Catch_Up'
|    | exchange    | symbol      | timeframe   |         close |     RSI |    zscore |         %B |   ATRstretch |    VWAPgap |   BTC_rel_zscore |   flags_met |
|---:|:------------|:------------|:------------|--------------:|--------:|----------:|-----------:|-------------:|-----------:|-----------------:|------------:|
|  2 | coinbase    | BONK-USD    | 5m          |     2.3e-05   | 62.5818 |  1.61771  | -0.194989  |    1.40836   |  0.15664   |        1.36965   |           3 |
|  7 | coinbase    | FLOKI-USD   | 5m          |     0.0001093 | 61.624  |  1.66641  | -0.218866  |    1.27197   |  0.0846209 |        1.71024   |           3 |
| 13 | coinbase    | MOODENG-USD | 5m          |     0.2777    | 54.4962 |  0.796913 | -0.496264  |    0.111714  |  1.66395   |        0.748743  |           3 |
| 14 | coinbase    | PENGU-USD   | 5m          |     0.01453   | 53.7828 |  0.965678 | -0.721007  |    0.242128  |  0.0185535 |        1.10119   |           3 |
| 15 | coinbase    | PEPE-USD    | 5m          |     1.44e-05  | 56.2662 |  0.900623 | -0.908834  |    0.0477595 |  0.384206  |        0.969908  |           3 |
|  0 | coinbasepro | BTC-USD     | 5m          | 67363.8       | 57.7431 |  0.735155 | -0.632361  |    1.22989   |  0.0056555 |      nan         |           2 |
|  4 | coinbase    | DEGEN-USD   | 5m          |     0.004021  | 56.1559 |  0.902144 | -0.655885  |    0.853173  | -0.202711  |        0.549775  |           2 |
|  5 | coinbase    | DOGE-USD    | 5m          |     0.23776   | 59.6966 |  1.25674  | -0.0659958 |    0.988645  | -0.0541618 |        1.08625   |           2 |
|  6 | coinbase    | DOGINME-USD | 5m          |     0.0007354 | 42.3472 |  0.148719 | -1.21723   |    1.18132   |  0.0402669 |        0.251742  |           2 |
|  9 | coinbase    | JASMY-USD   | 5m          |     0.01931   | 58.4819 |  1.40609  | -0.165553  |    1.26801   | -0.0705716 |        1.20337   |           2 |
| 10 | coinbase    | KEYCAT-USD  | 5m          |     0.0058    | 48.6891 |  0.663126 | -1.77628   |    0.678751  |  0.0857258 |        0.683371  |           2 |
| 16 | coinbase    | SHIB-USD    | 5m          |     1.622e-05 | 52.9046 |  0.647779 | -0.989652  |    0.0664055 | -0.019074  |        0.924466  |           2 |
| 17 | coinbase    | SPELL-USD   | 5m          |     0.000658  | 57.1729 |  1.32004  | -0.540194  |    1.38534   | -0.394448  |        1.67367   |           2 |
| 18 | coinbase    | TOSHI-USD   | 5m          |     0.0007087 | 50.7505 | -0.158999 | -1.1007    |    0.26741   |  0.0635337 |       -0.0189556 |           2 |
| 19 | coinbase    | TURBO-USD   | 5m          |     0.006153  | 52.1688 |  0.358791 | -0.992631  |    0.0491333 |  0.34807   |        0.181826  |           2 |

--- Evaluating Scan: BTC_Extreme_Underperformers ---
Description: Looks for symbols significantly underperforming Bitcoin. Could be for fading or bottom fishing if other metrics align.
Minimum flags to pass: 1
No symbols met the criteria for scan: 'BTC_Extreme_Underperformers'.
