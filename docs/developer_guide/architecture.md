# TradeSuite v2 Architecture

[//]: # (TOC)

## 1. Executive Snapshot
TradeSuite is a multi-exchange cryptocurrency trading platform built with DearPyGUI for the frontend and CCXT PRO for real-time data. It targets active traders needing a customizable, efficient view of market data (charts, order books, DOM) from multiple sources simultaneously. Its key differentiator is the optimized, shared data stream architecture allowing multiple widgets to display the same market (e.g., BTC/USDT) across different representations (e.g., 1m chart, 1h chart, order book) using a single WebSocket connection per exchange/symbol pair.

## 2. Guiding Principles
1.  **Decoupled Data Flow:** Data sources (streams, factories) must be independent of UI consumers (widgets). Communication via generic signals/queues identified by market data (exchange, symbol, timeframe), never widget IDs.
2.  **Centralized Resource Management:** `TaskManager` owns the lifecycle of data streams and processing tasks (like `CandleFactory`), using reference counting based on widget subscriptions.
3.  **Asynchronous Core:** All network I/O and data processing must occur asynchronously (`asyncio`) off the main UI thread to maintain responsiveness.
4.  **UI Thread Purity:** The DearPyGUI main loop thread must *only* handle UI rendering and event callbacks. No blocking operations allowed. Data updates are scheduled via DPG's `mvJobPool`.
5.  **Widget Encapsulation:** Widgets manage their own UI state and rendering logic, declaring data dependencies via `TaskManager.subscribe`. They filter incoming generic data based on their configuration.
6.  **Declarative Layout:** UI layout is defined in `.ini` files, allowing user customization without code changes.
7.  **Testability:** Components (TaskManager, DataSource, Widgets, Factories) should be designed for easier unit and integration testing (dependency injection, clear interfaces).

## 3. High-Level Diagram

```mermaid
graph TD
    subgraph User Interaction
        direction LR
        User -->|Menu Actions| Viewport
        User -->|Widget Interactions| Widgets
    end

    subgraph Application Core
        direction TB
        A[__main__] -->|CLI args, Env| B(Viewport)
        B -->|Creates/Manages| C(DashboardProgram)
        C -->|Manages/Creates| D{Widgets}
        C -->|Loads/Saves| E(DashboardManager/.ini)
        D -->|subscribe/unsubscribe| F(TaskManager)
        F -->|start/stop/manage| G(DataSource Tasks)
        F -->|start/stop/manage| H(CandleFactory Instances)
        G -->|Raw Data (Trades, OB)| F
        H -->|Processed Candles| F
        F -->|Data via Queues/DPG Jobs| D
        G -->|Network I/O| I[External Exchanges (CCXT PRO)]
    end

    User Interaction --> Application Core

```

## 4. Runtime Flow (Happy Path)
1.  **`[BOOT]`**: `python -m trade_suite` executes `src/trade_suite/__main__.py`.
2.  **`[BOOT]`**: Parses CLI args (`argparse`), loads `.env`, sets up logging.
3.  **`[BOOT]`**: Creates a `CoreServicesFacade` instance which sets up `SignalEmitter`, `CCXTInterface`, `DataFacade`, and `TaskManager` in `trade_suite.core`.
4.  **`[BOOT]`**: Instantiates `Viewport` and passes the `CoreServicesFacade`.
5.  **`[BOOT]`**: `Viewport` configures DPG (`docking=True`, `init_file='config/user_layout.ini'`), creates main window, viewport menu bar, and docking space.
6.  **`[BOOT]`**: `Viewport` instantiates `DashboardManager` (loads layout `.ini`) and `DashboardProgram`.
7.  **`[BOOT]`**: `Viewport` calls `DashboardProgram.initialize_program()`.
8.  **`[DASH]`**: `DashboardProgram` reads the layout from `DashboardManager`.
9.  **`[DASH]`**: `DashboardProgram._create_widgets_for_exchange()` iterates through widgets defined in the layout for the default exchange (e.g., 'coinbase').
10. **`[WIDGET]`**: For each widget config, calls `BaseWidget.create()` (e.g., `ChartWidget.create(...)`).
11. **`[WIDGET]`**: `BaseWidget.create()` generates a unique `window_tag`, creates the DPG window, and calls the widget's `_setup()` method.
12. **`[WIDGET]`**: Widget's `_setup()` method calls `TaskManager.subscribe()` with its required data keys (e.g., `StreamKey(type='candles', exchange='coinbase', symbol='BTC/USDT', timeframe='1h')`).
13. **`[TMGR]`**: `TaskManager.subscribe()` (running in its own thread) identifies required resources, increments reference counts.
14. **`[TMGR]`**: If ref count transitions 0 -> 1 for a resource:
    *   Starts the relevant `DataSource` task (e.g., `watch_trades`, `watch_orderbook`) via `asyncio.create_task` in its event loop. **`[DATA]`** `DataSource` establishes WebSocket connection.
    *   Creates `CandleFactory` instance if needed. **`[DATA]`** `CandleFactory` subscribes internally to necessary `NEW_TRADE` signals.
    *   Initiates fetch of initial historical data (e.g., `_fetch_initial_candles_for_factory`). **`[DATA]`** `DataSource` makes REST API calls.
15. **`[BOOT]`**: `Viewport` starts the DPG render loop (`dpg.start_dearpygui()`).
16. **`[DATA]`**: As data arrives (WebSocket messages, historical fetch results), `DataSource`/`CandleFactory` put it onto internal queues managed by `TaskManager`.
17. **`[TMGR]`**: `TaskManager` dequeues data, processes it (minimal processing, mainly routing), identifies subscribed widgets.
18. **`[TMGR]`**: `TaskManager` uses `dpg.submit_job()` to schedule UI updates on the main thread for each relevant widget, passing the data.
19. **`[WIDGET]`**: Widget's update callback (e.g., `_on_new_candles`) receives data, updates DPG items (plots, tables). First paint occurs as DPG processes these jobs.

## 5. Layer Cheat-Sheet
| Layer          | Dir / Module                           | Key Types                                   | "Only Talks To"                     | Primary Responsibility                        |
|----------------|----------------------------------------|---------------------------------------------|-------------------------------------|---------------------------------------------|
| **UI**         | `src/trade_suite/gui/widgets/`         | `BaseWidget` subclasses, `Viewport`         | DashboardProgram (via signals), TaskManager (subscribe/unsubscribe) | Rendering, User Input, Local State Mgmt     |
| **Dashboard**  | `src/trade_suite/gui/dashboard_program.py` | `DashboardProgram`, `DashboardManager`      | Viewport, TaskManager, Widgets (creation), Config | Widget Lifecycle, Layout Mgmt, Creation Dialogs |
| **Core Services** | `src/trade_suite/core/facade.py` | `CoreServicesFacade` | Viewport, DashboardProgram, AlertBot | Aggregates DataFacade, TaskManager, SignalEmitter |
| **Orchestration**| `src/trade_suite/core/task_manager.py`      | `TaskManager`, `StreamKey`                  | DataSource, CandleFactory, Widgets (data delivery), DPG Job Pool | Data Routing, Resource Lifecycle (Streams/Factories), Async Task Mgmt |
| **Data Source**| `src/trade_suite/core/data/data_source.py`  | `DataFacade`                                | External Exchanges (CCXT), TaskManager (queues) | Orchestrates `CacheStore`, `CandleFetcher`, `Streamer` |
| **Data Proc.** | `src/trade_suite/data/candle_factory.py`| `CandleFactory`                             | TaskManager (signals/queues)        | Trade Aggregation -> Candles              |
| **Config**     | `config/`, `.ini`, `src/trade_suite/config.py` | `ConfigManager` (implicitly via DPG/DashMgr) | Filesystem, (Read by DashboardManager, DPG) | Startup Settings, Layout Persistence        |
| **Shared**     | `src/trade_suite/core/signals.py`       | `SignalEmitter`, `Signals`                  | (Used by multiple layers)           | Application-wide Pub/Sub Events           |

## 6. Core Classes (Illustrative Signatures)

```python
# src/trade_suite/gui/viewport.py
class Viewport:
    def __init__(self, args): ...
    def run(self): ... # Configures DPG, creates DashboardProgram, starts loop
    def _configure_dpg(self): ...
    def _create_menu_bar(self): ...
```

```python
# src/trade_suite/gui/dashboard_program.py
class DashboardProgram:
    def __init__(self, viewport, task_manager, dashboard_manager, emitter): ...
    def initialize_program(self): ... # Reads layout, creates initial widgets
    def _create_widgets_for_exchange(self, exchange: str): ...
    def add_new_widget(self, widget_type: str, config: dict): ... # Instructs DashManager
    # Signal Handlers (_on_new_chart_requested, etc.)
```

```python
# src/trade_suite/gui/widgets/dashboard_manager.py
class DashboardManager:
    def __init__(self, config_dir: str = "config"): ...
    def load_layout(self, file: str): ... # Reads .ini, returns widget configs
    def save_layout(self, file: str): ... # Writes current DPG layout to .ini
    def add_widget(self, widget_instance: BaseWidget): ... # Tracks instance
    def remove_widget(self, widget_tag: str): ... # Removes tracking
```

```python
# src/trade_suite/gui/widgets/base_widget.py
class BaseWidget:
    def __init__(self, exchange: str, symbol: str | None = None, timeframe: str | None = None, instance_id: str | None = None): ...
    @classmethod
    def create(cls, *args, **kwargs) -> str: ... # Creates instance & DPG window, returns tag
    def show(self): ...
    def destroy(self): ... # Includes cleanup like unsubscribe
    def _setup(self): ... # Called after DPG window creation, place subscriptions here
    def _build_ui(self): ... # Abstract: Define DPG items here
    def _subscribe_to_data(self): ... # Abstract: Call TaskManager.subscribe
    def _cleanup(self): ... # Abstract: Call TaskManager.unsubscribe
```

```python
# src/trade_suite/core/task_manager.py
from collections import namedtuple
StreamKey = namedtuple('StreamKey', ['type', 'exchange', 'symbol', 'timeframe', 'misc'])

class TaskManager:
    def __init__(self, data_source, emitter): ...
    def subscribe(self, key: StreamKey, widget_tag: str, update_callback: Callable): ...
    def unsubscribe(self, key: StreamKey, widget_tag: str): ...
    def start(self): ... # Starts background thread and event loop
    def stop_all_tasks(self): ... # Cleanup on exit
    # Internal methods for task/factory management, data queuing, DPG job submission
```

```python
# src/trade_suite/core/data/data_source.py
class DataFacade:
    def __init__(self, influx, emitter, exchanges=None): ...
    async def watch_trades(self, symbol: str, exchange: str, stop_event: asyncio.Event) -> None: ...
    async def watch_orderbook(self, exchange: str, symbol: str, stop_event: asyncio.Event) -> None: ...
    async def fetch_candles(self, exchanges: list[str], symbols: list[str], since: str, timeframes: list[str]) -> dict[str, dict[str, pd.DataFrame]]: ...
    # Delegates to CacheStore, CandleFetcher, and Streamer
```

```python
# src/trade_suite/data/candle_factory.py
class CandleFactory:
    def __init__(self, exchange: str, symbol: str, timeframe: str, task_manager): ...
    def process_trade(self, trade_data: dict): ... # Updates internal state, potentially emits candle
    async def fetch_and_process_initial_trades(self, limit: int): ... # For seeding history if needed
    def get_initial_candles(self, num_candles: int) -> pd.DataFrame: ...
    def cleanup(self): ... # Unsubscribe from trade signals
```

## 7. Concurrency & Queues
*   **Event Loop:** A single `asyncio` event loop runs in a dedicated, non-daemon `threading.Thread` started by `TaskManager.start()`. This loop manages all `DataSource` tasks (WebSocket watchers, fetchers) and `CandleFactory` processing.
*   **UI Thread:** The main thread is exclusively managed by DearPyGUI after `dpg.start_dearpygui()` is called. It handles rendering and user input callbacks.
*   **Thread Communication:**
    *   **Data Source -> TaskManager:** `DataSource` uses thread-safe queues (likely `asyncio.Queue` accessed via `asyncio.run_coroutine_threadsafe` from `DataSource` if needed, or directly if `DataSource` methods run *in* the TaskManager loop) to pass raw data to the `TaskManager`'s event loop.
    *   **TaskManager -> UI:** `TaskManager` (from its background thread) uses `dpg.submit_job(callable, *args, **kwargs)` to schedule widget update callbacks (`callable`) to run safely on the main UI thread. This is DPG's mechanism for cross-thread UI updates.
*   **Data Fan-out:** `TaskManager` maintains internal dictionaries mapping `StreamKey` to lists of subscribed widget tags and their callbacks. When data arrives for a `StreamKey`, it iterates through the list and submits a DPG job for each subscriber.
*   **Back-pressure:** Currently implicit. If the UI thread falls behind processing `dpg.submit_job` calls, DPG's internal job queue will grow. The `asyncio.Queue` between `DataSource` and `TaskManager` could also grow if `TaskManager` processing is slow.
    *   *Open TODO:* Instrument queue sizes (`asyncio.Queue.qsize()`, monitor DPG performance). Consider strategies if queues grow unbounded (e.g., dropping intermediate order book updates, notifying user).

## 8. Configuration & Persistence
*   **Layout:** `config/user_layout.ini` stores the DPG docking layout, window positions, and sizes. It's loaded by DPG via `dpg.configure_app(init_file=...)`. It also contains metadata for each widget window (like `exchange`, `symbol`, `timeframe`) stored using `dpg.set_value` on hidden items or inferred from the window label/tag structure managed by `DashboardManager` during save/load. `DashboardManager` orchestrates reading widget metadata on load and saving it before DPG writes the layout.
*   **Factory Default:** `config/factory_layout.ini` serves as the default if `user_layout.ini` is missing or reset.
*   **Widget Registration:** Implicit. `DashboardProgram` knows which widget classes correspond to menu items/layout types (e.g., 'chart' -> `ChartWidget`). See `DashboardProgram._create_widgets_for_exchange` and `add_new_widget`. Adding a new widget requires updating `DashboardProgram` and potentially the `File` menu in `Viewport`.
*   **Hot-reload:** Not implemented. Application restart required for layout changes beyond DPG's runtime docking adjustments.
*   **Environment:** API keys and service endpoints are configured via `.env` file, loaded using `python-dotenv` in `__main__`.

## 9. Error Handling Contract
*   **DataSource Errors:** Network errors, API errors, or WebSocket disconnects within `DataSource` tasks are caught. Retry logic (e.g., exponential backoff for fetches, reconnect attempts for WebSockets) is implemented within `DataSource`. Persistent failures are logged with `[ERR]` tag. `TaskManager` may be notified to potentially update widget state to "Error" or "Disconnected".
*   **TaskManager Errors:** Errors within `TaskManager`'s own logic (e.g., bad data processing, subscription errors) are logged `[ERR]`. Should ideally not crash the task manager thread.
*   **Widget Errors:** Errors during widget initialization (`_setup`, `_build_ui`) or data updates (`_on_new_candles`, etc.) running on the UI thread are caught by a global DPG error handler (if configured) or potentially crash the UI. Uncaught exceptions bubble up, get logged `[ERR]`, and might be presented via a simple modal/toast if a global handler exists.
*   **UI Feedback:** Widgets should visually indicate connection/data issues (e.g., grayed-out chart, status bar message) based on error signals or lack of recent data received from `TaskManager`.

## 10. Extension Points
*   **Adding a New Exchange:**
    1.  Verify CCXT(PRO) support for the exchange.
    2.  Update UI elements (e.g., exchange selection dialogs in `DashboardProgram`) to include the new exchange ID.
    3.  Ensure `DataSource` handles any exchange-specific nuances (authentication methods, endpoint overrides if needed). Usually handled by CCXT.
    4.  Test thoroughly.
*   **Adding a New Widget:**
    1.  Create a new class inheriting from `src/trade_suite/gui/widgets/base_widget.py`.
    2.  Implement `_build_ui()` to define its DPG items.
    3.  Implement `_subscribe_to_data()` to call `TaskManager.subscribe()` for needed `StreamKey`s.
    4.  Implement data handling callbacks (e.g., `_on_new_data(self, data)`) to update the UI via DPG functions.
    5.  Implement `_cleanup()` to call `TaskManager.unsubscribe()`.
    6.  Add UI entry point:
        *   Create a signal (e.g., `NEW_MYWIDGET_REQUESTED`) in `Signals`.
        *   Add a menu item in `Viewport._create_menu_bar` that emits this signal.
        *   Add a handler in `DashboardProgram` (e.g., `_on_new_mywidget_requested`) that shows a configuration dialog (if needed) and calls `DashboardManager.add_widget(MyWidget(...))`.
    7.  Update `DashboardProgram._create_widgets_for_exchange` and `DashboardManager` save/load logic if the widget needs to be persisted in the layout.
*   **Embedding a Third-Party Model:**
    1.  Decide where it fits:
        *   *Data processing:* Integrate as a new step within `TaskManager` or a dedicated processor analogous to `CandleFactory`. Triggered by relevant data `StreamKey`s. Output becomes a new `StreamKey` type.
        *   *Widget-specific analysis:* Integrate directly within a widget's data handling callbacks. Requires model loading/inference within the widget or a helper class it owns.
    2.  Handle model loading (potentially async if large).
    3.  Ensure inference runs appropriately (async task if long-running, direct call if fast) without blocking UI or core data flow.
    4.  Display results in a new or existing widget.

## 11. Known Pain & Planned Refactors
*   See [`docs/REFACTOR.md`](REFACTOR.md) for the completed major data flow refactor.
*   See [`docs/CLEANUP_PLAN.md`](CLEANUP_PLAN.md) (if exists) or GitHub Issues for ongoing items like:
    *   Performance optimization for `PriceLevelWidget`.
    *   Refining default `factory_layout.ini`.
    *   Robustness testing, especially around edge cases (rapid connect/disconnect, unusual market data).
    *   Formalizing the widget metadata saving/loading within `.ini` files via `DashboardManager`.

## 12. Appendix: Glossary + Abbreviations
*   **DPG:** DearPyGUI, the immediate-mode GUI library used.
*   **CCXT / CCXT PRO:** Library for interacting with cryptocurrency exchange APIs (REST / WebSocket).
*   **Widget:** A dockable DearPyGUI window, typically inheriting from `BaseWidget`, representing a specific UI feature (Chart, Order Book).
*   **Window Tag / Tag:** Unique DearPyGUI identifier for a window or item, used for referencing (e.g., `dpg.get_value(tag)`). Often derived from `instance_id`.
*   **Instance ID:** A unique logical identifier for a widget instance, often based on its configuration (e.g., `coinbase_BTC/USDT_1h`). Used to generate the `window_tag`.
*   **TaskManager (TMGR):** Central orchestrator managing data subscriptions, background async tasks, and data delivery to widgets.
*   **DataSource:** Component responsible for all communication with external exchange APIs via CCXT.
*   **CandleFactory:** Component responsible for processing raw trades into OHLCV candles for a specific market/timeframe.
*   **StreamKey:** A named tuple identifying a specific data stream or requirement (e.g., trades for 'coinbase' 'BTC/USDT'). Used for subscriptions.
*   **Emitter / Signals:** Pub/Sub system (`SignalEmitter`) used for application-wide, non-data-flow events (e.g., requesting new widget creation).
*   **Layout:** The arrangement of widgets within the main application window, managed by DPG's docking system and persisted in `.ini` files.
*   **DOM:** Depth of Market, often visualized as aggregated buy/sell orders at discrete price levels. Handled by `PriceLevelWidget`.
*   **OB:** Order Book. 