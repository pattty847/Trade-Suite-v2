# Program Architecture and Flow

## Overview

This document outlines the architecture and operational flow of the Trade Suite v2 application. The program is designed as a comprehensive trading tool, providing users with real-time market data visualization, technical analysis capabilities, and data storage for various cryptocurrency exchanges. It leverages a graphical user interface (GUI) built with **Dear PyGui** for user interaction and data display, relying heavily on asynchronous data streams and a thread-safe signaling mechanism for communication.

## Architecture

The application follows a monolithic architecture with distinct layers for data management, analysis, and presentation (GUI). It heavily utilizes asynchronous programming (`asyncio`) and an event-driven, thread-safe Pub/Sub pattern (via `SignalEmitter`) for handling real-time data streams and maintaining GUI responsiveness.

**Major Components:**

*   **Entry Point (`trade_suite.__main__`)**:
    *   **Responsibilities**: Initializes the application, sets up logging, parses command-line arguments, loads environment variables (`dotenv`), loads configuration (`ConfigManager`), instantiates core components (`InfluxDB`, `SignalEmitter`, `Data`), and launches the main GUI window (`Viewport`).
*   **Configuration (`trade_suite.config.ConfigManager`)**:
    *   **Responsibilities**: Manages application settings stored in `config.json`. Provides methods to load, retrieve, and update configuration parameters. Uses a Singleton pattern.
*   **Data Layer (`trade_suite.data`)**:
    *   **Responsibilities**: Central hub for all data operations: establishing exchange connections, fetching real-time and historical data, caching, processing, delegating analysis, interacting with the database, and signaling updates to the GUI.
    *   **Sub-components**:
        *   **`CCXTInterface` (`ccxt_interface.py`)**: Base class responsible for initializing and managing connections to cryptocurrency exchanges using `ccxt` and `ccxt.pro`. Handles credential loading (from environment variables), market data loading, and connection lifecycle management. Maintains instances of active `ccxt.pro` exchange objects.
        *   **`Data` (`data_source.py`)**: Inherits from `CCXTInterface`. Orchestrates data flow. Initiates and manages asynchronous streaming loops (`watch_trades`, `watch_orderbook`) using the `ccxt.pro` exchange objects. Fetches historical data (`fetch_candles`) using `ccxt` methods, processes it into Pandas DataFrames, and manages a file-based cache (`data/cache`). Interacts with `InfluxDB` for data persistence. Delegates statistical calculations to `MarketAggregator`. Emits signals via `SignalEmitter` for GUI updates.
        *   **`InfluxDB` (`influx.py`)**: Manages the connection, writing (trades, stats, candles, order books - writing order books currently commented out), and potentially reading from an InfluxDB time-series database.
        *   **`CandleFactory` (`candle_factory.py`)**: (Potentially used by `Data` or `Analysis` - needs confirmation) Processes raw trade data to construct candlestick (OHLCV) data if not directly fetched.
        *   **`State` (`state.py`)**: (Role still requires confirmation) Potentially manages runtime state related to data streams or connections.
*   **Analysis Layer (`trade_suite.analysis`)**:
    *   **Responsibilities**: Performs calculations, aggregations, and transformations on market data.
    *   **Sub-components**:
        *   **`MarketAggregator` (`market_aggregator.py`)**: Used by the `Data` layer. Calculates real-time statistics (e.g., volume, VWAP) from incoming trade data. May interact with `InfluxDB` and `SignalEmitter`.
        *   `ChartProcessor` (`chart_processor.py`): Processes data specifically for chart rendering in the GUI.
        *   `OrderbookProcessor` (`orderbook_processor.py`): Processes order book data for display or analysis.
        *   `TechnicalAnalysis` (`technical_analysis.py`): Implements various technical indicators (e.g., SMA, EMA, RSI) calculated from OHLCV data.
*   **GUI Layer (`trade_suite.gui`)**:
    *   **Responsibilities**: Provides the user interface using **Dear PyGui**, displays data, and handles user interactions. Listens for signals from the `SignalEmitter` to update UI elements safely from the main thread.
    *   **Sub-components**:
        *   `Viewport` (`viewport.py`): The main Dear PyGui application window/viewport. Manages the overall layout (potentially using docking) and integrates different widgets/programs. Initializes the Dear PyGui context and likely runs the main render loop.
        *   `DashboardProgram` (`dashboard_program.py`): Represents the primary dashboard or a major view area within the `Viewport`, containing various Dear PyGui widgets.
        *   `TaskManager` (`task_manager.py`): Manages launching and potentially canceling asynchronous background tasks (like data streaming loops initiated by `Data` methods) requested by the GUI, ensuring the UI remains responsive.
        *   **`SignalEmitter` (`signals.py`) / `Signals` Enum**: Implements a thread-safe Pub/Sub mechanism. GUI components register callback functions (`register`). Data/Analysis components emit signals (`emit`) with data payloads. Ensures callbacks destined for the GUI are executed on the main thread via a queue processed by `process_signal_queue` (likely called within the Dear PyGui render loop).
        *   `Widgets` (`widgets/`): Contains custom UI components (Dear PyGui widgets or groups of widgets like charts, tables) that display data. These widgets register their update methods as callbacks with the `SignalEmitter`.
        *   `Utils` (`utils.py`): GUI-specific utility functions, possibly Dear PyGui helpers.

**Component Interactions:**

1.  `__main__` initializes core components (`ConfigManager`, `InfluxDB`, `SignalEmitter`, `Data`).
2.  `__main__` starts the `Viewport`, which sets up the Dear PyGui context and likely registers `signal_emitter.process_signal_queue` to run every frame (or frequently).
3.  GUI Widgets (within `DashboardProgram` or elsewhere) register callback methods with the `SignalEmitter` for signals they care about (e.g., `chart_widget.register(Signals.NEW_CANDLES, chart_widget.update_data)`).
4.  User interaction triggers a request to `TaskManager`.
5.  `TaskManager` starts an `asyncio` background task calling a method on `Data` (e.g., `data.watch_trades`).
6.  The `Data` task receives data from `ccxt.pro`.
7.  `Data` calls `signal_emitter.emit(Signals.NEW_TRADE, tab=..., trade_data=...)`.
8.  `SignalEmitter.emit` detects it's called from a background thread and puts the signal + data into its internal queue.
9.  The Dear PyGui main loop calls `signal_emitter.process_signal_queue`.
10. `process_signal_queue` dequeues the `NEW_TRADE` signal and its data.
11. `process_signal_queue` looks up callbacks registered for `NEW_TRADE`.
12. `process_signal_queue` executes the registered callback(s) (e.g., `widget.handle_new_trade(tab=..., trade_data=...)`) **within the main GUI thread**, passing the data.
13. The widget updates its Dear PyGui elements using the received data.
14. Similar flows occur for other signals (`ORDER_BOOK_UPDATE`, `TRADE_STAT_UPDATE`, etc.) and for data fetching (`fetch_candles` might emit `NEW_CANDLES` or return data directly depending on implementation).
15. Analysis components (`TechnicalAnalysis`, `ChartProcessor`) are called by GUI widgets when needed, processing data (e.g., DataFrames) received via signals or direct calls.

## Logic Flow

1.  **Initialization**: `__main__.py` executes.
2.  **Setup**: Logging, args, env vars, config loaded.
3.  **Core Components**: `InfluxDB`, `SignalEmitter`, `Data` (loads exchanges via `CCXTInterface` logic) instantiated.
4.  **GUI Launch**: `Viewport` created, Dear PyGui context initialized, `start_program()` called. GUI layout loaded/initialized. `process_signal_queue` is likely registered as a recurring callback.
5.  **Idle State**: Application waits for user interaction.
6.  **User Action (e.g., Open Chart)**: User selects exchange/symbol/timeframe in a GUI widget (associated with a `tab` ID).
7.  **Task Launch**: Widget requests `TaskManager` to run data fetching/streaming tasks.
8.  **Streaming (Real-time)**:
    *   `TaskManager` calls `data.watch_trades(tab=..., symbol=...)` and `data.watch_orderbook(tab=..., symbol=...)`.
    *   `Data` starts async loops using `ccxt.pro`.
    *   New data arrives -> `Data` emits signals (e.g., `NEW_TRADE`) via `SignalEmitter`, placing them in the queue.
    *   Main thread processes queue -> Relevant GUI widgets receive data via callbacks and update Dear PyGui items.
9.  **Fetching (Historical)**:
    *   `TaskManager` calls `data.fetch_candles(tab=..., symbol=..., timeframe=...)`.
    *   `Data` checks cache. If miss, calls `ccxt.fetch_ohlcv`.
    *   Processes data (Pandas), caches, optionally writes to `InfluxDB`.
    *   Returns DataFrame to the calling GUI component or emits a signal (e.g., `NEW_CANDLES`) with the data via `SignalEmitter`.
10. **Analysis & Display**: GUI widgets receive data (streaming updates or historical DataFrames). They may call `Analysis Layer` components (`TechnicalAnalysis`, `ChartProcessor`) to compute indicators or format data before rendering it.
11. **Termination**: User closes `Viewport`. Cleanup occurs (`Data.close_all_exchanges`, layout saving, etc.).

## Data Flow

1.  **Input**:
    *   User interactions (GUI).
    *   Configuration (`config.json`, `config/user_layout.ini`).
    *   Credentials/API Keys (`.env`).
    *   Real-time market data (trades, order books) via `ccxt.pro` websockets.
    *   Historical OHLCV data via `ccxt` REST API calls.
2.  **Processing/Transformation**:
    *   Raw JSON/dict data from `ccxt` converted to internal structures/objects.
    *   Historical OHLCV data processed into Pandas DataFrames (`Data.fetch_candles`).
    *   Real-time trades aggregated into statistics (`MarketAggregator`).
    *   OHLCV DataFrames processed by `TechnicalAnalysis` to add indicator columns.
    *   Data formatted for GUI display (`ChartProcessor`, `OrderbookProcessor`, Widgets).
3.  **Storage**:
    *   Time-series market data (candles, trades, stats) optionally stored in `InfluxDB`.
    *   Fetched OHLCV data cached as files (likely pickle/parquet) in `data/cache/`.
    *   Configuration (`config.json`).
    *   GUI layout (`config/user_layout.ini`).
    *   Logs (`logs/`).
4.  **Output**:
    *   Visualizations rendered by Dear PyGui in the GUI.
    *   Data updates propagated to GUI widgets via the `SignalEmitter` queue processed by the main thread.
    *   Log messages.
    *   Data written to `InfluxDB`.
    *   Cache files written to disk.

**Key Data Structures:**

*   Pandas DataFrames: Used extensively for OHLCV data.
*   Dictionaries: Representing trades, order book levels, stats from `ccxt`.
*   `ccxt.pro` Exchange Objects: Managed by `CCXTInterface` / `Data`.
*   `Signals` Enum members (used as keys)
*   `queue.Queue` (internal to `SignalEmitter`)

## Dependencies

*   **External Libraries**:
    *   `asyncio`, `logging`, `argparse`, `os`, `json` (Python Standard Library)
    *   `python-dotenv`: Loading `.env` files.
    *   `dearpygui`: The GUI framework.
    *   `ccxt`, `ccxt.pro`: Interacting with crypto exchanges (REST & WebSockets).
    *   `influxdb-client`: Interacting with InfluxDB v2+.
    *   `pandas`: Data manipulation, especially for OHLCV data.
    *   GUI Framework: `PyQt` or `PySide` (Needs confirmation by checking imports in `gui` files).
    *   Potentially `numpy` (often used with `pandas`).
*   **External Services**:
    *   Cryptocurrency Exchanges (APIs & WebSockets).
    *   InfluxDB instance.
*   **Configuration Files**:
    *   `config.json`, `config/user_layout.ini`, `.env`, `logs/trade_suite_*.log`.
    *   `data/cache/*`: Cached OHLCV data files.

## Assumptions and Limitations

*   **GUI Framework**: Confirmed to be **Dear PyGui**. Docking capabilities are often used with DPG, supporting the `Viewport` concept.
*   **Order Execution**: Confirmed focus is data retrieval/display.
*   **`CandleFactory` Usage**: Role needs confirmation.
*   **`State` (`data/state.py`)**: Role remains unclear.
*   **Error Handling Details**: Specifics need deeper review.
*   **`MarketAggregator` Details**: Specifics need deeper review.

## Architecture Diagram

```mermaid
graph TD
    subgraph User Interface (GUI Layer - Dear PyGui)
        direction LR
        User -- Interacts --> VP[Viewport/Main Window]
        VP -- Runs --> DPG_RenderLoop{DPG Render Loop}
        VP -- Manages --> DBP[Dashboard Program/Widgets]
        VP -- Owns --> TM[Task Manager]
        DBP -- Displays --> DataViz[DPG Charts, Tables, etc.]
        DBP -- Initiates Tasks --> TM
        DPG_RenderLoop -- Calls --> SE_QueueProcessor(SignalEmitter.process_signal_queue)
        SE_QueueProcessor -- Executes --> Callbacks(Registered GUI Callbacks)
        Callbacks -- Update --> DBP
    end

    subgraph Core Logic
        direction TB

        subgraph Data Layer
            direction TB
            DATA[Data Source]:::data
            DATA -- Inherits/Uses --> CCXT_I(CCXT Interface):::data
            DATA -- Uses --> AGG[Market Aggregator]:::analysis
            DATA -- Uses --> IFX[InfluxDB Client]:::data
            DATA -- Emits --> SE([Signal Emitter]):::data # Emission happens here
            DATA -- Manages --> CACHE[(File Cache)]:::data
            CCXT_I -- Manages --> CCXTPRO((ccxt.pro Instances)):::data
            SE -- Contains --> SignalQueue[(Queue)] # Internal queue
        end

        subgraph Analysis Layer
            direction TB
            AGG -- Calculates Stats From --> TradesData(Trade Data)
            AGG -- Emits --> SE # Also emits signals
            TA[Technical Analysis]:::analysis -- Processes --> CandleData(Candle DataFrames)
            CP[Chart Processor]:::analysis -- Formats --> DataViz
            OBP[Orderbook Processor]:::analysis -- Formats --> DataViz
        end
    end

    subgraph External Systems
        direction TB
        EXCH[Exchanges API/WebSockets]
        INFLUXDB_SVC[(InfluxDB Service)]
    end

    subgraph Configuration & Entry
      direction TB
      MAIN[__main__.py]:::config -- Initializes --> CONF[Config Manager]:::config
      MAIN -- Initializes --> DATA
      MAIN -- Initializes --> IFX
      MAIN -- Initializes --> SE
      MAIN -- Launches --> VP
      CONF -- R/W --> CFG_JSON[config.json]
      VP -- R/W --> LAYOUT_INI[config/user_layout.ini]
      MAIN -- Reads --> DOTENV[.env]
      CCXT_I -- Reads --> DOTENV
    end

    %% Data Flow Arrows
    TM -- Calls Methods (async) --> DATA

    DATA -- Uses --> CCXTPRO # To call watch/fetch
    CCXTPRO -- Interacts --> EXCH

    DATA -- Writes/Reads --> IFX
    IFX -- Interacts --> INFLUXDB_SVC
    DATA -- Writes/Reads --> CACHE

    DATA -- Provides Raw Data --> AGG # Sends trades
    DATA -- Provides Data --> ANALYSIS_LAYER{Analysis Layer} # Direct call/return

    %% Signal/Queue Flow
    DATA -- emit(signal, data) --> SE # Background Thread
    AGG -- emit(signal, data) --> SE # Background Thread
    SE -- Puts (signal, data) --> SignalQueue # If background thread
    SE_QueueProcessor -- Gets (signal, data) --> SignalQueue # Main Thread

    %% GUI Update Flow
    Callbacks -- Receive --> Data(Signal Data)
    TA -- Provides Enriched DFs --> Callbacks
    CP -- Provides Formatted Data --> Callbacks
    OBP -- Provides Formatted Data --> Callbacks

    %% Style Definitions
    classDef data fill:#D6EAF8,stroke:#2874A6,stroke-width:1px;
    classDef analysis fill:#E8DAEF,stroke:#884EA0,stroke-width:1px;
    classDef gui fill:#D5F5E3,stroke:#1D8348,stroke-width:1px;
    classDef config fill:#FCF3CF,stroke:#B7950B,stroke-width:1px;
    classDef external fill:#FDEDEC,stroke:#C0392B,stroke-width:1px;

    class DATA,CCXT_I,IFX,CACHE,CCXTPRO,SE,SignalQueue data;
    class AGG,TA,CP,OBP analysis;
    class VP,DBP,TM,DataViz,DPG_RenderLoop,SE_QueueProcessor,Callbacks gui;
    class MAIN,CONF,CFG_JSON,LAYOUT_INI,DOTENV config;
    class EXCH,INFLUXDB_SVC external;
```

**Rendering Instructions:**

This diagram uses Mermaid syntax. You can render it using:
*   Online editors like the official Mermaid Live Editor (https://mermaid.live).
*   Markdown preview features in IDEs like VS Code (with appropriate extensions).
*   Command-line tools if you have Mermaid installed.
*   Copy and paste the code block into platforms that support Mermaid. 