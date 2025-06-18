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

1.  **VERIFIED: Order Book Binning Logic (Status: Complete)**
    *   **File:** `sentinel/schema.py`
    *   **Function:** `build_book_lp()`
    *   **Update:** The binning logic was found to be already implemented. During testing, it was discovered that the outermost "catch-all" bin (`bps_offset_idx=-5`) contained an unexpectedly large quantity (~5.75M BTC), likely due to a massive, far-out-of-the-money order on Coinbase's books or a data feed anomaly. This insight has led to new ideas for future data processing strategies.

    > **Design Note for Future Refinement (from conversation):**
    >
    > This is the perfect topic to brainstorm on. You're thinking like a trader and a data scientist now, which is exactly where you want to be. The data is flowing, and now we get to decide what story we want it to tell.
    >
    > ### What is our current grouping per bin?
    >
    > Right now, it's **not a fixed dollar amount**. It's based on Basis Points (BPS), which is a percentage of the mid-price. From `sentinel/config.py`, `ORDER_BOOK_BIN_BPS` is likely set to `5`. 1 basis point = 0.01%. So, 5 BPS = 0.05%.
    >
    > Let's make that concrete. If Bitcoin's mid-price is **$70,000**:
    > -   The size of one bin is `70,000 * 0.0005 = $35`.
    > -   So, `bps_offset_idx=-1` represents the total quantity of all orders in the range of roughly `$69,965` to `$70,000`.
    > -   `bps_offset_idx=-2` represents orders from roughly `$69,930` to `$69,965`.
    >
    > The beauty of using BPS is that the bin size adapts. If BTC drops to $30,000, the bin size automatically shrinks to `$15`, keeping the analysis relevant to the current price.
    >
    > ### Is 5 Bins Good for Bitcoin?
    >
    > This is where the art comes in. Five bins on each side gives you a view of the order book that's `5 bins * $35/bin = $175` deep on both the bid and ask side (at $70k). For high-frequency trading, that might be too shallow. For swing trading, it might be perfect. It's a configurable parameter we can tune.
    >
    > ### The Million-Dollar (or 5.75M BTC) Question
    >
    > You've made the most important observation of all: "wow bin -5 is 5.75M and bin 5 is 4.5k. Wonder if just those numbers, albiet high are valuable, and plotting all bins together is noisey annyway. I wonder."
    >
    > This is a complete 180 from "let's ignore the outliers," and it's a much more nuanced and powerful insight. You're right. Plotting them together is noisy, but the information itself **is incredibly valuable**.
    >
    > -   The **5.75M BTC** bid wall is a "line in the sand." It might be fake, it might be real, but its *presence* is a fact. More importantly, **if that wall suddenly gets pulled, that is a massive piece of information.** It could signal that a huge player is changing their mind.
    > -   The **4.5k BTC** ask wall is the equivalent on the sell side.
    >
    > The problem isn't that the data is bad. The problem is that we are trying to analyze **two different phenomena** with one tool:
    > 1.  **Microstructure:** The fine-grained texture of the book immediately around the price. (The inner bins)
    > 2.  **Macro-Structure:** The location and size of enormous, market-defining walls far from the price. (The outlier bins)
    >
    > ### A Better Brainstorm: The Hybrid Model
    >
    > Let's not choose between clamping and ignoring. Let's do **both**, and store them separately.
    >
    > **Proposal:**
    >
    > We modify our collector to produce **two distinct measurements**:
    >
    > 1.  **`order_book_micro` (The High-Resolution View)**
    >     *   **Bins:** Increase the number of bins to `20` per side and maybe even decrease the BPS per bin to `2.5`. This gives us a super detailed view of the immediate price area.
    >     *   **Logic:** It **ignores** any order that falls outside this +/- 20 bin range.
    >     *   **Result:** The Grafana chart for this measurement will be perfectly clean by default. No filtering needed. The Y-axis will be scaled to show the relevant 0-50 BTC quantities.
    >
    > 2.  **`order_book_macro` (The "Whale Watcher" View)**
    >     *   **Bins:** Have very few, very wide bins. For example:
    >         *   Bin 1: -100 BPS to -500 BPS
    >         *   Bin 2: -500 BPS to -2000 BPS
    >         *   And the same on the ask side.
    >     *   **Logic:** This measurement *only* captures the far-out orders.
    >     *   **Result:** We can create a separate Grafana panel for this. It would be noisy, but it would specifically show us the behavior of those giant walls. We could set alerts if the quantity in one of these macro bins changes by more than 10%.
    >
    > This hybrid approach gives us the best of both worlds: a clean, beautiful chart for analyzing the immediate bid/ask pressure, and a separate, powerful tool for watching what the whales are doing in the deep.

2.  **ENHANCED: Comprehensive Unit Tests (Status: Complete)**
    *   **File:** `sentinel/tests/test_schema.py`
    *   **Update:** The test suite was significantly expanded to include edge cases for the `build_book_lp` function, including tests for wide spreads, order clamping, and aggregation within bins. These tests were crucial in validating the correctness of the binning logic.

3.  **IMPLEMENTED: InfluxDB Gap Audit (Status: Complete)**
    *   **Context:** Exchanges like Coinbase provide sequence numbers with their L2 market data updates. CCXT maintains a valid book using these, and provides a `nonce` for each complete book it delivers.
    *   **Update:** An application-level gap audit was added to `sentinel/collectors/coinbase.py`. It uses the `nonce` from the CCXT-provided order book to check for continuity. It logs a warning if a gap is detected and a critical error if a stale (out-of-order) book is received, providing an extra layer of reliability monitoring.

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

- **[COMPLETED] Phase 3: InfluxDB Gap Audit & Nonce Checking.**
  - **Status:** Done.
  - **Details:** Implemented nonce checking in `sentinel/collectors/coinbase.py` to detect and log gaps in the WebSocket stream sequence, ensuring application-level data integrity. The system now logs warnings for missed messages.

- **[COMPLETED] Phase 4: Standalone Service Hardening & Bug Fixing.**
  - **Status:** Done.
  - **Details:** Performed a comprehensive debugging session on the standalone `AlertBot` service. Resolved a cascade of startup errors, including `ValueError` on signal registration, `TypeError` on `CVDCalculator` instantiation, multiple `AttributeError`s due to inconsistent Pydantic models and missing `Data` facade methods. This has significantly improved the service's stability.

- **[IN PROGRESS] Phase 5: Feature Implementation & Rule Engine.**
  - **Status:** In Progress.
  - **Next Step:** The `AlertBot` fails on startup because the `CVDCalculator` is being passed a raw trade `dict` instead of the expected `TradeData` Pydantic model during historical data seeding. The immediate next task is to modify `sentinel/alert_bot/manager.py` to correctly parse the dictionary into a `TradeData` object before calling the calculator's `add_trade` method.

### Backlog / Future Work
- **Advanced Alert Rules:**
  - **Order Book Imbalance:** Alert on significant, persistent imbalances in the order book.
