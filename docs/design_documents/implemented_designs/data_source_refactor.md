# Data Flow Refactoring Plan - **COMPLETED**

## 0. Background Context & Key Components **[COMPLETED]**

This document outlines the necessary refactoring steps to fix the data flow architecture in the Trade Suite application. The core problem is that data streams (like trades and order books) and processed data (like candles) are tightly coupled to specific UI widget instances via a `tab` parameter (which corresponds to the widget's unique `window_tag`). This prevents multiple widgets from efficiently sharing and displaying the same underlying market data.

**Key Components Involved:**

*   **`SignalEmitter` (`gui/signals.py`):** A pub/sub system for event communication.
*   **`DockableWidget` (`gui/widgets/base_widget.py`):** Base class for UI widgets. Generates a unique `window_tag`. Needs methods/callbacks for setup (`subscribe` to `TaskManager`) and cleanup (`unsubscribe` from `TaskManager`).
*   **Specific Widgets (`gui/widgets/...`):** `ChartWidget`, `OrderbookWidget`, `PriceLevelWidget`, `TradingWidget`. Inherit from `DockableWidget`. Store their configuration (`exchange`, `symbol`, `timeframe`). Will register generic signal handlers and filter based on their config. Will handle internal config changes (e.g., symbol change) by updating subscriptions with `TaskManager`.
*   **`Data` (`data/data_source.py`):** Handles interaction with the CCXT library, fetches market data, and initiates WebSocket streams (`watch_trades`, `watch_orderbook`). Will no longer receive or use the `tab` parameter for these stream methods. Puts raw data onto `TaskManager.data_queue` tagged only with market identifiers (`exchange`, `symbol`, `trade_data`/`orderbook`).
*   **`TaskManager` (`gui/task_manager.py`):** Manages asyncio tasks for data streams and centralized `CandleFactory` instances in a separate thread. Uses `data_queue` for thread-safe communication. Manages resource lifecycles (streams, factories) via reference counting triggered by `subscribe`/`unsubscribe` calls from widgets. Emits generic data signals (`NEW_TRADE`, `ORDER_BOOK_UPDATE`, `NEW_CANDLES`) tagged only with market identifiers.
*   **`CandleFactory` (`data/candle_factory.py`):** **One instance per unique `(exchange, symbol, timeframe)` combination**, managed by `TaskManager`. Subscribes to generic `NEW_TRADE` signals, filters by its `exchange`/`symbol`, processes trades directly against its internal candle state (DataFrame), and emits generic `UPDATED_CANDLES` signals tagged with its `exchange`/`symbol`/`timeframe`. Does **not** use an internal queue/batching for live trades.
*   **`ChartProcessor` (`data/chart_processor.py`):** **To be removed or significantly repurposed.** Its role in live candle generation is superseded by `CandleFactory`. May have residual use for initial bulk history processing if complex logic is needed there, but aim to eliminate.


## 1. Detailed Summary of Issues **[ADDRESSED by Refactor]**

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

## 2. Target Architecture & Ideal Data Flow **[IMPLEMENTED]**

The goal was to decouple data streams and signals from specific UI widgets, enabling efficient sharing and subscription based on the *data source* (exchange, symbol, timeframe), managed centrally by `TaskManager` using reference counting. **This architecture has now been successfully implemented.**

**Conceptual Flow (Implemented):**

1.  **Widget Creation:** UI requests a new widget. `DashboardProgram` ensures a unique `instance_id`. Widget stores its config.
2.  **Subscription Request:** Widget calls `TaskManager.subscribe` with its requirements.
3.  **Resource Management & Stream Starting (`TaskManager`):** TaskManager determines resources, increments ref counts. Starts streams/creates factories on 0->1 transitions using generic IDs/keys. Fetches initial data.
4.  **Generic Signal Emission (`TaskManager`):** Processes queue items, emits generic signals (`NEW_TRADE`, `ORDER_BOOK_UPDATE`, `NEW_CANDLES`) with market identifiers, no `tab`.
5.  **Centralized Candle Processing (`CandleFactory`):** Central instances (per market/timeframe) filter generic `NEW_TRADE`, process, emit generic `UPDATED_CANDLES` (single candle update).
6.  **Widget Subscription & Filtering:** Widgets listen to generic signals, filter based on their own config, update UI.
7.  **Widget Closure / Config Change:** Widget calls `TaskManager.unsubscribe`. TaskManager decrements counts, cleans up resources (stops streams, deletes factories) when count reaches 0.

**Ideal Signal Payloads (Implemented Keywords):**

*   `ORDER_BOOK_UPDATE`: `exchange: str`, `orderbook: dict`
*   `NEW_TRADE`: `exchange: str`, `trade_data: dict`
*   `NEW_CANDLES`: `exchange: str`, `symbol: str`, `timeframe: str`, `candles: pd.DataFrame`
*   `UPDATED_CANDLES`: `exchange: str`, `symbol: str`, `timeframe: str`, `candles: pd.DataFrame` (single candle row)

## 3. Detailed Implementation Roadmap - **COMPLETED**

This roadmap was followed to achieve the refactoring.

**Phase 1: Signal Correction and Basic Decoupling (Order Books) **[COMPLETED]**

*   **Step 1.1: Fix Order Book Signal Mismatch:** **[COMPLETED]**
*   **Step 1.2: Standardize Order Book Signal Payload & Stream Call:** **[COMPLETED]**
*   **Step 1.3: Update Order Book Widget Handlers:** **[COMPLETED]**

**Phase 2: Decouple Trade and Candle Flow **[COMPLETED]**

*   **Step 2.1: Standardize Trade Signal Payload & Stream Call:** **[COMPLETED]**
*   **Step 2.2: Update Trading Widget Handler:** **[COMPLETED]**
*   **Step 2.3: Refactor TaskManager Trade Stream Start (Add Check):** **[COMPLETED]**
*   **Step 2.4: Centralize CandleFactory Management:** **[COMPLETED]**
*   **Step 2.5: Adapt CandleFactory Processing (Filtering & Emission):** **[COMPLETED]**
*   **Step 2.6: Standardize Candle Signal Payloads (`NEW_CANDLES`):** **[COMPLETED]**
*   **Step 2.7: Update Chart Widget Handlers:** **[COMPLETED]**

**Phase 3: Subscription, Cleanup, and Finalizing **[COMPLETED]**

*   **Step 3.1: Implement Subscription & Resource Management in TaskManager:** **[COMPLETED]**
*   **Step 3.2: Integrate Subscription with Widget Lifecycle:** **[COMPLETED]**
*   **Step 3.3: Refactor Configuration Changes (Symbol/Timeframe):** **[COMPLETED]**
*   **Step 3.4: Address Duplicate Widget Creation:** **[COMPLETED]**
*   **Step 3.5: Review and Remove Obsolete `tab` Usage:** **[COMPLETED]**
*   **Step 3.6: Remove/Repurpose `ChartProcessor`:** **[COMPLETED]** (Removed `ChartProcessor` entirely)
*   **Step 3.7: Testing:** **[NEXT STEP - See Section 4]**

## 4. Refactoring Conclusion & Next Steps

**Status:** The data flow refactoring outlined in this plan has been successfully completed. The application now utilizes a decoupled architecture where data streams and processing are managed centrally by `TaskManager` and `CandleFactory`, enabling efficient sharing of resources between widgets. Widgets subscribe to generic signals and filter based on their own configuration.

**Verification:** Manual testing and detailed logging analysis confirm that:
*   Multiple widgets for the same market (e.g., 1h and 5m charts for BTC/USD) share the same underlying data streams (`watch_trades`).
*   Separate `CandleFactory` instances are correctly created and managed per unique market/timeframe combination.
*   Reference counting correctly prevents duplicate stream tasks and cleans up resources when widgets are closed or reconfigured.
*   Data flows correctly from streams -> TaskManager -> Factories/Widgets via generic signals.

**Immediate Next Step: Comprehensive Testing**

While manual testing indicates success, the complexity of the data flow necessitates robust automated testing, as originally outlined in Section 0 (`Testing Strategy`). This is critical to ensure reliability and catch potential edge cases or race conditions missed during development.

**Recommended Testing Focus:**
1.  **Unit Tests:**
    *   `CandleFactory`: Verify candle calculation logic with various trade sequences (including edge cases like trades exactly on boundaries, out-of-order trades if possible, large volume trades).
    *   `TaskManager`: Test `subscribe`/`unsubscribe` logic thoroughly, mocking stream/factory start/stop, and asserting correct reference counts and resource lifecycle function calls.
    *   Widget Handlers: Test the filtering logic in `_on_*` methods of all relevant widgets.
2.  **Integration Tests:**
    *   Test the core flow: `Widget -> subscribe -> TaskManager -> Factory/Stream -> TaskManager -> emit -> Factory/Widget -> update` using mocked components where appropriate (especially network/DPG).
    *   Test configuration changes (symbol/timeframe) and widget closure, verifying resource cleanup (`unsubscribe` leading to stream stop/factory deletion when ref count hits 0).

**Future Action: Architecture Documentation**

Once testing provides sufficient confidence, a separate architecture document should be created. This document will formally describe the *new*, implemented data flow, serving as a reference for future development and maintenance. It should include diagrams illustrating the component interactions and data pathways.

**Well done on completing this significant refactor!**