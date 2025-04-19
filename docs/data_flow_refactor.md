# Data Flow Refactoring Plan

## 0. Background Context & Key Components

This document outlines the necessary refactoring steps to fix the data flow architecture in the Trade Suite application. The core problem is that data streams (like trades and order books) and processed data (like candles) are tightly coupled to specific UI widget instances via a `tab` parameter (which corresponds to the widget's unique `window_tag`). This prevents multiple widgets from efficiently sharing and displaying the same underlying market data.

**Key Components Involved:**

*   **`SignalEmitter` (`gui/signals.py`):** A pub/sub system for event communication.
*   **`DockableWidget` (`gui/widgets/base_widget.py`):** Base class for UI widgets. Generates a unique `window_tag`. Needs methods/callbacks for setup (`subscribe` to `TaskManager`) and cleanup (`unsubscribe` from `TaskManager`).
*   **Specific Widgets (`gui/widgets/...`):** `ChartWidget`, `OrderbookWidget`, `PriceLevelWidget`, `TradingWidget`. Inherit from `DockableWidget`. Store their configuration (`exchange`, `symbol`, `timeframe`). Will register generic signal handlers and filter based on their config. Will handle internal config changes (e.g., symbol change) by updating subscriptions with `TaskManager`.
*   **`Data` (`data/data_source.py`):** Handles interaction with the CCXT library, fetches market data, and initiates WebSocket streams (`watch_trades`, `watch_orderbook`). Will no longer receive or use the `tab` parameter for these stream methods. Puts raw data onto `TaskManager.data_queue` tagged only with market identifiers (`exchange`, `symbol`, `trade_data`/`orderbook`).
*   **`TaskManager` (`gui/task_manager.py`):** Manages asyncio tasks for data streams and centralized `CandleFactory` instances in a separate thread. Uses `data_queue` for thread-safe communication. Manages resource lifecycles (streams, factories) via reference counting triggered by `subscribe`/`unsubscribe` calls from widgets. Emits generic data signals (`NEW_TRADE`, `ORDER_BOOK_UPDATE`, `NEW_CANDLES`) tagged only with market identifiers.
*   **`CandleFactory` (`data/candle_factory.py`):** **One instance per unique `(exchange, symbol, timeframe)` combination**, managed by `TaskManager`. Subscribes to generic `NEW_TRADE` signals, filters by its `exchange`/`symbol`, processes trades directly against its internal candle state (DataFrame), and emits generic `UPDATED_CANDLES` signals tagged with its `exchange`/`symbol`/`timeframe`. Does **not** use an internal queue/batching for live trades.
*   **`ChartProcessor` (`data/chart_processor.py`):** **To be removed or significantly repurposed.** Its role in live candle generation is superseded by `CandleFactory`. May have residual use for initial bulk history processing if complex logic is needed there, but aim to eliminate.

### Notes: 

Testing Strategy - Avoiding the "Start App & Wait" Grind:
This is a super important point. We absolutely need a better way to test than just running the whole thing manually. Here are some strategies we should aim for as we implement:
Unit Testing:
CandleFactory: This is prime for unit tests. We can feed its _on_new_trade method (after refactoring) specific sequences of mock trade data (dicts) and assert that its internal candle DataFrame state is updated correctly (correct OHLCV values, correct timestamps, new bars created when expected). We don't need live data or signals for this.
TaskManager (Subscription Logic): We can write tests to verify the reference counting. Mock out the actual start_task/stop_task/CandleFactory creation calls. Then, simulate subscribe and unsubscribe calls from mock widgets and assert that the reference counts (stream_ref_counts, factory_ref_counts) are correct and that the (mocked) start/stop/create/delete functions are called only when the counts transition between 0 and 1.
Widget Filtering: Test the _on_* data handlers in widgets. Create a widget instance, manually call its handler (e.g., widget._on_updated_candles(...)) with various signal payloads (correct exchange/symbol/timeframe, incorrect ones), and assert that the widget's internal state (or a mock UI update function) is only affected when the filter conditions match.
Mocking Dependencies:
Data / CCXT: When testing TaskManager or CandleFactory, we don't need real CCXT streams. We can mock Data.watch_trades, Data.watch_orderbook, and Data.fetch_candles. For streams, the mock could yield pre-defined trade/orderbook data. For fetch_candles, it returns a sample DataFrame.
SignalEmitter: We can use a real SignalEmitter instance in tests but control the signals being sent manually or via mocked components, allowing us to test the publish/subscribe flow between components without the full UI or network stack.
DearPyGui (dpg): For unit/integration tests that don't need visual verification, mock out dpg calls within widgets to avoid errors about DPG context not being initialized or needing a running event loop.
Integration Testing (Smaller Scale):
Test the flow: Mock Widget -> TaskManager.subscribe -> TaskManager (starts mock stream/factory) -> Mock Stream (yields trade) -> TaskManager (emits NEW_TRADE) -> CandleFactory (_on_new_trade) -> CandleFactory (emits UPDATED_CANDLES) -> Mock Widget (_on_updated_candles). This verifies the core interaction paths using mocked streams/UI but real TaskManager, CandleFactory, and signal handlers.
Fixtures / Recorded Data: Store sample trade sequences or candle DataFrames in files (e.g., JSON, CSV, Pickle) to use as consistent input for tests.
Setting up a test framework (like pytest) and adopting these strategies early will save massive amounts of time and frustration compared to purely manual testing. We can build confidence in each refactored piece as we go.


## 1. Detailed Summary of Issues

The current data flow architecture suffers from several issues stemming from a tight coupling between data streams/signals and specific UI widget instances (`window_tag`/`tab`), preventing efficient data sharing and causing unexpected behavior when multiple widgets display the same market.

*   **Issue 1: Tab-Based Signal Routing:** Signals (`NEW_TRADE`, `NEW_CANDLES`, `UPDATED_CANDLES`, `NEW_ORDERBOOK`) are emitted with a `tab` parameter corresponding to the specific originating/target widget's `window_tag`.
    *   *Evidence:*
        *   `TaskManager._update_ui_with_trades`: `self.data.emitter.emit(Signals.NEW_TRADE, tab, exchange, trades)`
        *   `TaskManager._update_ui_with_candles`: `self.data.emitter.emit(Signals.NEW_CANDLES, tab, exchange, candles)`
        *   `TaskManager._update_ui_with_orderbook`: `self.data.emitter.emit(Signals.NEW_ORDERBOOK, tab, exchange, orderbook)`
        *   `CandleFactory._process_trade_batch`: `self.emitter.emit(Signals.UPDATED_CANDLES, tab=self.tab, ...)`
    *   *Problem:* Data is explicitly addressed to a single widget, making sharing impossible via the pub/sub mechanism.
    *   *Files Affected:* `gui/task_manager.py`, `data/candle_factory.py`

*   **Issue 2: Tab-Based Signal Handling:** Widgets filter incoming signals by comparing the signal's `tab` parameter to their own `window_tag`. Widgets miss data not explicitly tagged for them, even if relevant (e.g., a second chart for the same market won't get updates tagged for the first chart).
    *   *Evidence:*
        *   `ChartWidget._on_new_candles`: `if tab == self.window_tag and exchange == self.exchange:`
        *   `ChartWidget._on_updated_candles`: `if tab == self.window_tag and exchange == self.exchange:`
        *   `OrderbookWidget._on_order_book_update`: `if exchange != self.exchange: return` (implicitly assumes signal is relevant if exchange matches, but the `tab` parameter exists in the signature, suggesting potential confusion or leftover code). Needs update based on Step 1.3.
        *   `PriceLevelWidget._on_order_book_update`: `if exchange != self.exchange or not self.is_created: return` (Similar to OrderbookWidget).
        *   `CandleFactory._on_new_trade`: `if tab == self.tab:` (Filters trades before processing).
    *   *Problem:* Widgets only react to data specifically addressed to them, ignoring potentially relevant data for the same market tagged for a different widget instance.
    *   *Files Affected:* `gui/widgets/chart_widget.py`, `gui/widgets/orderbook_widget.py`, `gui/widgets/price_level_widget.py`, `data/candle_factory.py`, `gui/widgets/trading_widget.py`

*   **Issue 3: Stream Task Hijacking/Restarting (Trades):** `TaskManager.start_stream_for_chart` uses a generic task name for trades (`trades_{exchange}_{symbol}`) but **does not check if it's already running** before calling `start_task`. The `start_task` method stops any existing task with the same name before starting the new one. Furthermore, the `wrapped_watch_trades` coroutine initiated by `start_task` uses the specific `tab` of the *requesting* widget.
    *   *Evidence:*
        *   `TaskManager.start_stream_for_chart`: Defines `trades_task = f"trades_{exchange}_{symbol}"` but calls `self.start_task(trades_task, coro=wrapped_watch_trades())` without checking `is_stream_running`.
        *   `TaskManager.start_task`: `if name in self.tasks: self.stop_task(name)`
        *   `TaskManager.start_stream_for_chart`: `wrapped_watch_trades` uses the `tab` variable from the outer scope, which is the requesting widget's tag: `await self.data.watch_trades(tab=tab, ...)`
    *   *Problem:* When a second chart for the same market is created, it stops the trade stream serving the first chart and restarts it, now associated only with the second chart's `tab`. The first chart stops receiving trade data for candle processing.
    *   *Files Affected:* `gui/task_manager.py` (`start_stream_for_chart`, `start_task`)

*   **Issue 4: Per-Widget Candle Processing:** A separate `CandleFactory` instance is created for *each* `ChartWidget` within `TaskManager.start_stream_for_chart`, keyed by the widget's `window_tag` (`tab`) in `self.data.candle_factories`. Each factory processes trades tagged only for its specific widget (due to Issue 1 & 2).
    *   *Evidence:*
        *   `TaskManager.start_stream_for_chart`: Creates `CandleFactory(..., tab=tab, ...)` and stores it: `self.data.candle_factories[tab] = candle_factory`.
    *   *Problem:* Redundant processing. Multiple charts for the same market/timeframe require identical candle data, but each processes trades independently and inefficiently. Prevents sharing of calculated candles.
    *   *Files Affected:* `gui/task_manager.py` (`start_stream_for_chart`), `data/candle_factory.py`

*   **Issue 5: Order Book Signal Mismatch:** `TaskManager._update_ui_with_orderbook` emits `Signals.NEW_ORDERBOOK`, but `OrderbookWidget` and `PriceLevelWidget` listen for `Signals.ORDER_BOOK_UPDATE`.
    *   *Evidence:*
        *   `TaskManager`: `self.data.emitter.emit(Signals.NEW_ORDERBOOK, tab, exchange, orderbook)`
        *   `OrderbookWidget`: `self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)`
        *   `PriceLevelWidget`: `self.emitter.register(Signals.ORDER_BOOK_UPDATE, self._on_order_book_update)`
    *   *Problem:* Order book widgets likely never receive live updates via the signal system due to listening for the wrong signal name.
    *   *Files Affected:* `gui/task_manager.py`, `gui/widgets/orderbook_widget.py`, `gui/widgets/price_level_widget.py`

*   **Issue 6: Duplicate Widget Tag Collision:** Manually adding a widget with the exact same configuration (e.g., chart with same exchange/symbol/timeframe, or order book with same exchange/symbol) results in the same `instance_id` being generated by the widget's `__init__`. This leads to `DockableWidget.__init__` creating the same `window_tag`. `DockableWidget.create` detects the duplicate tag via `dpg.does_item_exist`, logs an error, and returns the existing tag without creating a new DPG window.
    *   *Evidence:*
        *   `ChartWidget.__init__`: `instance_id = f"{exchange}_{symbol}_{timeframe}"` if None.
        *   `OrderbookWidget.__init__`: `instance_id = f"{exchange}_{symbol}"` if None.
        *   `gui/dashboard_program.py` (`create_chart`, `create_orderbook`): Instantiates widgets without providing an `instance_id`, triggering default generation.
        *   `DockableWidget.create`: `if dpg.does_item_exist(self.window_tag): logging.error(...) return self.window_tag`
    *   *Problem:* Although DPG doesn't crash, the second widget object exists but has no corresponding UI window. This leads to user confusion and potentially inconsistent state in `DashboardManager`.
    *   *Files Affected:* `gui/dashboard_program.py` (manual add dialogs), `gui/widgets/chart_widget.py`, `gui/widgets/orderbook_widget.py`, `gui/widgets/base_widget.py` (`create`)

## 2. Target Architecture & Ideal Data Flow

The goal is to decouple data streams and signals from specific UI widgets, enabling efficient sharing and subscription based on the *data source* (exchange, symbol, timeframe), managed centrally by `TaskManager` using reference counting.

**Conceptual Flow:**

1.  **Widget Creation:** UI requests a new widget (e.g., Chart for BTC/USD 1h). `DashboardProgram` ensures a unique `instance_id` (e.g., `coinbase_btcusd_1h_2`). Widget stores its configuration (`exchange`, `symbol`, `timeframe`).
2.  **Subscription Request:** Widget initialization (or `DashboardManager` after adding) calls `TaskManager.subscribe(widget_instance, requirements={'type': 'candles', 'exchange': '...', 'symbol': ..., 'timeframe': ...})`.
3.  **Resource Management & Stream Starting (`TaskManager`):**
    *   Receives subscription request. Determines required resources (e.g., `trades_CB_BTCUSD` stream, `CF(CB, BTC/USD, 1h)` factory).
    *   Increments reference count for each required resource.
    *   **If resource count goes 0 -> 1:**
        *   Starts the required stream (`Data.watch_*`) using a generic task ID (`trades_exchange_symbol`, `orderbook_exchange_symbol`), **without `tab`**. Ensures stream task is not already running. `Data.watch_*` puts raw data tagged with `exchange`/`symbol` onto `TaskManager.data_queue`.
        *   Creates the required `CandleFactory(exchange, symbol, timeframe)` if it doesn't exist in `self.candle_factories` (keyed by `(exchange, symbol, timeframe)`). The factory subscribes itself to `NEW_TRADE`.
    *   If required, fetches initial historical candles (`_fetch_candles_with_queue`), putting data tagged with `exchange`, `symbol`, `timeframe` onto `data_queue`.
4.  **Generic Signal Emission (`TaskManager`):**
    *   `_process_data_queue` retrieves items (raw trades, order books, initial candles) tagged with market identifiers.
    *   Calls `_update_ui_with_*` methods (signatures updated to use market identifiers, not `tab`).
    *   These methods emit generic signals via `emitter.emit`:
        *   `NEW_TRADE` (payload: `exchange`, `trade_data`)
        *   `ORDER_BOOK_UPDATE` (payload: `exchange`, `orderbook`) - *Note: Signal name corrected.*
        *   `NEW_CANDLES` (payload: `exchange`, `symbol`, `timeframe`, `candles`)
    *   **Crucially, no `tab` parameter is used in signal emissions.**
5.  **Centralized Candle Processing (`CandleFactory`):**
    *   The specific `CandleFactory(exchange, symbol, timeframe)` instance receives generic `NEW_TRADE` signals.
    *   Its `_on_new_trade` handler filters based on `if exchange == self.exchange and trade_data.get('symbol') == self.symbol:`.
    *   If matched, it processes the trade directly against its internal candle DataFrame state.
    *   If the DataFrame is updated, it emits a generic `UPDATED_CANDLES` signal (payload: `exchange`, `symbol`, `timeframe`, `candles`).
6.  **Widget Subscription & Filtering:**
    *   All widgets (`ChartWidget`, `OrderbookWidget`, etc.) register listeners for the relevant generic signals (`ORDER_BOOK_UPDATE`, `NEW_TRADE`, `NEW_CANDLES`, `UPDATED_CANDLES`).
    *   Their handler methods (`_on_*`) receive parameters like `exchange`, `symbol`, `timeframe`, etc. (NO `tab`).
    *   Each handler filters the incoming signal based on whether the signal's identifiers match the widget's *own* configuration (e.g., `if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:`).
    *   If the data matches, the widget updates its UI.
7.  **Widget Closure / Config Change:**
    *   User closes widget window / Widget changes symbol/timeframe.
    *   Cleanup logic (e.g., `DockableWidget.on_close` callback via `DashboardManager`) calls `TaskManager.unsubscribe(widget_instance)`. For config change, widget also calls `TaskManager.subscribe` with new requirements.
    *   `TaskManager.unsubscribe` decrements reference counts for resources used by the widget.
    *   **If resource count drops to 0:** `TaskManager` stops the stream task and removes the `CandleFactory` instance.

**Ideal Signal Payloads (Keywords):**

*   `ORDER_BOOK_UPDATE`: `exchange: str`, `orderbook: dict` (containing `symbol`, `bids`, `asks`, etc.)
*   `NEW_TRADE`: `exchange: str`, `trade_data: dict` (containing `symbol`, `price`, `amount`, `timestamp`, etc.)
*   `NEW_CANDLES`: `exchange: str`, `symbol: str`, `timeframe: str`, `candles: pd.DataFrame` (initial bulk history)
*   `UPDATED_CANDLES`: `exchange: str`, `symbol: str`, `timeframe: str`, `candles: pd.DataFrame` (live updates from factory)

## 3. Detailed Implementation Roadmap

This roadmap breaks the refactor into manageable steps. Each step should ideally result in a testable intermediate state.

**Phase 1: Signal Correction and Basic Decoupling (Order Books)**

*   **Step 1.1: Fix Order Book Signal Mismatch:**
    *   **Rationale:** Corrects the typo preventing order book widgets from receiving any signal updates.
    *   **Action:** In `gui/task_manager.py`, locate the `_update_ui_with_orderbook` method. Change the `emit` call from `self.data.emitter.emit(Signals.NEW_ORDERBOOK, ...)` to `self.data.emitter.emit(Signals.ORDER_BOOK_UPDATE, ...)`.
    *   **Files:** `gui/task_manager.py`
    *   **Verification:** Check logs or UI behavior to confirm order book widgets *start* receiving signal calls (though filtering might still be wrong).

*   **Step 1.2: Standardize Order Book Signal Payload & Stream Call:**
    *   **Rationale:** Removes the widget-specific `tab` from the signal payload and the underlying stream initiation, preparing for generic handling.
    *   **Action 1 (TaskManager):** In `gui/task_manager.py`, `_update_ui_with_orderbook`, modify the `emit` call:
        *   Change `self.data.emitter.emit(Signals.ORDER_BOOK_UPDATE, tab, exchange, orderbook)` to `self.data.emitter.emit(Signals.ORDER_BOOK_UPDATE, exchange=exchange, orderbook=orderbook)`.
    *   **Action 2 (Data Queue):** In `gui/task_manager.py`, `_process_data_queue`, ensure the call to `_update_ui_with_orderbook` passes `exchange=data.get('exchange')` and `orderbook=data.get('orderbook')`. The `tab` from `data.get('tab')` should no longer be passed.
    *   **Action 3 (Data Source):** In `data/data_source.py`, `watch_orderbook`:
        *   Remove the `tab` parameter from the function signature.
        *   Locate the point where data is put onto the `TaskManager`'s queue (this might happen indirectly via `TaskManager.start_task` wrapping the coroutine or directly if `watch_orderbook` itself queues). Ensure the queued item contains `{'type': 'orderbook', 'exchange': exchange, 'orderbook': latest_orderbook}` and **no `tab`**. *Self-correction: `watch_orderbook` is called by `TaskManager`, which puts data on the queue via `_process_data_queue` -> `_update_ui_with_orderbook`. The key is to modify `TaskManager.start_stream_for_chart` / `start_task` / `wrapped_watch_orderbook` and the manual order book creation in `DashboardProgram` to *not* pass the `tab` parameter to `Data.watch_orderbook` if it's only used for queuing/signaling.* Let's simplify: Ensure the `wrapped_watch_orderbook` in `TaskManager` (and the direct call in `DashboardProgram._show_new_orderbook_dialog`) calls `await self.data.watch_orderbook(exchange=exchange, symbol=symbol)` (removing `tab`). Adjust `Data.watch_orderbook` signature accordingly. The queuing mechanism in `TaskManager` already extracts `exchange` and `orderbook`.
    *   **Files:** `gui/task_manager.py`, `data/data_source.py`, `gui/dashboard_program.py`
    *   **Verification:** Check logs for `ORDER_BOOK_UPDATE` signals being emitted without the `tab` parameter. Ensure `watch_orderbook` runs without errors after signature change.

*   **Step 1.3: Update Order Book Widget Handlers:**
    *   **Rationale:** Makes widgets filter incoming generic signals based on their own market configuration.
    *   **Action (OrderbookWidget):** In `gui/widgets/orderbook_widget.py`, modify `_on_order_book_update`:
        *   Change signature from `def _on_order_book_update(self, tab, exchange, orderbook):` to `def _on_order_book_update(self, exchange: str, orderbook: dict):`.
        *   Change filtering logic. Replace any initial check involving `tab` or just `exchange` with `if exchange != self.exchange or orderbook.get('symbol') != self.symbol: return`.
    *   **Action (PriceLevelWidget):** In `gui/widgets/price_level_widget.py`, modify `_on_order_book_update` similarly:
        *   Change signature from `def _on_order_book_update(self, tab, exchange, orderbook):` to `def _on_order_book_update(self, exchange: str, orderbook: dict):`.
        *   Change filtering logic. Replace `if exchange != self.exchange or not self.is_created:` with `if not self.is_created or exchange != self.exchange or orderbook.get('symbol') != self.symbol: return`.
    *   **Files:** `gui/widgets/orderbook_widget.py`, `gui/widgets/price_level_widget.py`
    *   **Goal:** Order book widgets filter data based on the market they display. Multiple order books for the same market should now update correctly from the single shared stream.
    *   **Verification:** Create two `OrderbookWidget` instances for the same market. Verify both update simultaneously. Check logs in the handlers to see filtering logic working.

**Phase 2: Decouple Trade and Candle Flow**

*   **Step 2.1: Standardize Trade Signal Payload & Stream Call:**
    *   **Rationale:** Removes `tab` from `NEW_TRADE` signal and underlying stream call, analogous to Step 1.2 for order books.
    *   **Action 1 (TaskManager Emit):** In `gui/task_manager.py`, `_update_ui_with_trades`, modify the `emit` call:
        *   Change `self.data.emitter.emit(Signals.NEW_TRADE, tab, exchange, trades)` to `self.data.emitter.emit(Signals.NEW_TRADE, exchange=exchange, trade_data=trades)`. (Assuming `trades` here is the single trade dictionary `trade_data`). If `trades` is a list, emit `trade_data=trades[0]` or loop. Let's assume it's `trade_data`. Check actual `trades` type passed. *Correction: Log shows `trade_data=trades[0]` in `data_source.py`, but `_update_ui_with_trades` receives `trades`. Let's assume `trades` is the dict.* Modify to `self.data.emitter.emit(Signals.NEW_TRADE, exchange=exchange, trade_data=trades)`.
    *   **Action 2 (Data Queue):** In `gui/task_manager.py`, `_process_data_queue`, ensure the call to `_update_ui_with_trades` passes `exchange=data.get('exchange')` and `trade_data=data.get('trades')`. No `tab`.
    *   **Action 3 (Data Source):** In `data/data_source.py`, `watch_trades`:
        *   Remove the `tab` parameter from the function signature.
        *   Ensure the queued item (likely via `TaskManager`'s wrapper) contains `{'type': 'trades', 'exchange': exchange, 'trades': trade_data}` (or the single trade dict) and **no `tab`**. Similar to 1.2, modify `TaskManager.start_stream_for_chart`'s `wrapped_watch_trades` to call `await self.data.watch_trades(exchange=exchange, symbol=symbol, ...)` (removing `tab`). Adjust `Data.watch_trades` signature.
    *   **Files:** `gui/task_manager.py`, `data/data_source.py`
    *   **Verification:** Check logs for `NEW_TRADE` signals emitted without `tab`. Ensure `watch_trades` runs without errors.

*   **Step 2.2: Update Trading Widget Handler:**
    *   **Rationale:** Makes `TradingWidget` filter generic trades based on its market.
    *   **Action:** In `gui/widgets/trading_widget.py`, modify `_on_new_trade`:
        *   Change signature to `def _on_new_trade(self, exchange: str, trade_data: dict):`.
        *   Implement filtering: `trade_symbol = trade_data.get('symbol')
if exchange != self.exchange or trade_symbol != self.symbol: return`.
    *   **Files:** `gui/widgets/trading_widget.py`
    *   **Verification:** Open multiple `TradingWidget` instances. Verify each only displays trades for its configured market.

*   **Step 2.3: Refactor TaskManager Trade Stream Start (Add Check):**
    *   **Rationale:** Prevents the trade stream from being stopped and restarted unnecessarily, enabling sharing.
    *   **Action:** In `gui/task_manager.py`, `start_stream_for_chart`:
        *   Locate the line defining `trades_task = f"trades_{exchange}_{symbol}"`.
        *   **Before** the `self.start_task(trades_task, ...)` call for trades, **add** the check: `if not self.is_stream_running(trades_task):`. Indent the `start_task` call and any related logging under this `if`.
        *   Ensure the `wrapped_watch_trades` coroutine (defined within `start_stream_for_chart`) no longer uses the `tab` variable when calling `self.data.watch_trades` (as done in Step 2.1).
    *   **Files:** `gui/task_manager.py`
    *   **Verification:** Add logging inside the `if not self.is_stream_running(trades_task):` block. Create two charts for the same market. Verify the log message "Starting trade stream..." appears only once for that market. Check that the trade stream task is not stopped/restarted in logs when the second chart is added.

*   **Step 2.4: Centralize CandleFactory Management:**
    *   **Rationale:** Creates a single source of truth for candle data per market/timeframe, eliminating redundant processing.
    *   **Action 1 (TaskManager/Data):** Decide where to store the central factories. `TaskManager` seems appropriate. Add a dictionary attribute `self.candle_factories = {}` in `TaskManager.__init__`. The key will be `(exchange, symbol, timeframe)`.
    *   **Action 2 (TaskManager Logic):** In `TaskManager.start_stream_for_chart`:
        *   Remove the line `self.data.candle_factories[tab] = candle_factory`.
        *   Define `factory_key = (exchange, symbol, timeframe)`.
        *   Add check: `if factory_key not in self.candle_factories:`
        *   Inside the `if`, move the `CandleFactory` instantiation. **Crucially, remove the `tab=tab` argument** from the constructor call: `candle_factory = CandleFactory(exchange=exchange, emitter=self.data.emitter, ..., timeframe_str=timeframe)`. Adjust `CandleFactory.__init__` signature in the next step.
        *   Store the new factory: `self.candle_factories[factory_key] = candle_factory`.
        *   Add logging for factory creation/reuse.
    *   **Action 3 (CandleFactory Constructor):** In `data/candle_factory.py`, `__init__`:
        *   Remove the `tab` parameter from the signature.
        *   Remove the line `self.tab = tab`.
    *   **Files:** `gui/task_manager.py`, `data/candle_factory.py`
    *   **Verification:** Add logging for `CandleFactory` creation in `TaskManager`. Create two charts for the same market/timeframe. Verify the factory is created only once. Create a chart for a different timeframe and verify a *new* factory is created.

*   **Step 2.5: Adapt CandleFactory Processing (Filtering & Emission):**
    *   **Rationale:** Makes the central `CandleFactory` listen to generic trades, filter correctly, and emit generic candle updates.
    *   **Action 1 (Filtering):** In `data/candle_factory.py`, `_on_new_trade`:
        *   Remove the `tab` parameter from the signature.
        *   Change the filtering logic from `if tab == self.tab:` to `if exchange == self.exchange and trade_data.get('symbol') == self.symbol:`. Adjust logging messages that refer to `self.tab`.
    *   **Action 2 (Emission):** In `data/candle_factory.py`, `_process_trade_batch` and `try_resample`:
        *   Modify the `self.emitter.emit(Signals.UPDATED_CANDLES, ...)` calls.
        *   Remove the `tab=self.tab` parameter.
        *   Ensure `exchange=self.exchange`, `symbol=self.symbol`, `timeframe=self.timeframe_str` (or equivalent) are included as keyword arguments. Example: `self.emitter.emit(Signals.UPDATED_CANDLES, exchange=self.exchange, symbol=self.symbol, timeframe=self.timeframe_str, candles=updated_candles)`.
    *   **Files:** `data/candle_factory.py`
    *   **Verification:** Check logs for `CandleFactory` confirming it filters trades correctly based on its `exchange`/`symbol`. Check logs for `UPDATED_CANDLES` emission, ensuring `tab` is absent and `exchange`, `symbol`, `timeframe` are present.

*   **Step 2.6: Standardize Candle Signal Payloads (`NEW_CANDLES`):**
    *   **Rationale:** Ensures the initial candle load signal is also generic.
    *   **Action 1 (TaskManager Emit):** In `gui/task_manager.py`, `_update_ui_with_candles`:
        *   Modify the `emit` call: `self.data.emitter.emit(Signals.NEW_CANDLES, tab, exchange, candles)` to `self.data.emitter.emit(Signals.NEW_CANDLES, exchange=exchange, symbol=symbol, timeframe=timeframe, candles=candles)`.
        *   **IMPORTANT:** The `symbol` and `timeframe` are not directly available here. The `candles` data likely originates from `_fetch_candles_with_queue`. The queued item needs to be augmented to include `symbol` and `timeframe`. Modify `_fetch_candles_with_queue` to put `{'type': 'candles', 'tab': tab, 'exchange': ..., 'symbol': symbols[0], 'timeframe': timeframes[0], 'candles': ...}` onto the queue.
        *   Modify `_process_data_queue` to extract `symbol` and `timeframe` from the `data` dict and pass them to `_update_ui_with_candles`.
        *   Modify `_update_ui_with_candles` signature to accept `symbol` and `timeframe`.
    *   **Files:** `gui/task_manager.py`
    *   **Verification:** Check logs for `NEW_CANDLES` emission, ensuring `tab` is absent and `exchange`, `symbol`, `timeframe` are present.

*   **Step 2.7: Update Chart Widget Handlers:**
    *   **Rationale:** Makes charts filter generic initial (`NEW_CANDLES`) and updated (`UPDATED_CANDLES`) candle signals based on their market/timeframe.
    *   **Action (`_on_new_candles`):** In `gui/widgets/chart_widget.py`:
        *   Change signature from `def _on_new_candles(self, tab, exchange, candles):` to `def _on_new_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):`.
        *   Change filtering logic from `if tab == self.window_tag and exchange == self.exchange:` to `if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:`.
    *   **Action (`_on_updated_candles`):** In `gui/widgets/chart_widget.py`:
        *   Change signature from `def _on_updated_candles(self, tab, exchange, candles):` to `def _on_updated_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):`.
        *   Change filtering logic from `if tab == self.window_tag and exchange == self.exchange:` to `if exchange == self.exchange and symbol == self.symbol and timeframe == self.timeframe:`. Adjust logging.
    *   **Files:** `gui/widgets/chart_widget.py`
    *   **Verification:** Create two charts for the same market/timeframe. Verify both receive initial candles (`NEW_CANDLES`) and subsequent updates (`UPDATED_CANDLES`) simultaneously from the single shared `CandleFactory`. Create charts for different timeframes/symbols and verify they only update from their respective data.

**Phase 3: Subscription, Cleanup, and Finalizing**

*   **Step 3.1: Implement Subscription & Resource Management in TaskManager:**
    *   **Action:**
        *   Add `self.stream_ref_counts = defaultdict(int)` and `self.factory_ref_counts = defaultdict(int)` to `TaskManager.__init__`. Also `self.widget_subscriptions = defaultdict(set)`.
        *   Implement `TaskManager.subscribe(self, widget, requirements: dict)`:
            *   Parse `requirements` (type, exchange, symbol, timeframe).
            *   Determine needed resources (e.g., `'trades_exch_sym'`, `'cf_exch_sym_tf'`).
            *   Store `widget` reference mapped to its requirements/resources.
            *   For each needed resource: increment ref count. If count becomes 1, start stream (using `start_task` internally, checking `is_stream_running`) or create `CandleFactory` (storing in `self.candle_factories`). Trigger initial candle fetch (`_get_candles_for_market`) if needed.
        *   Implement `TaskManager.unsubscribe(self, widget)`:
            *   Find resources used by `widget` from `self.widget_subscriptions`.
            *   Remove widget subscription mapping.
            *   For each resource: decrement ref count. If count becomes 0, stop stream (`stop_task`) or delete factory (from `self.candle_factories`).
    *   **Files:** `gui/task_manager.py`

*   **Step 3.2: Integrate Subscription with Widget Lifecycle:**
    *   **Action:**
        *   In `DockableWidget` base class or individual widget `__init__` / `setup`, call `task_manager.subscribe(self, self.get_requirements())`.
        *   Ensure `DashboardManager` (when handling widget closure via DPG callbacks) calls `task_manager.unsubscribe(widget)`.
    *   **Files:** `gui/widgets/base_widget.py`, `gui/widgets/*_widget.py`, `gui/dashboard_manager.py`

*   **Step 3.3: Refactor Configuration Changes (Symbol/Timeframe):**
    *   **Action:**
        *   Remove `_on_symbol_changed` from `DashboardProgram`.
        *   In `ChartWidget` (and others if applicable), modify UI callbacks for symbol/timeframe changes:
            1.  Call `self.task_manager.unsubscribe(self)`.
            2.  Update `self.symbol` / `self.timeframe`.
            3.  Call `self.task_manager.subscribe(self, self.get_requirements())`.
            4.  Clear old data / request refresh if necessary.
    *   **Files:** `gui/widgets/chart_widget.py`, `gui/dashboard_program.py` (remove handler)

*   **Step 3.4: Address Duplicate Widget Creation:**
    *   **Action:** In `gui/dashboard_program.py` (or wherever manual widgets are created), before instantiating, check `DashboardManager` for existing widgets with the *exact same configuration*. If found, generate a unique suffix and pass a unique `instance_id` (e.g., `f"{exchange}_{symbol}_{timeframe}_2"`) to the constructor.
    *   **Files:** `gui/dashboard_program.py`

*   **Step 3.5: Review and Remove Obsolete `tab` Usage:**
    *   **Action:** Perform global search for `tab`. Remove its usage entirely from signal payloads, function arguments, and internal logic related to data routing or configuration changes. Replace config change signaling with direct calls or passing widget instances if necessary.
    *   **Files:** Potentially many.

*   **Step 3.6: Remove/Repurpose `ChartProcessor`:**
    *   **Action:** Delete `data/chart_processor.py` if it's no longer needed. Remove its instantiation and usage from `CandleFactory` and potentially `TaskManager`.
    *   **Files:** `data/candle_factory.py`, `gui/task_manager.py`, `data/chart_processor.py` (delete)

*   **Step 3.7: Testing:**
    *   **Action:** Comprehensive testing as described in the original plan, focusing on shared streams, independent timeframes, dynamic widget add/close/reconfigure, and resource cleanup.

This updated plan provides a more detailed and robust roadmap for the refactor. 