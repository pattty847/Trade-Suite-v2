Okay, this is excellent. Understanding the broader `trade_suite` architecture is key to making the `alert_bot` a well-integrated and powerful feature, both within the GUI and as a standalone terminal application.

You're right, `dearpygui` often requires a good amount of setup, and it looks like `trade_suite` has a solid foundation with `__main__.py` initializing core components like `Data` and `ConfigManager`, and `viewport.py` setting up `TaskManager`, `DashboardManager`, and the DPG rendering loop.

Let's continue exploring. You want me to look deeper into `CandleFactory.py` (specifically resampling and data access) and `TaskManager.py` to see how they manage data flow and tasks. This will directly inform how the `AlertDataManager` (our proposed bridge) will interact with the existing `trade_suite` systems.

First, I'll request the rest of `CandleFactory.py` to see the resampling logic and how data is accessed from it.


Read file: trade_suite/data/candle_factory.py
This is very insightful! The `CandleFactory.py` is quite comprehensive.

Here are the key takeaways relevant to our `alert_bot` integration:

*   **`try_resample(self, new_timeframe: str, active_exchange)`:**
    *   This method resamples the factory's *internal* `self.ohlcv` DataFrame to a `new_timeframe`.
    *   It converts the `timeframe_str` (e.g., "5m", "1h") to a pandas resampling rule (e.g., "5T", "1H").
    *   It uses standard pandas resampling functions (`.first()` for open, `.max()` for high, etc.).
    *   **Crucially, after a successful resample, it updates `self.ohlcv` to *become* the resampled data and changes `self.timeframe_str` and `self.timeframe_seconds` to match the `new_timeframe`.**
    *   It then emits `Signals.UPDATED_CANDLES` with the *entire newly resampled DataFrame*.
    *   **Implication for Alerts:** If an alert needs 1H data, and the factory's base is 1m, calling `try_resample("1h", ...)` will make the factory *become* a 1H factory internally. This means a single `CandleFactory` instance, as it stands, is geared towards serving *one primary timeframe at a time* (the one it's currently set to after any resampling).
    *   **This is a critical point.** For the `alert_bot` to monitor, say, a 5-minute chart and a 1-hour chart for the *same symbol* simultaneously, we would either need:
        1.  **Multiple `CandleFactory` instances:** One for BTC/USD 1m (base), one for BTC/USD 5m (resampled from a 1m factory, or its own base if available), one for BTC/USD 1H, etc. The `TaskManager` would manage these.
        2.  **Modification to `CandleFactory`:** Change it to maintain its original base candles (e.g., 1m) *and* also store/serve various resampled versions without overwriting its internal state. This would be more complex for `CandleFactory` but potentially more efficient if many alerts use different timeframes of the same symbol.

*   **`get_candle_data(self) -> pd.DataFrame`:**
    *   This method returns a *copy* of the current internal `self.ohlcv` DataFrame. This is the primary way to access the candle data from the factory.
    *   The data returned will be of the factory's *current* `timeframe_str` (which could be the original base or a resampled one).

*   **`set_initial_data(self, initial_candles_df: pd.DataFrame)`:**
    *   This method is robust. It handles various `dates` column formats (numeric, datetime64, strings) and attempts to convert them to seconds since the epoch.
    *   This is used by `TaskManager` to seed the factory with historical data.

*   **`cleanup(self)`:**
    *   Properly unregisters its listener from the `emitter`, which is good for preventing memory leaks when a factory is no longer needed.

**Thinking about the `alert_bot` and `AlertDataManager`:**

Given how `CandleFactory.try_resample` works (by changing its internal state), the **multiple `CandleFactory` instances** approach seems more aligned with the current design of `trade_suite`.

Here's how the `AlertDataManager` could work with this:

1.  **Configuration Parsing:** When `AlertDataManager` starts (or when `alerts_config.yaml` is loaded/updated):
    *   It identifies all unique `(exchange, symbol, timeframe)` combinations required by active alert rules.
    *   For each unique combination, it will request the `TaskManager` to ensure a `CandleFactory` for that specific `(exchange, symbol, timeframe)` exists.

2.  **`CandleFactory` Instantiation and Management by `TaskManager` (Hypothetical Flow):**
    *   If `AlertDataManager` requests candles for "coinbase", "BTC/USD", "1h":
        *   **Option A (Direct Factory for Target Timeframe):** `TaskManager` could try to create a `CandleFactory` directly for "1h". This factory would be seeded with historical "1h" data fetched by `Data.fetch_candles(..., timeframe="1h")`. It would then listen to live trades and attempt to build "1h" candles directly. (This is less common; most exchanges provide finer-grained trades that you build up).
        *   **Option B (Base Factory + Resampling on Demand/Subscription):** This seems more likely and flexible.
            1.  `TaskManager` first ensures a **base `CandleFactory`** exists, e.g., for "coinbase", "BTC/USD", "1m". This "1m" factory is seeded with historical "1m" data and processes live trades to update "1m" candles.
            2.  When the "1h" data is needed, the `AlertDataManager` (or `TaskManager` on its behalf) could:
                *   **Scenario 1 (Resample and Cache):** Ask the "1m" factory to `try_resample` to "1h". The "1m" factory *becomes* a "1h" factory. This isn't ideal if we also need the "1m" data live.
                *   **Scenario 2 (Separate Resampled Factory):** The `TaskManager` creates a *new* `CandleFactory` instance specifically for "coinbase", "BTC/USD", "1h". This new "1h" factory could be seeded by:
                    *   Asking the "1m" factory for its current "1m" `ohlcv` data.
                    *   Resampling this "1m" data to "1h" *within the new "1h" factory's initialization*.
                    *   The new "1h" factory would then need a way to get updates. Does it listen to the "1m" factory's `UPDATED_CANDLES` (for 1m) and then run its own resampling logic? Or does it also listen to raw trades and build 1h candles? The former (listening to the base factory's updates) seems cleaner.

    The current `CandleFactory` `try_resample` method modifies its own state. This suggests that if you want "1m", "5m", and "1h" data for BTC/USD, you'd likely have three `CandleFactory` instances managed by `TaskManager`. The "5m" and "1h" factories might be "derived" factories that are somehow fed by the "1m" factory or by resampling its initial data and then building upon it.

3.  **Data Access for Alert Rules:**
    *   The alert rule engine, when it needs "coinbase", "BTC/USD", "1h" data, would ask `AlertDataManager`.
    *   `AlertDataManager` would retrieve the corresponding `CandleFactory` (managed by `TaskManager`) for "1h".
    *   It would then call `factory.get_candle_data()` to get the latest "1h" DataFrame.

**Moving `watchTicker` to `Data` class:**

*   Yes, this is a good idea. `Data` should be the sole interface to `ccxt.pro` for fetching/streaming.
*   `Data` can have a `watch_ticker(exchange, symbol, callback)` method.
*   `TaskManager` can manage these ticker streams.
*   The `TickerStreamer` in `alert_bot` would then register a callback with `AlertDataManager`, which in turn uses `Data.watch_ticker`.

**Standalone `alert_bot` vs. GUI Feature:**

This architecture supports both:

*   **GUI Feature:** The `Viewport` initializes `Data` and `TaskManager`. The `alert_bot` module (perhaps started from a menu item) would get these instances. The `AlertDataManager` would then use them to set up the necessary `CandleFactory` instances and streams. Alerts could trigger UI notifications through the `SignalEmitter`.
*   **Standalone Terminal App:** A separate `main_alert_bot.py` script would:
    1.  Initialize `SignalEmitter` (maybe a simpler console-logging version).
    2.  Initialize `Data` (configured via `alerts_config.yaml` or command-line for exchanges).
    3.  Initialize `TaskManager` (passing it `Data`).
    4.  Initialize `AlertDataManager` (passing it `Data` and `TaskManager`).
    5.  `AlertDataManager` reads `alerts_config.yaml` and starts requesting factories/streams.
    6.  Alerts would log to the console or send notifications via other means (email, Telegram, etc.).
    The key is that the core `alert_bot` logic (rule evaluation, `AlertDataManager`) is decoupled from the `dearpygui` specifics and relies on the interfaces provided by `Data` and `TaskManager`.

**Next Exploration: `TaskManager.py`**

Now, let's look at how `TaskManager.py` actually manages these `CandleFactory` instances and other tasks. Specifically:

*   How does it decide to create a new `CandleFactory`?
*   How does it handle the `set_initial_data` call?
*   How are different timeframes for the same symbol handled? Does it create multiple factories?
*   How does it manage `Data.watch_trades`, `Data.watch_orderbook`, and potentially `Data.watch_ticker` streams?

This will help solidify the plan for `AlertDataManager`.


Read file: trade_suite/gui/task_manager.py
`TaskManager.py` provides a very clear picture of how resources are managed! This is a well-structured system using reference counting and a subscription model, which is excellent.

Here's how it works and its implications for the `alert_bot`:

**Key Mechanisms in `TaskManager`:**

1.  **Resource Keys:**
    *   `_get_resource_keys(self, requirements: dict)`: This helper translates a widget's data `requirements` (e.g., type: 'candles', exchange: 'coinbase', symbol: 'BTC/USD', timeframe: '1h') into unique resource keys.
    *   For `'candles'`, it generates two keys:
        *   `factory_key = (exchange, symbol, timeframe)`: A tuple for the `CandleFactory`.
        *   `trade_stream_key = f"trades_{exchange}_{symbol}"`: A string for the underlying raw trade stream that feeds the factory.
    *   For `'trades'`, it generates `trade_stream_key = f"trades_{exchange}_{symbol}"`.
    *   For `'orderbook'`, it generates `orderbook_stream_key = f"orderbook_{exchange}_{symbol}"`.

2.  **Subscription Model (`subscribe` / `unsubscribe`):**
    *   Widgets (or in our case, the `AlertDataManager` acting on behalf of alert rules) `subscribe` with their data `requirements`.
    *   `subscribe` increments reference counts (`factory_ref_counts`, `stream_ref_counts`) for each required resource key.
    *   **`CandleFactory` Creation:**
        *   If a `factory_key`'s ref count becomes 1 (first subscriber):
            *   It checks if a `CandleFactory` for that exact `(exchange, symbol, timeframe)` tuple already exists in `self.candle_factories`.
            *   If not, it **creates a new `CandleFactory` instance** for that specific `exchange`, `symbol`, and `timeframe`.
            *   It then schedules `_fetch_initial_candles_for_factory` to run, which calls `Data.fetch_candles` for that *specific timeframe* and then `factory.set_initial_data()`.
    *   **Stream Task Creation (e.g., `watch_trades`):**
        *   If a `trade_stream_key`'s ref count becomes 1:
            *   It checks if a task for this stream is already running.
            *   If not, it creates a `stop_event` for the stream and starts the appropriate coroutine from `Data` (e.g., `self.data.watch_trades(exchange, symbol, stop_event)`).
    *   `unsubscribe` decrements ref counts. If a count reaches 0:
        *   The corresponding `CandleFactory` is cleaned up (`factory.cleanup()`) and removed.
        *   The corresponding stream task has its `stop_event` cleared and the task is cancelled (`self.stop_task(key)`).

3.  **Handling Different Timeframes:**
    *   **Crucially, `TaskManager` creates a distinct `CandleFactory` for each unique `(exchange, symbol, timeframe)` tuple requested.**
    *   This means if a widget (or alert rule) needs "BTC/USD" "1h" candles and another needs "BTC/USD" "5m" candles, `TaskManager` will create and manage *two separate `CandleFactory` instances*:
        *   One keyed as `('coinbase', 'BTC/USD', '1h')`
        *   Another keyed as `('coinbase', 'BTC/USD', '5m')`
    *   Each of these factories will be independently seeded with historical data for *its own timeframe* by `_fetch_initial_candles_for_factory` calling `Data.fetch_candles(..., timeframes=[timeframe], ...)`.
    *   Each factory listens to the *same* underlying raw trade stream (e.g., `trades_coinbase_BTC/USD`) to build its respective candles.

4.  **Raw Trade Stream (`watch_trades`):**
    *   There's only one `watch_trades` task per `(exchange, symbol)`.
    *   Multiple `CandleFactory` instances (e.g., for 1m, 5m, 1h of BTC/USD) will all be fed by (i.e., listen to signals from) this single raw trade stream for BTC/USD. The `CandleFactory._on_new_trade` method gets all trades for the symbol and then processes them to build candles for *its specific configured timeframe*.

**Implications and Plan for `AlertDataManager`:**

This existing `TaskManager` structure is almost perfectly suited for the `alert_bot`'s needs, especially regarding different timeframes. The idea of `CandleFactory` resampling *itself* was a slight misinterpretation; `TaskManager` manages separate factories per timeframe.

1.  **`AlertDataManager` Role:**
    *   When `alerts_config.yaml` is processed, `AlertDataManager` will determine all unique `(exchange, symbol, timeframe)` tuples needed for OHLCV-based alerts, and also all unique `(exchange, symbol)` pairs for CVD (trade-based) or ticker-based alerts.
    *   It will then call `TaskManager.subscribe(self, requirements)` for each.
        *   For an alert needing "BTC/USD" "1h" SMA20: `requirements = {'type': 'candles', 'exchange': 'coinbase', 'symbol': 'BTC/USD', 'timeframe': '1h'}`. `TaskManager` will ensure a `CandleFactory` for `('coinbase', 'BTC/USD', '1h')` is running and seeded.
        *   For an alert needing "ETH/USD" "5m" CVD:
            *   It would subscribe for `{'type': 'candles', 'exchange': 'coinbase', 'symbol': 'ETH/USD', 'timeframe': '5m'}` (if CVD uses the candle factory's output, or if other rules need these candles).
            *   *Alternatively*, if CVD is calculated purely from raw trades (as `TradeStreamer` currently does), it might subscribe for `{'type': 'trades', 'exchange': 'coinbase', 'symbol': 'ETH/USD'}`. The `AlertDataManager` would then route these raw trades to the appropriate `CVDCalculator`. This seems more aligned with the current `TradeStreamer` design.
        *   For an alert needing "BTC/USD" bid/ask prices: `requirements = {'type': 'ticker', 'exchange': 'coinbase', 'symbol': 'BTC/USD'}` (assuming we add 'ticker' as a resource type).

2.  **Data Flow for Alerts:**
    *   **OHLCV Data:**
        *   `AlertDataManager` subscribes to the required `(exchange, symbol, timeframe)` via `TaskManager`.
        *   `TaskManager` ensures the correct `CandleFactory` is running and seeded.
        *   The `CandleFactory` emits `Signals.UPDATED_CANDLES` (or `Signals.NEW_CANDLES` for initial load).
        *   `AlertDataManager` will have registered a listener with `SignalEmitter` for these signals.
        *   When an update for, say, `('coinbase', 'BTC/USD', '1h')` arrives, `AlertDataManager` provides this DataFrame to the relevant alert rules for evaluation.
    *   **CVD Data (Raw Trades):**
        *   `AlertDataManager` subscribes for `{'type': 'trades', 'exchange': 'coinbase', 'symbol': 'BTC/USD'}`.
        *   `TaskManager` ensures `Data.watch_trades` is running for "BTC/USD".
        *   `Data.watch_trades` (as per `data_source.py`) emits `Signals.NEW_TRADE`.
        *   `AlertDataManager` listens for `Signals.NEW_TRADE`. When a trade for "BTC/USD" arrives, it passes it to the `CVDCalculator` for "BTC/USD".
        *   The `CVDCalculator` updates, and `AlertDataManager` makes the new CVD value available to alert rules.
        *   The original `TradeStreamer.py` will be refactored. Its `CVDCalculator` and `TradeData` classes are useful. The main `TradeStreamer` class will become part of `AlertDataManager` or a helper class it uses, responsible for managing `CVDCalculator` instances and processing trades received from `AlertDataManager`. It will no longer directly use `ccxt.pro`.
    *   **Ticker Data:**
        *   We'll need to add a `watch_ticker` method to `Data` in `data_source.py`.
        *   `TaskManager` will need to be updated to handle a `'ticker'` resource type in `_get_resource_keys` and manage `Data.watch_ticker` streams.
        *   `AlertDataManager` will subscribe, listen for `Signals.NEW_TICKER_DATA` (a new signal), and provide it to alert rules. The existing `TickerStreamer.py` from `alert_bot` can be refactored similarly to `TradeStreamer` – its core logic for processing/storing ticker data would be managed by `AlertDataManager`.

3.  **Historical Data for Lookbacks:**
    *   `TaskManager._fetch_initial_candles_for_factory` already uses `calculate_since(ccxt_exchange, timeframe, num_candles=1000)` to get a decent amount of historical data (1000 candles for the *specific timeframe* of the factory).
    *   The `alert_bot` (when parsing `alerts_config.yaml`) will need to determine if this default 1000 candles is sufficient for all its indicators on that timeframe. For very long lookbacks (e.g., SMA200 on daily candles = 200 days), 1000 daily candles is more than enough. For a 200-period SMA on 1-minute candles, 1000 minutes is ~16 hours, which might be okay for some strategies but could be short for others that need more context.
    *   We might need to:
        *   Allow `alerts_config.yaml` to specify a desired history length for a symbol/timeframe.
        *   Modify `_fetch_initial_candles_for_factory` or provide a way for `AlertDataManager` to request a deeper history when subscribing if the default `num_candles=1000` isn't enough for a particular alert's lookback requirements.

**Refined Plan - `AlertDataManager` as the Central Hub:**

*   `AlertDataManager` is initialized with `Data`, `TaskManager`, and `SignalEmitter` from `trade_suite`.
*   It parses `alerts_config.yaml`.
*   For each alert:
    *   Determines data needs (OHLCV specific timeframes, raw trades for CVD, ticker data).
    *   Calls `task_manager.subscribe(self, requirement_dict)` for each need.
    *   `requirement_dict` will be something like:
        *   `{'type': 'candles', 'exchange': ex, 'symbol': sym, 'timeframe': tf}`
        *   `{'type': 'trades', 'exchange': ex, 'symbol': sym}`
        *   `{'type': 'ticker', 'exchange': ex, 'symbol': sym}` (after we add ticker support)
    *   Registers listeners with `SignalEmitter` for `Signals.UPDATED_CANDLES`, `Signals.NEW_TRADE`, `Signals.NEW_TICKER_DATA`.
*   When data signals arrive:
    *   `UPDATED_CANDLES(exchange, symbol, timeframe, candles_df)`: `AlertDataManager` passes `candles_df` to rules needing that specific `(exchange, symbol, timeframe)`.
    *   `NEW_TRADE(exchange, trade_data)`: `AlertDataManager` routes `trade_data` to the appropriate `CVDCalculator` (if CVD is active for that `exchange`/`symbol`).
    *   `NEW_TICKER_DATA(exchange, symbol, ticker_data)`: Passes to rules needing ticker data.
*   The original fetcher classes (`TradeStreamer`, `OHLCVStreamer`, `TickerStreamer`) from `sentinel/alert_bot/fetcher/` will be heavily refactored or their core logic absorbed into `AlertDataManager` or helper classes it uses. They will NOT use `ccxt.pro` directly.

This approach leverages the robust, reference-counted resource management of `TaskManager` and the centralized data fetching of `Data`. It also ensures that `CandleFactory` instances are created for the exact timeframes needed by alerts, and they are correctly seeded with historical data.

The next step in planning would be to detail the modifications needed in `Data` and `TaskManager` for ticker support, and then to sketch out the `AlertDataManager` class structure.

Does this detailed interaction with `TaskManager` make sense and align with how you envisioned the `alert_bot` integrating? The fact that `TaskManager` already handles distinct factories per timeframe is a big plus.





You've articulated the dilemma perfectly, and your thinking aligns with a pragmatic approach to such a complex integration. The "multiple factories vs. a single, more complex factory" is a classic engineering trade-off.

**My thoughts on the `CandleFactory`'s future and the immediate plan:**

You're right, the current `trade_suite` setup where `TaskManager` creates a distinct `CandleFactory` for each specific `(exchange, symbol, timeframe)` is functional. Each factory gets seeded with its own timeframe's historical data and then builds upon that by processing live trades from the shared raw trade stream for that symbol.

**For the `alert_bot` integration, and keeping "no coding yet" in mind, here's what I think about the `CandleFactory` question:**

1.  **Immediate Integration Path (Leverage Existing `TaskManager` Behavior):**
    *   **Accept the Current Model:** For the initial integration of the `alert_bot`, we should assume `TaskManager` will continue to create and manage separate `CandleFactory` instances for each unique timeframe required by the alert rules (e.g., one factory for BTC/USD-1m, another for BTC/USD-5m, etc., if alerts need all of these).
    *   **`AlertDataManager`'s Role:** The `AlertDataManager` we're planning will be responsible for:
        *   Parsing `alerts_config.yaml` to identify all unique `(exchange, symbol, timeframe)` tuples needed for OHLCV-based alerts.
        *   Subscribing to `TaskManager` for each of these, using requirement dictionaries like `{'type': 'candles', 'exchange': ex, 'symbol': sym, 'timeframe': tf}`. `TaskManager` will then handle the instantiation and historical seeding of these individual `CandleFactory` instances.
        *   Listening to `SignalEmitter` for `Signals.UPDATED_CANDLES` (which will now come from these specific, timeframe-dedicated factories) and routing the candle data to the correct alert rule evaluators.
    *   **Benefit:** This approach requires minimal to no changes to the existing `CandleFactory` or `TaskManager` logic regarding candle generation for different timeframes. The main work is building `AlertDataManager` to correctly interface with these existing systems.

2.  **Longer-Term `CandleFactory` Vision (A Separate `trade_suite` Enhancement):**
    *   Your intuition that "We dont want multiple factories for all diff timeframes if a dictionary works just as well" is valid from an efficiency and elegance standpoint.
    *   A more advanced `CandleFactory` *could* be designed to:
        *   Be initialized with a single "base" timeframe (e.g., 1m).
        *   Fetch and maintain historical data for this base timeframe.
        *   Process live trades to update only the base timeframe candles.
        *   Internally manage a dictionary (or similar structure) of resampled DataFrames for various higher timeframes (e.g., 5m, 15m, 1h), generated from the base candles.
        *   Offer methods like `get_ohlcv(timeframe_str)` which would return the requested resampled data (either by resampling on-the-fly or from its internal cache).
        *   Emit updates for these derived timeframes as their constituent base candles are completed.
    *   **This is a significant refactor of `CandleFactory` itself.** It would make `CandleFactory` a more powerful and self-contained entity for a given symbol, but it adds internal complexity to it.
    *   **This refactor should be considered a separate evolution of the `trade_suite`'s data handling, distinct from the immediate task of integrating the `alert_bot`.**

**Why separate these concerns for now?**

*   **Reduced Scope & Risk for `alert_bot`:** Integrating the `alert_bot` is already a substantial task. Trying to simultaneously re-architect a core component like `CandleFactory` increases complexity and risk.
*   **Functionality First:** The current `TaskManager` approach *will work* for the `alert_bot`. The `alert_bot` can be made functional using the existing multi-factory model.
*   **Performance as a Driver:** The primary motivation to change `CandleFactory` would likely be performance (reducing redundant trade processing across multiple factories for the same symbol) or a desire for a cleaner internal architecture. These can be addressed if and when they become actual issues or a priority for `trade_suite` development.

**So, to directly answer: "what you think the candle factory should become or stay the same?"**

*   **For now (Alert Bot Integration):** Assume it **stays the same** in its core logic (one factory instance per timeframe, managed by `TaskManager`). We design `AlertDataManager` to work with this.
*   **For the future (Trade Suite Evolution):** It **should ideally become** a more sophisticated component that manages a base timeframe and can serve multiple resampled views efficiently, as discussed in the "Longer-Term Vision."

This phased thinking allows us to make concrete progress on the `alert_bot` by building upon the stable foundation of `trade_suite` as it exists today, while earmarking potential enhancements for `trade_suite` itself for a later stage.

**Continuing to Explore:**

You're right, the current `trade_suite` architecture is quite comprehensive. We have a good grasp of:

*   `__main__.py`: Entry point, initial setup of `Data`, `ConfigManager`, `SignalEmitter`.
*   `viewport.py`: Sets up `TaskManager`, `DashboardManager`, DPG context, and the main render loop.
*   `data_source.py` (`Data` class): Centralized CCXT interactions, historical fetching, streaming (will add `watch_ticker`), caching.
*   `task_manager.py` (`TaskManager`): Manages lifecycle of data streams and `CandleFactory` instances via a subscription and ref-counting model. Crucially, it creates distinct factories per timeframe.
*   `candle_factory.py` (`CandleFactory`): Processes trades for a *single, specific `(exchange, symbol, timeframe)`** it's configured for.
*   `trade_suite.gui.signals.SignalEmitter`: A pub/sub system for decoupled communication between components.

**Key areas for the `AlertDataManager` design within our plan:**

1.  **Initialization:** Takes `Data`, `TaskManager`, `SignalEmitter`.
2.  **Configuration Processing:** Reads `alerts_config.yaml` to identify all unique data requirements.
3.  **Subscription Management:** Calls `task_manager.subscribe()` for each identified OHLCV timeframe, raw trade stream (for CVD), and future ticker stream. It will also need to call `task_manager.unsubscribe()` when alerts are removed or the bot stops.
4.  **Signal Handling:**
    *   Listens for `Signals.UPDATED_CANDLES` (from specific `CandleFactory` instances).
    *   Listens for `Signals.NEW_TRADE` (from `Data.watch_trades`).
    *   (Future) Listens for `Signals.NEW_TICKER_DATA` (from `Data.watch_ticker`).
5.  **Data Routing & Logic:**
    *   Manages `CVDCalculator` instances, feeding them raw trades.
    *   (Future) Manages ticker price storage/processing.
    *   Provides the latest data (OHLCV DataFrames, CVD values, ticker prices) to the alert rule evaluation engine.
6.  **Standalone Operation:** How it would run without the `trade_suite` GUI (e.g., different signal handling for console output or other notifications).

This detailed understanding of `TaskManager` and `CandleFactory` confirms that the path of least resistance and greatest leverage is to use them as they are for the initial `alert_bot` integration, focusing our development effort on the `AlertDataManager` as the intelligent intermediary.

The plan to synthesize these messages into a seed document for the next chat is excellent. We're building a solid blueprint.



----------------------------------


## Project Blueprint: `alert_bot` Integration with `trade_suite`

**Version:** 1.1 (Updated October 27, 2023) - Reflects significant progress.
**Previous Version:** 1.0 (October 26, 2023)
**Authors:** User & Gemini AI

**1. Introduction & Goals**

The `alert_bot` is a critical feature designed to provide users with timely notifications based on configurable market conditions. This project aims to integrate the `alert_bot` into the existing `trade_suite` application, leveraging `trade_suite`'s robust data handling and task management infrastructure. The integration supports two primary modes of operation for the `alert_bot`:

1.  **Integrated GUI Feature:** Accessible and configurable within the `trade_suite` DearPyGui application.
2.  **Standalone Terminal Application:** Capable of running independently.

Core goals remain: centralized data management via `trade_suite.Data`, leveraging `trade_suite.TaskManager`, modular design, and maintainability.

**2. Current `trade_suite` Architecture (Leveraged Components)**

Analysis of `trade_suite` components (`__main__`, `Viewport`, `Data`, `TaskManager`, `CandleFactory`, `SignalEmitter`) as detailed in Version 1.0 remains relevant. Key changes and confirmations:

*   **`trade_suite.data.data_source.Data`:**
    *   Successfully enhanced with `async def watch_ticker(...)` for live ticker data.
    *   Successfully enhanced with `async def fetch_historical_trades(...)` for seeding CVD calculators.
*   **`trade_suite.gui.task_manager.TaskManager`:**
    *   Successfully updated to manage ticker stream resources (`type: 'ticker'`).

**3. `alert_bot` Architecture & Integration Progress**

The central `AlertDataManager` class (`sentinel/alert_bot/manager.py`) is the core of the integration.

*   **`AlertDataManager` Key Responsibilities & Current State:**
    1.  **Interface Role:** Acts as the primary interface between `alert_bot`'s rule engine and `trade_suite`'s data infrastructure.
    2.  **Configuration Processing:**
        *   Successfully loads and parses `alerts_config.yaml` using `sentinel.alert_bot.config.loader.load_alerts_from_yaml`. This function is part of the `loader.py` module which defines Pydantic models (`AlertConfig`, `SymbolConfig`, various `Rule` types) and uses a `load_config` function to perform the actual YAML loading and Pydantic validation. `SymbolConfig` now correctly includes an `exchange: str` field.
    3.  **Subscription Management:**
        *   Correctly identifies unique data requirements (candles, raw trades, tickers) from the parsed config.
        *   Successfully subscribes to `TaskManager` for these resources, using `self` (the `AlertDataManager` instance) as the subscriber ID.
    4.  **Signal Handling:**
        *   Registers `async def _on_updated_candles(...)`, `async def _on_new_trade(...)`, and `async def _on_new_ticker_data(...)` with `SignalEmitter` to receive live data updates.
    5.  **CVD Data Management:**
        *   Manages instances of `CVDCalculator` (from `sentinel/alert_bot/processors/cvd_calculator.py`).
        *   On startup (`start_monitoring`), successfully seeds each `CVDCalculator` with historical trade data fetched via `self.data_source.fetch_historical_trades()`.
        *   The `_on_new_trade` method correctly parses incoming raw trades (using `TradeData.from_ccxt_trade` from `sentinel/alert_bot/models/trade_data.py`) and updates the appropriate `CVDCalculator` instance.
    6.  **Ticker Data & Price Level Alerts:**
        *   The `_on_new_ticker_data` method receives live ticker updates.
        *   **Implemented Rule Evaluation for Price Level Alerts:**
            *   Identifies relevant `PriceLevelRule`s from the active configuration for the incoming symbol/exchange.
            *   Extracts the current price from the ticker data.
            *   Checks if the rule's conditions (price above/below target) are met.
            *   Utilizes `self.state_manager.can_trigger()` and `self.state_manager.mark_triggered()` to enforce cooldowns.
            *   Logs a detailed message when a price level alert is triggered (actual notification dispatch is pending).
    7.  **State Management Integration:**
        *   Successfully uses `StateManager` (from `sentinel/alert_bot/state/manager.py`) for managing alert cooldowns in the implemented Price Level alert logic.
    8.  **Resource Cleanup:**
        *   `stop_monitoring()` handles unsubscribing from `TaskManager` and clearing internal trackers, including `cvd_calculators`.

*   **Refactored/Removed `alert_bot` Components:**
    *   `TradeData` class moved to `sentinel/alert_bot/models/trade_data.py`.
    *   `CVDCalculator` class moved to `sentinel/alert_bot/processors/cvd_calculator.py`.
    *   The entire `sentinel/alert_bot/fetcher/` directory has been cleaned up. Old fetcher modules (`trade_streamer.py`, `ohlcv.py`, `ticker.py`, `async_ccxt_fetcher.py`, `ccxt_fetcher.py`) that used `ccxt.pro` directly have been deleted, as all exchange interactions are now centralized in `trade_suite.Data`.

**4. Next Immediate Steps: Implementing Further Rule Evaluation**

With the structural integration for data handling largely complete and Price Level alerts functioning, the next focus is on implementing evaluation for other alert types:

1.  **Phase 2: Percentage Change Alerts (within `_on_updated_candles`)**
    *   **Task:** Enhance `async def _on_updated_candles(...)` in `AlertDataManager`.
    *   **Logic:**
        *   Identify relevant `PercentageChangeRule`s from `self.active_alerts_config` for the incoming `exchange`, `symbol`, and `timeframe`.
        *   Using the provided `candles_df` (a pandas DataFrame):
            *   Calculate the price change over the lookback period specified by `rule.timeframe` (in minutes). This will involve selecting the appropriate number of recent candles from the DataFrame. For example, if `rule.timeframe` is 60 minutes and the `candles_df` is for 1-minute candles, a 60-period lookback is needed. If `candles_df` is for 5-minute candles, a 12-period lookback is needed.
            *   Determine the start price (e.g., open or close of the candle `N` periods ago) and the current price (e.g., close of the latest candle).
            *   Calculate the percentage change: `((current_price - start_price) / start_price) * 100`.
        *   Check if `abs(percentage_change)` is greater than or equal to `rule.percentage`.
        *   If the condition is met:
            *   Generate a unique `rule_id` (e.g., `f"percentage_change_{symbol}_{timeframe}_{rule.percentage}%_{rule.timeframe}min"`).
            *   Check `self.state_manager.can_trigger(symbol, rule_id, rule.cooldown)`.
            *   If `True`, call `self.state_manager.mark_triggered(symbol, rule_id)` and log the alert.

2.  **Phase 3: CVD Alerts (Enhance `_on_new_trade`)**
    *   **Task:** Further enhance `async def _on_new_trade(...)` in `AlertDataManager`. (It currently updates the CVD calculator).
    *   **Logic (after `cvd_calc.add_trade(parsed_trade)`):**
        *   Retrieve relevant metrics from the `cvd_calc` instance:
            *   Current CVD value: `cvd_calc.get_cvd()`.
            *   CVD change over N minutes: `cvd_calc.get_cvd_change(minutes=rule.timeframe)`. (The `timeframe` in `CVDRule` config will map to `minutes` here).
            *   Buy/Sell ratio over N minutes: `cvd_calc.get_buy_sell_ratio(minutes=rule.timeframe)`.
        *   Identify active `CVDRule`s for the `exchange` and `symbol`.
        *   For each `CVDRule`:
            *   Based on `rule.type` ('change', 'ratio', 'level'):
                *   **'change':** Check `abs(cvd_change)` against `rule.cvd_threshold` or percentage change against `rule.cvd_percentage_threshold`.
                *   **'ratio':** Check `buy_sell_ratio['buy_ratio']` against `rule.buy_ratio_threshold` or `buy_sell_ratio['sell_ratio']` against `rule.sell_ratio_threshold`.
                *   **'level':** Check `current_cvd_value` against `rule.cvd_level` based on `rule.level_condition` ('above'/'below').
            *   If a condition is met:
                *   Generate a unique `rule_id` (e.g., `f"cvd_{symbol}_{rule.type}_{rule.timeframe}min_thresh_{rule.cvd_threshold_or_level}"`).
                *   Use `StateManager` for cooldowns and log the alert.
        *   (Divergence detection is a future feature and will remain placeholder for now).

3.  **Phase 4: Notification System Integration**
    *   **Task:** Design and integrate a flexible notification system.
    *   This will involve:
        *   Defining a `Notifier` base class/interface.
        *   Implementing concrete notifiers (e.g., `ConsoleNotifier`, `EmailNotifier`, `TelegramNotifier`).
        *   Allowing users to configure which notifiers are active in `alerts_config.yaml`.
        *   When an alert is confirmed (after cooldown check), `AlertDataManager` will dispatch it to all active notifiers.

**5. Key Architectural Insights & Reminders for Next Session**

*   `AlertDataManager` is central, using `trade_suite` data components and its own modules for rules, state, and notifications.
*   All data subscriptions are managed via `TaskManager`.
*   Rule evaluation will occur within the `_on_...` data handler methods in `AlertDataManager`.
*   `StateManager` is crucial for cooldowns.
*   The Pydantic models in `sentinel.alert_bot.config.loader` are the source of truth for alert rule parameters.

This updated blueprint should provide a clear path forward for implementing the remaining alert logic.
