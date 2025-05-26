# Price Alert Feature (`scripts/price_alert.py`)

**Version:** 1.0 (Post-Refactor May 2024)
**Author:** Gemini AI & User
**Primary Contact:** User

## 1. Purpose

The `price_alert.py` script is a sophisticated monitoring tool designed to track cryptocurrency prices from the Coinbase exchange (via `ccxt`). It allows users to define complex alert conditions for multiple trading symbols through a YAML configuration file. When an alert condition is met, the script logs the event and sends an email notification.

This feature is intended to provide timely updates on significant market movements based on user-defined criteria, enabling proactive responses.

## 2. Features

*   **Configuration-Driven:** All symbols and alert parameters are defined in a YAML file (`sentinel/alert_bot/alerts_config.yaml` by default).
*   **Multiple Symbol Monitoring:** Tracks any number of trading pairs (e.g., BTC/USD, ETH/USD, PEPE/USD) simultaneously.
*   **Price Level Alerts:** Triggers alerts when a symbol's price crosses above or below a specified level.
*   **Percentage Change Alerts:** Triggers alerts when a symbol's price changes by a specified percentage over a defined timeframe (e.g., 5% change in 30 minutes). Uses OHLCV data.
*   **Volatility Alerts:** Triggers alerts when a symbol's price volatility (calculated as the standard deviation of closing prices) exceeds a specified threshold over a defined timeframe. Uses OHLCV data.
*   **Symbol-Specific Timeframes:** Each percentage change and volatility alert can have its own `timeframe` (e.g., 5m, 30m, 1h), determining the granularity of OHLCV data used.
*   **Email Notifications:** Sends detailed email alerts when conditions are met (requires SMTP configuration via `.env` file).
*   **Comprehensive Logging:** Logs all activities, price updates, fetched data, and alerts to both the console and a dedicated log file (`logs/alert_logs.log`).
*   **Dynamic Price Precision:** Automatically formats logged prices based on the symbol's market precision.
*   **Graceful Error Handling:** Includes error handling for API requests and other potential issues.

## 3. How It Works

### 3.1. Core Components

*   **`PriceAlert` Class:** The main class encapsulating all logic.
    *   **Initialization (`__init__`)**:
        *   Loads the exchange (Coinbase) and market data (for price precision).
        *   Parses the provided `config_data` (from `alerts_config.yaml`).
        *   Initializes structures to store OHLCV data (`self.ohlcv_data`), last OHLCV fetch times (`self.last_ohlcv_fetch_time`), and last ticker prices (`self.last_ticker_prices`).
    *   **Main Loop (`run`)**:
        *   Runs continuously at a `main_loop_interval_seconds` (default 60s).
        *   For each monitored symbol:
            1.  Fetches the current ticker price (`exchange.fetch_ticker`).
            2.  Logs the current price with appropriate precision.
            3.  Calls `_fetch_ohlcv_if_needed` to update historical candle data if required by any alert config for that symbol.
            4.  Calls `check_alerts` to evaluate all configured alert conditions for the symbol against the latest ticker and OHLCV data.
    *   **OHLCV Data Fetching (`_fetch_ohlcv_if_needed`)**:
        *   Identifies unique timeframes required by `percentage_changes` and `volatility` alerts for a given symbol from its configuration.
        *   For each required timeframe (e.g., '5m', '30m'):
            *   Checks if enough time has passed since the last fetch for that specific symbol and timeframe (cooldown mechanism).
            *   If a fetch is due, calls `exchange.fetch_ohlcv(symbol, timeframe_str, limit=50)`.
            *   Stores the fetched candles in `self.ohlcv_data[symbol][timeframe_str]` and updates `self.last_ohlcv_fetch_time[symbol][timeframe_str]`.
    *   **Alert Checking (`check_alerts`)**:
        *   Iterates through `price_levels`, `percentage_changes`, and `volatility` configurations for the given symbol.
        *   **Price Level Alerts**: Compares `current_price` against configured `price` and `condition`.
        *   **Percentage Change Alerts (`check_percentage_change`)**:
            *   Requires at least 2 OHLCV candles of the specified `timeframe`.
            *   Uses the closing price of the second-to-last candle as `old_price`.
            *   Calculates `((current_price - old_price) / old_price) * 100`.
            *   Compares with configured `percentage`.
            *   Sets an in-memory `triggered_session: True` flag on the alert configuration to prevent re-alerting in the same script run.
        *   **Volatility Alerts (`check_volatility`)**:
            *   Requires at least `N_VOLATILITY_PERIODS` (default 14) OHLCV candles of the specified `timeframe`.
            *   Calculates the standard deviation of the closing prices of the last `N_VOLATILITY_PERIODS` candles.
            *   Calculates volatility as `(std_dev / current_price) * 100`.
            *   Compares with configured `threshold`.
            *   Sets an in-memory `triggered_session: True` flag.
    *   **Helper Functions**:
        *   `_format_price`: Formats prices based on exchange-provided precision.
        *   `_get_ccxt_timeframe`: Converts integer minutes to `ccxt`-compatible timeframe strings (e.g., 5 -> '5m').

### 3.2. Data Structures

*   `self.config_data`: Stores the entire parsed YAML configuration.
*   `self.ohlcv_data`: `Dict[symbol_str, Dict[timeframe_str, List[ohlcv_candle]]]`
*   `self.last_ohlcv_fetch_time`: `Dict[symbol_str, Dict[timeframe_str, datetime_obj]]`
*   `self.last_ticker_prices`: `Dict[symbol_str, float]`

## 4. Configuration (`alerts_config.yaml`)

The script is configured using a YAML file (default: `sentinel/alert_bot/alerts_config.yaml`).

```yaml
SYMBOL_1/PAIR:  # e.g., BTC/USD
  price_levels:
    - price: <float>       # Price point for the alert
      condition: <above|below> # Condition for the alert
  percentage_changes:
    - percentage: <float>  # Percentage change to trigger alert (e.g., 5 for 5%)
      timeframe: <int>     # Timeframe in minutes (e.g., 30 for 30 minutes)
                           # This timeframe is used for both lookback and OHLCV candle size.
  volatility:
    - threshold: <float>   # Volatility percentage threshold (e.g., 2 for 2%)
      timeframe: <int>     # Timeframe in minutes for OHLCV candles used in calculation
                           # Volatility is calculated over N_VOLATILITY_PERIODS (e.g., 14) of these candles.

SYMBOL_2/PAIR:
  # ... similar structure ...
```

**Example:**

```yaml
BTC/USD:
  price_levels:
    - price: 70000
      condition: above
    - price: 65000
      condition: below
  percentage_changes:
    - percentage: 2
      timeframe: 15  # Alert on 2% change over 15 mins (using 15m candles)
  volatility:
    - threshold: 1
      timeframe: 5   # Alert on 1% volatility using 14 periods of 5m candles

PEPE/USD:
  price_levels:
    - price: 0.00001400
      condition: above
```

## 5. Setup & Usage

### 5.1. Dependencies

Ensure you have Python 3 installed. Install required libraries:

```bash
pip install ccxt pyyaml python-dotenv
```

### 5.2. Environment Variables (`.env` file)

Create a `.env` file in the root of the project for email notifications:

```
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_email@example.com
SMTP_PASSWORD=your_email_password
ALERT_EMAIL=recipient_email@example.com
```

### 5.3. Command-Line Arguments

```
usage: price_alert.py [-h] [--config CONFIG] [--main-loop-interval MAIN_LOOP_INTERVAL] [--create-config] [--test-email]

Crypto Price Alert Monitor - Config Driven

options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to YAML configuration file (default: sentinel/alert_bot/alerts_config.yaml)
  --main-loop-interval MAIN_LOOP_INTERVAL
                        Main loop check interval in seconds (default: 60)
  --create-config       Create an example configuration file and exit
  --test-email          Send a test email to verify credentials and exit
```

### 5.4. Running the Script

```bash
python scripts/price_alert.py
# or with a custom config
python scripts/price_alert.py --config path/to/your/custom_config.yaml
```

## 6. Logging

*   **Console Logging:** Provides real-time updates on fetched prices, OHLCV data, and triggered alerts.
*   **File Logging:** All log messages are also saved to `logs/alert_logs.log`.
    *   **Format:** `YYYY-MM-DD HH:MM:SS,ms - price_alert - LEVEL - Message`
    *   Log levels include `INFO`, `WARNING`, `ERROR`, `DEBUG`.

## 7. Price Precision (`_format_price`)

The `_format_price` method attempts to fetch market precision data from the exchange via `self.exchange.markets[symbol]['precision']['price']`. This ensures that prices, especially for assets with many decimal places (like PEPE/USD), are logged and reported accurately. If market data is unavailable, it uses fallback logic (e.g., 8 decimal places for prices < 0.001, otherwise 2 decimal places).

## 8. Future Enhancements (Potential)

*   **Refined Triggered State Management:** More advanced reset conditions for alerts (time-based, price-reversal based).
*   **Advanced Volatility Metrics:** Implement ATR (Average True Range).
*   **Configurable OHLCV Fetch Limits:** Allow `number_of_candles` per alert in config.
*   **Alert Cooldowns:** Prevent rapid re-alerting for the same condition.
*   **Enhanced Error Handling:** Symbol-specific backoff strategies.
*   **Unit Tests.** 
