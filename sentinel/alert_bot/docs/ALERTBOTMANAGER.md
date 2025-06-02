
**[IMPLEMENTATION COMPLETE]**
*The `AlertDataManager` as outlined in this document, including all five phases of its development (Core Skeleton, Data Subscriptions, Processor Integration, Rule Evaluation, and Notifier Integration), has been implemented in `sentinel/alert_bot/manager.py`. The following sections detail the planned and now realized architecture and functionalities.*

Okay, let's pick up where we left off with planning the `AlertDataManager`. The `alert_bot_ts_merge.md` document provides an excellent foundation and outlines the progress so far. We'll focus on elaborating the "Next Immediate Steps" to ensure we're designing a robust, full-time monitoring solution.

Based on the blueprint, the next phases were initially planned as:
1.  **Phase 2: Percentage Change Alerts** (within `_on_updated_candles`)
2.  **Phase 3: CVD Alerts** (Enhance `_on_new_trade`)
3.  **Phase 4: Notification System Integration**

*(The actual implementation followed a more granular 5-phase approach detailed at the end of this document, covering the above and more.)*

Let's delve into each, keeping in mind the requirements for continuous operation.

**Percentage Change Alerts (Implemented in `_on_updated_candles`)**

The blueprint task was to: "Enhance `async def _on_updated_candles(...)` in `AlertDataManager`."
This has been achieved as follows:

*   **Input:** The method receives `exchange`, `symbol`, `timeframe` (of the candle data itself, e.g., "5m"), and `candles_df` (a Pandas DataFrame).
*   **Rule Identification:**
    *   It uses `self._get_symbol_config(exchange, symbol)` to fetch the relevant symbol configuration.
    *   It iterates through `rules` in the symbol configuration, filtering for `type == "percentage_change"` and `enabled == True`.
    *   It verifies that the `rule.candle_timeframe` matches the `timeframe` of the incoming `candles_df` before processing.
*   **Core Logic for each `PercentageChangeRule`:**
    1.  **Parameters from Rule:**
        *   `rule.lookback_duration_str`: The total lookback period (e.g., "60m", "4h", "1d").
        *   `rule.percentage`: The threshold percentage change.
        *   `rule.price_point_to_use`: Which candle price point to use (e.g., 'open', 'high', 'low', 'close'), defaulting to 'close'. Validated against `candles_df` columns.
        *   `rule.cooldown`: Cooldown period in seconds.
        *   `symbol_alert_config.price_precision`: For formatting output.
    2.  **Lookback Calculation (using `_convert_duration_to_minutes` helper):**
        *   `lookback_total_minutes = self._convert_duration_to_minutes(rule.lookback_duration_str)`
        *   `candle_interval_minutes = self._convert_duration_to_minutes(timeframe)`
        *   A warning is logged if `lookback_total_minutes` is not a multiple of `candle_interval_minutes`.
        *   `num_candles_for_lookback = lookback_total_minutes // candle_interval_minutes`.
    3.  **Data Availability Check:**
        *   Ensures `len(candles_df) >= num_candles_for_lookback + 1`.
    4.  **Price Extraction:**
        *   `current_price = candles_df[rule.price_point_to_use].iloc[-1]`
        *   `start_price = candles_df[rule.price_point_to_use].iloc[-(num_candles_for_lookback + 1)]`
        *   Handles `pd.isna(current_price)` or `pd.isna(start_price)`.
    5.  **Percentage Change Calculation:**
        *   `calculated_percentage = ((current_price - start_price) / start_price) * 100`.
        *   Handles `start_price == 0` to prevent `ZeroDivisionError`.
    6.  **Condition Check & Triggering:**
        *   If `abs(calculated_percentage) >= rule.percentage`:
            *   Generates a unique `rule_id` (e.g., `f"percentage_change_{symbol}_{timeframe}_{price_point_to_use}_{lookback_duration_str}_{rule.percentage}%"`).
            *   If `self.state_manager.can_trigger(symbol, rule_id, rule.cooldown)`:
                *   `self.state_manager.mark_triggered(symbol, rule_id)`
                *   Formats a detailed title, message, and context dictionary.
                *   Calls `await self._dispatch_alert(...)`.
*   **Error Handling:** Each rule's evaluation is wrapped in a `try-except` block.

**CVD Alerts (Implemented in `_on_new_trade`)**

The blueprint task was to: "Further enhance `async def _on_new_trade(...)` in `AlertDataManager`."
This has been implemented as follows:

*   **Input:** The method receives `exchange`, `symbol`, and `trade_data` (dictionary).
*   **CVDCalculator Update:**
    *   Retrieves the `CVDCalculator` for the `exchange` and `symbol` from `self.cvd_calculators` (keyed as `f"{exchange}_{symbol}"`).
    *   If a calculator exists, `calculator.add_trade_from_dict(trade_data)` is called. Errors during this update are logged, and rule evaluation for this trade may be skipped.
    *   If no calculator exists for a symbol with configured CVD rules, a warning is logged.
*   **Rule Identification:**
    *   Uses `self._get_symbol_config(exchange, symbol)`.
    *   Iterates through rules, filtering for types starting with "cvd" (e.g., "cvd_change", "cvd_ratio", "cvd_level") and `enabled == True`.
*   **Core Logic for each `CVDRule` (after `CVDCalculator` is updated):**
    1.  **Parameters from Rule & Lookback:**
        *   `rule.cooldown`.
        *   `rule.timeframe_duration_str`: Lookback for the CVD calculation (e.g., "15m"). Converted to `lookback_minutes` using `_convert_duration_to_minutes`.
        *   Relevant thresholds (e.g., `cvd_threshold`, `cvd_percentage_threshold`, `buy_ratio_threshold`, `sell_ratio_threshold`, `cvd_level`, `level_condition`).
        *   `symbol_alert_config.price_precision` and `symbol_alert_config.volume_precision` for formatting.
    2.  **CVD Value Retrieval (from `CVDCalculator` instance):**
        *   **For `cvd_change` type:** Calls `calculator.get_cvd_change_value(minutes=lookback_minutes)` and/or `calculator.get_cvd_change_percentage(minutes=lookback_minutes)`.
        *   **For `cvd_ratio` type:** Calls `calculator.get_buy_sell_ratio(minutes=lookback_minutes)`.
        *   **For `cvd_level` type:** Calls `calculator.get_cvd()`.
    3.  **Condition Check & Triggering:**
        *   Compares the fetched CVD values against the rule's specific thresholds and conditions.
        *   If a condition is met:
            *   Generates a unique `rule_id` incorporating rule type, symbol, timeframe, and threshold details.
            *   Uses `self.state_manager.can_trigger` and `self.state_manager.mark_triggered`.
            *   Formats a tailored title, message, and context dictionary for the specific CVD alert type.
            *   Calls `await self._dispatch_alert(...)`.
*   **Error Handling:** Each rule's evaluation is wrapped in a `try-except` block.
*   **Note on `CVDCalculator`:** The implementation assumes `CVDCalculator` has methods like `add_trade_from_dict`, `get_cvd_change_value(minutes)`, `get_cvd_change_percentage(minutes)`, `get_buy_sell_ratio(minutes)`, and `get_cvd()`. These methods are expected to handle the actual CVD computation based on stored trade data and the requested lookback period.

**Price Level Alerts (Implemented in `_on_new_ticker_data`)**

This alert type was also implemented as part of the comprehensive rule evaluation system:

*   **Input:** Receives `exchange`, `symbol`, and `ticker_data` (dictionary).
*   **Rule Identification:** Uses `_get_symbol_config` and filters for `type == "price_level"` and `enabled == True`.
*   **Core Logic:**
    1.  **Price Determination:** Extracts `current_price_to_use` from `ticker_data['last']` or the midpoint of `ticker_data['bid']` and `ticker_data['ask']`.
    2.  **Parameters from Rule:** `target_price`, `condition` ("above" or "below"), `cooldown`, `price_precision`.
    3.  **Condition Check:** Compares `current_price_to_use` with `target_price` based on the `condition`.
    4.  **Triggering:** If met, generates `rule_id`, uses `StateManager`, formats alert details, and calls `_dispatch_alert`.
*   **Error Handling:** `try-except` block for each rule.

**Notification System Integration (Implemented via `_initialize_notifiers` and `_dispatch_alert`)**

The blueprint task was to: "Design and integrate a flexible notification system."
This has been achieved:

*   **Notifier Abstraction:** Relies on `notifier.base.AbstractNotifier` and concrete implementations like `notifier.async_console_notifier.AsyncConsoleNotifier` and `notifier.async_email_notifier.AsyncEmailNotifier`.
*   **Configuration in `alerts_config.yaml`:** Expects a `notification_settings` block in the global configuration, with a list of `notifiers`, each having an `id`, `type`, `enabled` status, and a `config` dictionary for notifier-specific settings (e.g., email recipients, SMTP details).
*   **`AlertDataManager` Integration:**
    1.  **Initialization (`_initialize_notifiers` method):**
        *   Called during `AlertDataManager.start_monitoring()`.
        *   Loads `notification_settings` from `self.global_config`.
        *   For each enabled notifier configuration:
            *   Instantiates the corresponding `AbstractNotifier` subclass (e.g., `AsyncConsoleNotifier`, `AsyncEmailNotifier`).
            *   Calls `await notifier.start()` for any async setup.
            *   Stores active notifiers in `self.active_notifiers: List[AbstractNotifier]`.
    2.  **Dispatching Notifications (`_dispatch_alert` method):**
        *   When an alert is confirmed (after `StateManager` check and rule logic determines a trigger):
            *   A clear `title`, `message`, and `alert_context` dictionary are constructed by the rule evaluation logic.
            *   `_dispatch_alert` iterates `self.active_notifiers`.
            *   For each notifier, it creates an `asyncio.task` for `notifier.send_notification(message, title, alert_context)` to send notifications concurrently.
            *   Uses `asyncio.gather` to await all notification tasks and logs any errors from individual notifiers.
    3.  **Shutdown (`stop_monitoring` method):**
        *   Iterates `self.active_notifiers` and calls `await notifier.stop()` for each, within a `try-except` block.
        *   Clears the `self.active_notifiers` list.

**General Considerations for Full-Time Monitoring (Status & Notes):**

1.  **Robust Error Handling:** Implemented within each rule evaluation loop in the signal handlers and for notifier dispatch, preventing single failures from halting others.
2.  **Dynamic Configuration Reloading:** *Not yet implemented.* `AlertDataManager` loads config at startup. For changes, a restart is currently required.
3.  **`StateManager` Persistence:** *Not yet implemented.* `StateManager` currently operates in memory; cooldown states are lost on restart.
4.  **Detailed & Structured Logging:** Python's `logging` module is used throughout `AlertDataManager` with varying levels (INFO, WARNING, ERROR, DEBUG) for operations, issues, and rule evaluation details.
5.  **Health Monitoring/Heartbeat:** *Not yet implemented.*
6.  **Resource Management:** `start_monitoring` and `stop_monitoring` handle subscriptions, listener registration/unregistration, processor initialization/clearing, and notifier start/stop for resource management.

This detailed plan, now largely implemented, provides a solid framework for the `AlertDataManager`, aiming for a solution that can run reliably full-time.

*(Original "What are your thoughts..." section removed as implementation is complete)*

**Core Philosophy for `AlertDataManager` (`manager.py`) (Achieved):**

*   **Orchestrator, Not Monolith:** `AlertDataManager` acts as the central coordinator, initializing components, subscribing to data via `TaskManager`, receiving signals via `SignalEmitter`, and directing flow to rule evaluation and notification. It delegates complex calculations to processors like `CVDCalculator` and notification sending to `Notifier` modules.
*   **Configuration-Driven:** Behavior is almost entirely defined by `alerts_config.yaml`, parsed by `config.loader` into Pydantic models.
*   **Leverage `trade_suite` Infrastructure:** Acts as a client to `trade_suite`'s `Data`, `TaskManager`, and `SignalEmitter`.
*   **Modular Internals:** Uses helper methods and relies on separate modules for configuration (`config/`), stateful data processing (`processors/`), state management (`state/`), and notifications (`notifier/`). Rule logic is primarily within the signal handlers in `manager.py` but is well-structured.

**Structure of `sentinel/alert_bot/manager.py` (Implemented Highlights):**

```python
# sentinel/alert_bot/manager.py
import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from trade_suite.gui.signals import Signals

from .config.loader import load_alerts_from_yaml, GlobalAlertConfig
from .processors.cvd_calculator import CVDCalculator
from .state.manager import StateManager
from .notifier.base import AbstractNotifier
from .notifier.async_console_notifier import AsyncConsoleNotifier
from .notifier.async_email_notifier import AsyncEmailNotifier
# ... (other potential notifier imports) ...

logger = logging.getLogger(__name__)

class AlertDataManager:
    def __init__(self, data_source: Any, task_manager: Any, signal_emitter: Any, config_file_path: str):
        # Stores data_source, task_manager, signal_emitter, config_file_path
        # Initializes self.global_config, self.active_alerts_config (parsed rules)
        # Initializes self.cvd_calculators: Dict[str, CVDCalculator]
        # Initializes self.state_manager = StateManager()
        # Initializes self.active_notifiers: List[AbstractNotifier]
        # Initializes self._is_running, self._data_processing_tasks, self._subscribed_requirements
        pass

    async def start_monitoring(self):
        # Sets _is_running = True
        # Calls self._load_and_parse_config()
        # Calls await self._initialize_notifiers()
        # Calls self._setup_subscriptions_and_listeners() if active_alerts_config exists
        # Calls await self._initialize_processors_and_fetch_history() if active_alerts_config exists
        # Logs startup status.
        pass

    async def stop_monitoring(self):
        # Sets _is_running = False
        # Calls self._teardown_subscriptions()
        # Stops and clears self.active_notifiers
        # Cancels self._data_processing_tasks
        # Clears self.cvd_calculators
        # Logs shutdown status.
        pass

    def _load_and_parse_config(self):
        # Loads YAML from self.config_file_path using loader.load_alerts_from_yaml.
        # Populates self.global_config and self.active_alerts_config.
        # Handles FileNotFoundError and other parsing errors.
        pass

    @staticmethod
    def _format_timeframe(time_value: Any) -> Optional[str]:
        # Converts timeframe representations (int minutes, string like "1h") to CCXT string format.
        pass

    @staticmethod
    def _convert_duration_to_minutes(duration_str: str) -> Optional[int]:
        # Converts duration strings (e.g., "30m", "1h", "2d", "1w") to total minutes.
        pass

    def _get_symbol_config(self, exchange_name: str, symbol_name: str) -> Optional[Any]:
        # Helper to retrieve the specific symbol alert configuration object from self.active_alerts_config.
        # Prioritizes new structure (GlobalAlertConfig.alerts.symbols), with basic fallback for flatter dicts.
        pass

    async def _initialize_notifiers(self):
        # Clears and populates self.active_notifiers based on self.global_config.notification_settings.
        # Instantiates AsyncConsoleNotifier, AsyncEmailNotifier, etc.
        # Calls await notifier.start() for each.
        pass

    async def _initialize_processors_and_fetch_history(self):
        # Iterates active_alerts_config.symbols to find symbols requiring CVD.
        # Initializes self.cvd_calculators[f"{exchange}_{symbol_name}"] = CVDCalculator(...).
        # Fetches historical trades (limit 900, reversed for chronological order) using self.data_source.
        # Seeds CVDCalculator instances with historical trades via calculator.add_trade_from_dict().
        pass

    def _get_data_requirements(self) -> Tuple[Set[Tuple[str, str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]]]:
        # Parses self.active_alerts_config to determine unique data subscriptions needed (candles, trades, tickers).
        # Returns sets of (exchange, symbol, timeframe) for candles, (exchange, symbol) for trades/tickers.
        pass

    def _setup_subscriptions_and_listeners(self):
        # Calls _get_data_requirements().
        # Subscribes to self.task_manager for each required data stream.
        # Registers self._on_updated_candles, self._on_new_trade, self._on_new_ticker_data with self.signal_emitter.
        # Tracks subscriptions in self._subscribed_requirements.
        pass

    def _teardown_subscriptions(self):
        # Unregisters signal handlers from self.signal_emitter.
        # Unsubscribes from self.task_manager for all tracked requirements.
        # Clears self._subscribed_requirements.
        pass

    async def _on_updated_candles(self, exchange: str, symbol: str, timeframe: str, candles_df: pd.DataFrame):
        # Handles PercentageChangeRule evaluation:
        # - Validates rule timeframe against incoming candle timeframe.
        # - Calculates lookback periods and extracts start/current prices from candles_df.
        # - Calculates percentage change, checks against threshold.
        # - Uses StateManager for cooldowns, calls _dispatch_alert if triggered.
        pass

    async def _on_new_trade(self, exchange: str, symbol: str, trade_data: dict):
        # Updates the relevant CVDCalculator with the new trade.
        # Handles CVDRule evaluation (cvd_change, cvd_ratio, cvd_level):
        # - Fetches CVD metrics from the calculator (e.g., get_cvd_change_value, get_buy_sell_ratio, get_cvd).
        # - Checks metrics against rule thresholds and conditions.
        # - Uses StateManager for cooldowns, calls _dispatch_alert if triggered.
        pass

    async def _on_new_ticker_data(self, exchange: str, symbol: str, ticker_data: dict):
        # Handles PriceLevelRule evaluation:
        # - Determines current price from ticker_data (last or mid-price).
        # - Compares against rule's target_price and condition ("above"/"below").
        # - Uses StateManager for cooldowns, calls _dispatch_alert if triggered.
        pass

    async def _dispatch_alert(self, title: str, message: str, context: Dict[str, Any]):
        # Logs the alert details.
        # Iterates self.active_notifiers, creating asyncio.tasks for notifier.send_notification(...).
        # Uses asyncio.gather to send notifications concurrently and handle errors.
        pass
```

*(Original Mermaid diagram and detailed explanations for structure are still relevant but now describe an implemented system rather than a proposed one.)*

---

**Phased Implementation Plan (Executed & Completed):**

*This section outlines the phased approach taken to build the `AlertDataManager`.*

────────────────────────────
**Phase 1: Core Skeleton & Configuration (Complete)**
────────────────────────────
*   **Achieved:**
    *   Created the lean skeleton of `AlertDataManager` in `manager.py`.
    *   Established `__init__` to accept `data_source`, `task_manager`, `signal_emitter`, and `config_file_path`.
    *   Implemented `_load_and_parse_config` to load `alerts_config.yaml` (handling both planned Pydantic structure via `GlobalAlertConfig` and current simpler structure) and populate `self.global_config` and `self.active_alerts_config`.
    *   Initialized `StateManager` instance (`self.state_manager`).
    *   Set up basic logging and stub methods for `start_monitoring` and `stop_monitoring`.
    *   Added helper `_format_timeframe`.

────────────────────────────
**Phase 2: Data Subscriptions & Signal Registration (Complete)**
────────────────────────────
*   **Achieved:**
    *   Implemented `_get_data_requirements` to parse `active_alerts_config` and identify unique candle, trade, and ticker streams needed.
    *   Implemented `_setup_subscriptions_and_listeners` to:
        *   Subscribe to `TaskManager` for all identified data requirements.
        *   Register async signal handlers (`_on_updated_candles`, `_on_new_trade`, `_on_new_ticker_data`) with `SignalEmitter`.
        *   Added `_subscribed_requirements` to track subscriptions.
    *   Implemented `_teardown_subscriptions` to unsubscribe from `TaskManager` and unregister handlers, called from `stop_monitoring`.
    *   Signal handlers created as stubs with logging.
    *   Added helper `_convert_duration_to_minutes` and `_get_symbol_config`.

────────────────────────────
**Phase 3: Processor Integration & Historical Seeding (Complete)**
────────────────────────────
*   **Achieved:**
    *   Implemented `_initialize_processors_and_fetch_history`:
        *   Identifies symbols requiring CVD analysis from `active_alerts_config`.
        *   Instantiates `CVDCalculator` for these symbols, stored in `self.cvd_calculators`.
        *   Fetched historical trades (limit 900, reversed for chronological order) via `self.data_source.fetch_historical_trades`.
        *   Seeded `CVDCalculator` instances using `calculator.add_trade_from_dict(trade)`.
    *   Updated `_on_new_trade` to call `calculator.add_trade_from_dict(trade_data)` for the relevant `CVDCalculator` with live trades.
    *   Ensured `self.cvd_calculators` is cleared in `stop_monitoring`.

────────────────────────────
**Phase 4: Rule Evaluation & Alert Dispatch (Complete)**
────────────────────────────
*   **Achieved:**
    *   Implemented Price Level alert logic in `_on_new_ticker_data`:
        *   Retrieves symbol config, determines current price from ticker.
        *   Checks rule conditions (target price, above/below).
        *   Uses `StateManager` for cooldowns.
        *   Calls `_dispatch_alert` with formatted alert details.
    *   Implemented Percentage Change alert logic in `_on_updated_candles`:
        *   Retrieves symbol config, validates rule timeframe against candle timeframe.
        *   Calculates lookback periods, extracts start/current prices from `candles_df` using `price_point_to_use`.
        *   Calculates percentage, checks against threshold.
        *   Uses `StateManager`, calls `_dispatch_alert`.
    *   Implemented CVD alert logic in `_on_new_trade` (after CVDCalculator update):
        *   Retrieves symbol config.
        *   For "cvd_change", "cvd_ratio", "cvd_level" rules, calls respective methods on `CVDCalculator` (e.g., `get_cvd_change_value`, `get_buy_sell_ratio`, `get_cvd`) with appropriate lookback minutes.
        *   Checks conditions against thresholds.
        *   Uses `StateManager`, calls `_dispatch_alert`.
    *   Implemented `async def _dispatch_alert(self, title: str, message: str, context: Dict[str, Any])` (initially as a logger, later enhanced in Phase 5).
    *   All rule evaluations are wrapped in `try-except` blocks for robustness.

────────────────────────────
**Phase 5: Notifier Integration & Complete Dispatch (Complete)**
────────────────────────────
*   **Achieved:**
    *   Implemented `_initialize_notifiers`:
        *   Loads `notification_settings` from `self.global_config`.
        *   Instantiates `AsyncConsoleNotifier`, `AsyncEmailNotifier` (and placeholders for others) based on config type.
        *   Calls `await notifier.start()`.
        *   Stores instances in `self.active_notifiers`.
    *   Enhanced `_dispatch_alert`:
        *   Iterates `self.active_notifiers`.
        *   Creates `asyncio.Task` for each `notifier.send_notification(...)` for concurrent sending.
        *   Uses `asyncio.gather` to await tasks and handle/log individual notifier errors.
    *   Integrated notifier start into `start_monitoring`.
    *   Integrated notifier stop (calling `await notifier.stop()`) into `stop_monitoring`.

*(Original User query asking about the phased approach is still relevant as it kicked off this structure)*
How does that sound? Ready to start chunking this out phase by phase, or do you have any tweaks you’d like to incorporate?

