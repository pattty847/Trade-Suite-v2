# sentinel/config.py

# Websocket and data processing configuration
CADENCE_MS = 100  # Target time in milliseconds for order book snapshots (10 Hz)
DEPTH_BINS = 5  # Number of price bins on each side (bids/asks) of the mid-price
SNAPSHOT_POINTS = 10  # Total data points for an order book snapshot (2 * DEPTH_BINS typically)

# Order book binning configuration (New)
ORDER_BOOK_BIN_BPS = 5          # Basis points for each bin width (e.g., 5 bps = 0.05%)
ORDER_BOOK_MAX_BINS_PER_SIDE = 5 # Number of bins to generate on each side of the mid-price (e.g., 5 bins for bids, 5 for asks)

# Raw Order Book configuration (New)
RAW_BOOK_TOP_N = 10             # Number of top bid/ask levels for raw order book data
INFLUX_BUCKET_OB_RAW = "raw_order_book" # Bucket for raw order book data

# InfluxDB configuration
INFLUX_BUCKET_OB = "order_book"       # Bucket for order book data
INFLUX_BUCKET_TR = "trades"           # Bucket for trade data
INFLUX_ORG = "pepe"                   # InfluxDB organization (as per your existing InfluxDB class)
INFLUX_URL_LOCAL = "http://localhost:8086"
# INFLUX_URL_CLOUD = "https://us-east-1-1.aws.cloud2.influxdata.com" # Example, if you use cloud
# INFLUX_TOKEN_ENV_VAR_LOCAL = "INFLUXDB_TOKEN_LOCAL" # Environment variable for local token
# INFLUX_TOKEN_ENV_VAR_CLOUD = "INFLUXDB"           # Environment variable for cloud token

# Collector/Writer behavior
WS_RECONNECT_BACKOFF = [1, 2, 5, 10]  # Seconds to wait before WebSocket reconnection attempts
WRITER_BATCH_SIZE_POINTS = 5000       # Max points to batch before writing to InfluxDB
WRITER_FLUSH_INTERVAL_MS = 100      # Max time to wait before flushing batch to InfluxDB

# Logging configuration
LOG_FILE = "./sentinel.log"         # Path to the log file
LOG_LEVEL = "INFO"                  # Default logging level (e.g., DEBUG, INFO, WARNING, ERROR)

# Run configuration
RUN_DURATION_SECONDS_DRY_RUN = 300 # 5 minutes, was 30 seconds
RUN_DURATION_SECONDS_LIVE = 48 * 60 * 60  # 48 hours
RUN_DURATION_SECONDS_TEST = 1 * 60    # 1 minute for integration tests

# Health Check Interval
# How often the supervisor should log the status of its queues (in seconds)
HEALTH_CHECK_INTERVAL_SECONDS = 30

# Targetted assets and exchanges
TARGET_EXCHANGE = "coinbase"
TARGET_SYMBOL_CCXT = "BTC/USD" # CCXT format
TARGET_SYMBOL_INFLUX = "BTC-USD" # Format for InfluxDB tags/fields if different 