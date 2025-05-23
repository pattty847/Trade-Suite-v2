## Sentinel Architecture & Progress Report

**Core Goal:** To create a robust, 24/7 data collection service ("Sentinel") for BTC/USD order book snapshots and trades from Coinbase, storing the data in InfluxDB for analysis. The system is designed to be modular and resilient.

**Key Architectural Decisions & Components:**

1.  **Decoupled Data Source (`trade_suite/data/data_source.py`):**
    *   The existing `Data` class, originally designed for a GUI application using an `SignalEmitter`, has been enhanced.
    *   `watch_trades` and `watch_orderbook` methods now support a `sink` (async callback) or `queue` (`asyncio.Queue`) mechanism. This allows data to be piped to external systems like Sentinel without modifying the core emission logic needed for the GUI.
    *   If a `sink`/`queue` is provided, raw data (dictionaries of CCXT trade/order book objects) is passed there.
    *   The `watch_orderbook` method now accepts a `cadence_ms` parameter (defaulting to 500ms), allowing Sentinel to request data at its desired 10Hz (100ms) frequency.
    *   Legacy direct InfluxDB writes and statistics calculations within these methods are bypassed when Sentinel uses the `sink`/`queue`.

2.  **Sentinel Application (`sentinel/` directory):**
    *   **`config.py`**: Centralized configuration for InfluxDB connection details, data collection parameters (cadence, depth for future binning), logging settings, and run mode durations.
    *   **`schema.py`**:
        *   `build_trade_lp()`: Converts raw trade data into InfluxDB Line Protocol.
        *   `build_book_lp()`: Converts raw order book data into InfluxDB Line Protocol. *Currently, this function has a placeholder for binning logic and writes the top N levels directly.*
    *   **`collectors/coinbase.py` (`stream_data_to_queues`):**
        *   Acts as the bridge between the `TradeSuiteData` source and Sentinel's internal queues.
        *   It calls `watch_trades` and `watch_orderbook` on an initialized `TradeSuiteData` instance, providing local `async def sink` functions.
        *   These sink functions receive the raw data, use `sentinel.schema` to convert it to Line Protocol, and then `put` the LP strings onto dedicated `asyncio.Queue`s (one for trades, one for order books). Timestamps are converted from milliseconds (from CCXT) to nanoseconds (for InfluxDB).
    *   **`writers/influx_writer.py` (`InfluxWriter` class):**
        *   Connects to InfluxDB using settings from `config.py` and an environment variable for the token.
        *   The `run_queue_consumer()` method runs as an asyncio task for each data type (trades, order books). It consumes Line Protocol strings from the respective `asyncio.Queue`.
        *   Manages batching of data points (based on `WRITER_BATCH_SIZE_POINTS` or `WRITER_FLUSH_INTERVAL_MS` from `config.py`) before writing to InfluxDB.
        *   Includes basic retry logic for InfluxDB write operations.
    *   **`supervisor.py` (`Supervisor` class):**
        *   The orchestrator of the Sentinel application.
        *   Initializes `TradeSuiteData` (with `emitter=None` for Sentinel's use) and `InfluxWriter`.
        *   Creates and manages the `asyncio.Queue`s for trades and order books.
        *   Spawns and manages:
            *   One collector task (`stream_data_to_queues`).
            *   Two writer tasks (instances of `influx_writer.run_queue_consumer`, one for trades, one for order books, each writing to their configured bucket).
        *   Implements task restart logic with exponential backoff (using `WS_RECONNECT_BACKOFF` from `config.py`).
        *   Manages graceful shutdown via an `asyncio.Event` and by closing connections.
    *   **`run.py`**:
        *   The command-line interface (CLI) entry point (`python -m sentinel.run`).
        *   Uses `argparse` to handle `--dry-run` (runs for `RUN_DURATION_SECONDS_DRY_RUN`) and `--live` (runs for `RUN_DURATION_SECONDS_LIVE`, e.g., 48 hours) flags.
        *   Initializes and starts the `Supervisor`.
        *   Handles `SIGINT` (Ctrl+C) and `SIGTERM` for graceful shutdown by signaling the `Supervisor` to stop.
    *   **`tests/test_schema.py`**: A placeholder for unit tests for the Line Protocol generation functions.

**Data Flow Summary:**

`run.py` → `Supervisor` (creates Queues, starts Collector & Writers) → `Collector (coinbase.py)` (uses `TradeSuiteData` via `sink`s) → `TradeSuiteData` (calls `sink`s with CCXT data) → `Collector` (converts to LP via `schema.py`, puts on Queues) → `InfluxWriter` (gets from Queues, batches) → InfluxDB.

**What Has Been Achieved / Current Status:**

*   **Core Scaffolding Complete:** All primary modules for Sentinel are in place with basic functionality.
*   **Decoupled Data Ingestion:** `trade_suite.data.data_source` can now feed data to Sentinel without interfering with its existing GUI operations.
*   **Asynchronous Operations:** The system is built entirely on `asyncio` for efficient I/O.
*   **Data Queuing:** `asyncio.Queue`s are used to buffer data between collection and writing, improving resilience.
*   **Basic InfluxDB Integration:** Line Protocol generation and writing to InfluxDB (with batching and retries) are implemented.
*   **Task Supervision:** The supervisor can manage and restart collector/writer tasks.
*   **CLI and Run Modes:** Basic CLI for dry and live runs is functional.
*   **Graceful Shutdown:** Signal handling is in place for controlled termination.

---

**Next Steps & Areas for Development:**

1.  **Implement Order Book Binning Logic (High Priority):**
    *   **File:** `sentinel/schema.py`
    *   **Function:** `build_book_lp()`
    *   **Details:** The current `build_book_lp` writes raw top-N levels. This needs to be updated to:
        *   Calculate the mid-price.
        *   Define Basis Point Spread (BPS) bins (e.g., ±5, ±10, ±25 bps) relative to the mid-price, potentially configurable via `config.DEPTH_BINS` or a new `BPS_LEVELS` list in `config.py`.
        *   Aggregate the total volume (sum of amounts) within each BPS bin for both bids and asks.
        *   Generate Line Protocol for each bin, including tags for exchange, symbol, side (bid/ask), and the BPS bin identifier. Fields should include the aggregated volume and potentially other metrics like VWAP within the bin if desired.
        *   Ensure timestamps are consistently in nanoseconds.

2.  **Write Comprehensive Unit Tests (High Priority):**
    *   **File:** `sentinel/tests/test_schema.py`
    *   **Details:**
        *   Test `build_trade_lp()` for correct measurement name, tags (exchange, symbol, side), fields (price, size, trade\_id with proper type handling and string quoting), and nanosecond timestamp.
        *   Test `build_book_lp()` thoroughly once binning is implemented. Verify correct mid-price calculation, assignment of raw levels to the correct BPS bins, and accurate aggregation of volumes within those bins. Test edge cases (e.g., empty book, book with few levels).

3.  **InfluxDB Gap Audit (Medium Priority):**
    *   **Context:** Exchanges like Coinbase provide sequence numbers with their L2 market data updates.
    *   **Collector Task:** (`sentinel/collectors/coinbase.py`): If using a level2 channel that provides sequence numbers (e.g., Coinbase `l2update`), the collector should track these sequence numbers.
    *   **Writer Task:** (`sentinel/writers/influx_writer.py` or a dedicated mechanism): If a gap in sequence numbers is detected by the collector, it should either:
        *   Push a special "gap event" onto a queue, which the writer then records in a dedicated InfluxDB measurement (e.g., `gaps,exchange=coinbase,symbol=BTCUSD missing_count=X,start_seq=Y,end_seq=Z <timestamp>`).
        *   Or, the schema for order book data itself could include the sequence number, allowing for offline analysis of gaps.
    *   *Initial thought: The plan mentioned "gap-audit" in the writer. This implies the writer would need sequence numbers. If the `watch_order_book` from `ccxt` doesn't directly provide easily usable sequence numbers for full snapshots, or if we switch to a delta-based feed, the collector logic in `sentinel/collectors/coinbase.py` would become more complex to maintain the local book and track sequences.*

4.  **Logging Enhancement (Medium Priority):**
    *   **Task:** Transition from standard Python `logging` to `structlog` across all Sentinel modules.
    *   **Benefit:** Provides structured (e.g., JSON) logging, which is easier to parse, search, and analyze, especially for a long-running service. Ensure ISO timestamps are used.

5.  **Refine Configuration & Secrets Management (Medium Priority):**
    *   **InfluxDB Token:** Currently relies on `INFLUXDB_TOKEN_LOCAL`. Consider more robust ways to manage secrets, especially if deploying to different environments (e.g., separate dev/prod tokens, integration with a secrets manager for cloud deployments, or clearer instructions for `.env` files).
    *   **InfluxDB URL:** Allow easier switching between local and cloud InfluxDB instances (e.g., via an environment variable or CLI flag).

6.  **Pydantic for Data Validation (Low-Medium Priority):**
    *   **Task:** Introduce Pydantic models within the collector sinks (`sentinel/collectors/coinbase.py`) to validate the structure of incoming raw trade and order book data from `TradeSuiteData`.
    *   **Benefit:** Catches unexpected data format changes or errors early, making the system more robust.

7.  **Backlog Items (from original plan, for future iterations):**
    *   **Parquet Archiver Task:** A separate task/process to periodically query data from InfluxDB and archive it to Parquet files for long-term storage or offline analysis.
    *   **Derived Metrics Writer:** A component that consumes raw data (or data from InfluxDB) to calculate and write derived metrics like Cumulative Volume Delta (CVD), order book imbalance, etc., to InfluxDB.
    *   **REST API:** An HTTP API (e.g., using FastAPI) for `/sentinel/alerts` or status checks.
    *   **Multi-Asset & Multi-Exchange Support:** Generalize the configuration and collector logic to support more trading pairs and exchanges beyond BTC/USD on Coinbase.
    *   **Bucket Rotation:** Implement strategies for InfluxDB bucket rotation if data volume becomes an issue for retention policies.
    *   **Containerization & CI/CD:** Dockerfile for easy deployment and Continuous Integration/Deployment pipeline.

8.  **Review `TradeSuiteData.close_all_exchanges()`:**
    *   The `Supervisor.stop()` method calls `await self.data_source.close_all_exchanges()`. Verify this method is correctly implemented in `CCXTInterface` or `Data` within `trade_suite.data.data_source` to ensure all underlying CCXT WebSocket connections are properly closed during shutdown.

This detailed breakdown should provide a solid foundation for planning the next development phases.
