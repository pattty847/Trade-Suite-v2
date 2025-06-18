import asyncio
import logging
from typing import Dict, Any, Set, Tuple, List, Optional
import pandas as pd
from datetime import datetime, timedelta

# Trade Suite components
from trade_suite.core.data.data_source import Data
from trade_suite.core.task_manager import TaskManager
from trade_suite.core.signals import SignalEmitter, Signals
from trade_suite.core.facade import CoreServicesFacade

# Alert Bot components
from sentinel.alert_bot.config.loader import load_alerts_from_yaml, GlobalAlertConfig
from sentinel.alert_bot.state.manager import StateManager
from sentinel.alert_bot.models.trade_data import TradeData
from sentinel.alert_bot.processors.cvd_calculator import CVDCalculator
from sentinel.alert_bot.notifier.base import AsyncBaseNotifier

# Placeholder for rule engine and notifiers, will be used later
# from sentinel.alert_bot.rules.engine import RuleEngine
# from sentinel.alert_bot.notifier.base import Notifier # Or specific notifier instances

# Import concrete notifier classes for Phase 5
from sentinel.alert_bot.notifier.async_console_notifier import AsyncConsoleNotifier
from sentinel.alert_bot.notifier.async_email_notifier import AsyncEmailNotifier
# Add other notifiers here as they are implemented, e.g.:
# from sentinel.alert_bot.notifier.async_telegram_notifier import AsyncTelegramNotifier

logger = logging.getLogger(__name__)

class AlertDataManager:
    def __init__(self, core_services: CoreServicesFacade, config_file_path: str):
        """
        Initializes the AlertDataManager.

        Args:
            core_services: The main CoreServicesFacade providing access to backend services.
            config_file_path: Path to the alerts configuration YAML file.
        """
        self.core = core_services
        self.data_source = core_services.data
        self.task_manager = core_services.task_manager
        self.signal_emitter = core_services.emitter
        self.config_file_path = config_file_path

        self.global_config: Optional[GlobalAlertConfig] = None
        # active_alerts_config will hold the part of global_config relevant to rules,
        # e.g., self.global_config.alerts if 'alerts' is the top-level key for SymbolConfigs.
        self.active_alerts_config: Any = None 
        
        self.cvd_calculators: Dict[str, CVDCalculator] = {} 
        self.state_manager = StateManager()
        self.active_notifiers: List[AsyncBaseNotifier] = []

        self._is_running = False
        self._data_processing_tasks: List[asyncio.Task] = []
        self._subscribed_requirements: Dict[str, Set[Tuple[str, ...]]] = {
            "candles": set(),
            "trades": set(),
            "tickers": set()
        }

    def _load_and_parse_config(self):
        """Loads and parses the alert configuration file."""
        logger.info(f"Loading alert configuration from: {self.config_file_path}")
        try:
            self.global_config = load_alerts_from_yaml(self.config_file_path)
            
            if self.global_config and hasattr(self.global_config, 'alerts'): # As per ALERTBOTMANAGER.md desired structure
                 self.active_alerts_config = self.global_config.alerts
            elif self.global_config and isinstance(self.global_config, dict): # Handles current simpler config structure
                self.active_alerts_config = self.global_config
            else:
                self.active_alerts_config = None

            if self.active_alerts_config:
                num_symbols = 0
                # Check based on ALERTBOTMANAGER.md structure (GlobalAlertConfig -> .alerts -> .symbols)
                if hasattr(self.active_alerts_config, 'symbols') and isinstance(self.active_alerts_config.symbols, dict):
                    num_symbols = len(self.active_alerts_config.symbols)
                # Check based on current alerts_config.yaml structure (root is Dict[str, SymbolAlertConfig])
                elif isinstance(self.active_alerts_config, dict):
                    num_symbols = len(self.active_alerts_config)
                logger.info(f"Successfully loaded configuration for {num_symbols} symbols.")
            else:
                logger.warning("Alert configuration loaded, but no active alert rules found or structure not as expected.")

        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_file_path}")
            self.global_config = None
            self.active_alerts_config = None
        except Exception as e:
            logger.exception(f"Error loading or parsing alert configuration from {self.config_file_path}: {e}")
            self.global_config = None
            self.active_alerts_config = None

    @staticmethod
    def _format_timeframe(time_value: Any) -> Optional[str]:
        """Converts various timeframe representations to CCXT string format.
        Primarily expects CCXT standard timeframe strings or integer minutes.
        """
        if isinstance(time_value, str):
            # Assume if it's a string, it's intended to be a CCXT timeframe.
            # Basic validation for common units.
            time_value_lower = time_value.lower()
            if not any(unit in time_value_lower for unit in ['m', 'h', 'd', 'w']) or \
               not time_value_lower[:-1].isdigit() and len(time_value_lower) > 1: # e.g. "1m", "15m", "1h", "2d", "1w"
                try:
                    # If it's a string but just a number, treat as integer minutes
                    m = int(time_value)
                    return AlertDataManager._format_timeframe(m) # Recurse with int
                except ValueError:
                    logger.warning(f"Invalid string timeframe format: {time_value}. Expected CCXT format (e.g., '1m', '1h', '1d', '1w') or integer minutes.")
                    return None
            return time_value_lower
        
        if isinstance(time_value, int):
            if time_value < 1: # Should be at least 1 minute
                logger.warning(f"Timeframe too short: {time_value} minutes. Must be at least 1 minute.")
                return None
            
            minutes_in_hour = 60
            minutes_in_day = 24 * minutes_in_hour
            minutes_in_week = 7 * minutes_in_day

            if time_value >= minutes_in_week and time_value % minutes_in_week == 0:
                return f"{time_value // minutes_in_week}w"
            if time_value >= minutes_in_day and time_value % minutes_in_day == 0:
                return f"{time_value // minutes_in_day}d"
            if time_value >= minutes_in_hour and time_value % minutes_in_hour == 0:
                return f"{time_value // minutes_in_hour}h"
            # Default to minutes if not a whole hour, day, or week, or if less than an hour
            return f"{time_value}m"

        logger.warning(f"Unsupported timeframe format: {time_value} (type: {type(time_value)}). Expected CCXT string or integer minutes. Returning None.")
        return None

    @staticmethod
    def _convert_duration_to_minutes(duration_str: str) -> Optional[int]:
        """Converts duration strings (e.g., "30m", "1h", "2d") to minutes."""
        if not isinstance(duration_str, str) or not duration_str:
            logger.warning(f"Invalid duration string: {duration_str}. Expected format like '30m', '2h', '1d'.")
            return None
        
        duration_str = duration_str.lower()
        value = duration_str[:-1]
        unit = duration_str[-1]

        if not value.isdigit():
            logger.warning(f"Invalid duration value in string: '{value}' from '{duration_str}'. Expected a number.")
            return None
        
        value = int(value)

        if unit == 'm':
            return value
        elif unit == 'h':
            return value * 60
        elif unit == 'd':
            return value * 60 * 24
        elif unit == 'w':
            return value * 60 * 24 * 7
        else:
            logger.warning(f"Unsupported duration unit '{unit}' in '{duration_str}'. Supported units: m, h, d, w.")
            return None

    def _get_symbol_config(self, exchange_name: str, symbol_name: str) -> Optional[Any]:
        """Helper to retrieve the specific symbol alert configuration object."""
        if not self.active_alerts_config:
            return None

        # Scenario 1: Based on ALERTBOTMANAGER.md (GlobalAlertConfig -> .alerts -> .symbols)
        # self.active_alerts_config is an object with a .symbols dictionary
        # where values are SymbolAlertConfig objects having .exchange and .symbol attributes.
        if hasattr(self.active_alerts_config, 'symbols') and isinstance(self.active_alerts_config.symbols, dict):
            for config_key, symbol_config_obj in self.active_alerts_config.symbols.items():
                if hasattr(symbol_config_obj, 'exchange') and hasattr(symbol_config_obj, 'symbol'):
                    if symbol_config_obj.exchange == exchange_name and symbol_config_obj.symbol == symbol_name:
                        return symbol_config_obj
            logger.debug(f"No symbol config found for {exchange_name}-{symbol_name} in .symbols structure.")
            return None
        
        # Scenario 2: Based on current simple alerts_config.yaml (root is Dict[str, SymbolRules])
        # self.active_alerts_config is a Dict where key is e.g. "ETH/USD" and value is the rules struct.
        # This scenario is harder to map exchange if not explicitly in the structure or if a default is used.
        # For now, this primarily supports the structure from ALERTBOTMANAGER.md.
        # If your loader.py transforms the old config into the new structure, Scenario 1 will work.
        # Otherwise, this part needs to be more robust or make assumptions about the key format.
        # Example for simple key format like "EXCHANGE_SYMBOL" or if symbol keys are unique across exchanges
        # in a flatter structure (less likely for a robust system).
        elif isinstance(self.active_alerts_config, dict):
            # This is a simplified lookup. If exchange is part of the key or implicit, this would need adjustment.
            # For instance, if keys are "EXCHANGE_SYMBOL" or if symbol_name is globally unique.
            # The `ALERTBOTMANAGER.md` structure is preferred for clarity.
            key_to_try = f"{exchange_name}_{symbol_name}" # Example, if keys are formed this way
            if symbol_name in self.active_alerts_config: # If key is just symbol
                # This implies that the rules object itself needs to be associated with an exchange implicitly
                # or that the symbol_name is unique across all exchanges you monitor with one config file.
                # To make this work, the rules object fetched here would need an 'exchange' attribute or we assume it matches.
                config_obj = self.active_alerts_config.get(symbol_name)
                # We would need to verify if this config_obj is for the correct exchange.
                # This path is ambiguous without knowing more about how the simple config is meant to map to exchanges.
                # Let's assume for now this path is less used if the new structure is adopted.
                logger.debug(f"Found config for symbol {symbol_name} in flat dict structure. Exchange matching not explicitly verified here.")
                return config_obj
            elif key_to_try in self.active_alerts_config:
                 return self.active_alerts_config.get(key_to_try)

        logger.warning(f"Could not find symbol config for {exchange_name}-{symbol_name}. Structure of active_alerts_config might be unexpected.")
        return None

    def _get_data_requirements(self) -> Tuple[Set[Tuple[str, str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]]]:
        candle_reqs: Set[Tuple[str, str, str]] = set() # (exchange, symbol, timeframe)
        trade_reqs: Set[Tuple[str, str]] = set()      # (exchange, symbol)
        ticker_reqs: Set[Tuple[str, str]] = set()     # (exchange, symbol)

        if not self.active_alerts_config:
            return candle_reqs, trade_reqs, ticker_reqs

        # Determine iteration strategy based on config structure
        symbols_data_iterator = None
        if hasattr(self.active_alerts_config, 'symbols') and isinstance(self.active_alerts_config.symbols, dict):
            # New structure: self.active_alerts_config.symbols is Dict[str, SymbolAlertConfig]
            # where SymbolAlertConfig has .exchange, .symbol, .rules
            symbols_data_iterator = self.active_alerts_config.symbols.values()
        elif isinstance(self.active_alerts_config, dict):
            # Old structure: self.active_alerts_config is Dict[str, Any] (e.g. {"BTC/USD": {...rules...}})
            # We need to parse exchange/symbol from the key or assume a default exchange
            # This path is less defined by ALERTBOTMANAGER.md; focusing on the new structure.
            # If you need robust support for the old structure, `loader.py` should ideally transform it.
            logger.debug("Parsing data requirements assuming new config structure (GlobalAlertConfig.alerts.symbols)")
            symbols_data_iterator = self.active_alerts_config.symbols.values() if hasattr(self.active_alerts_config, 'symbols') else []

        if not symbols_data_iterator:
            logger.warning("Could not determine how to iterate over symbol configurations for data requirements.")
            return candle_reqs, trade_reqs, ticker_reqs

        for symbol_config in symbols_data_iterator:
            # These attributes are expected from the Pydantic models defined by loader.py
            # based on the target configuration structure.
            # Assuming Pydantic models ensure 'exchange' and 'symbol' are present.
            exchange = symbol_config.exchange
            symbol_name = symbol_config.symbol
            rules = getattr(symbol_config, 'rules', []) # rules can be optional or empty

            for rule in rules:
                if not getattr(rule, 'enabled', True): # Assume enabled if not specified
                    continue

                rule_type = getattr(rule, 'type', 'unknown')

                if rule_type == "price_level":
                    ticker_reqs.add((exchange, symbol_name))
                elif rule_type == "percentage_change":
                    raw_tf = getattr(rule, 'candle_timeframe', None)
                    if raw_tf:
                        formatted_tf = self._format_timeframe(raw_tf)
                        if formatted_tf:
                            candle_reqs.add((exchange, symbol_name, formatted_tf))
                        else:
                            logger.warning(f"Invalid timeframe '{raw_tf}' for {symbol_name} percentage_change. Skipping candle sub.")
                    else:
                        logger.warning(f"Percentage change rule for {symbol_name} missing 'candle_timeframe'. Skipping candle sub.")
                elif rule_type.startswith("cvd") or rule_type == "cvd_change" or rule_type == "cvd_ratio" or rule_type == "cvd_level": # Generalizing for CVD rules
                    trade_reqs.add((exchange, symbol_name))
                    # Some CVD rules might also depend on candles for context (e.g. plotting CVD on a chart)
                    raw_cvd_candle_tf = getattr(rule, 'candle_timeframe', None)
                    if raw_cvd_candle_tf:
                        formatted_cvd_tf = self._format_timeframe(raw_cvd_candle_tf)
                        if formatted_cvd_tf:
                            candle_reqs.add((exchange, symbol_name, formatted_cvd_tf))
                        else:
                            logger.warning(f"Invalid 'candle_timeframe': '{raw_cvd_candle_tf}' for CVD rule on {symbol_name}. Skipping this candle sub.")
                # Add other rule types and their data needs here
        return candle_reqs, trade_reqs, ticker_reqs

    def _setup_subscriptions_and_listeners(self):
        candle_reqs, trade_reqs, ticker_reqs = self._get_data_requirements()

        self._subscribed_requirements["candles"].clear()
        self._subscribed_requirements["trades"].clear()
        self._subscribed_requirements["tickers"].clear()

        # AlertDataManager itself acts as the 'widget' or 'subscriber' context for TaskManager
        subscriber_context = self 

        for ex, sym, tf in candle_reqs:
            req = {'type': 'candles', 'exchange': ex, 'symbol': sym, 'timeframe': tf}
            logger.info(f"Subscribing AlertDataManager to TaskManager for: {req}")
            self.task_manager.subscribe(widget=subscriber_context, requirements=req)
            self._subscribed_requirements["candles"].add((ex, sym, tf))
        
        for ex, sym in trade_reqs:
            req = {'type': 'trades', 'exchange': ex, 'symbol': sym}
            logger.info(f"Subscribing AlertDataManager to TaskManager for: {req}")
            self.task_manager.subscribe(widget=subscriber_context, requirements=req)
            self._subscribed_requirements["trades"].add((ex, sym))

        for ex, sym in ticker_reqs:
            req = {'type': 'ticker', 'exchange': ex, 'symbol': sym}
            logger.info(f"Subscribing AlertDataManager to TaskManager for: {req}")
            self.task_manager.subscribe(widget=subscriber_context, requirements=req)
            self._subscribed_requirements["tickers"].add((ex, sym))
        
        logger.info(f"Total subscriptions made by AlertDataManager: {len(candle_reqs)} candle, {len(trade_reqs)} trade, {len(ticker_reqs)} ticker streams.")

        # Register listeners with SignalEmitter
        # Ensure signal names match what trade_suite.SignalEmitter uses.
        # Using Signals enum/class members is preferred if available.
        self.signal_emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        self.signal_emitter.register(Signals.NEW_TRADE, self._on_new_trade)
        self.signal_emitter.register(Signals.NEW_TICKER_DATA, self._on_new_ticker_data)
        logger.info("AlertDataManager successfully registered its listeners with the SignalEmitter.")

    def _teardown_subscriptions(self):
        logger.info("AlertDataManager tearing down subscriptions from TaskManager and SignalEmitter...")
        
        # Unregister signal handlers first
        try:
            self.signal_emitter.unregister(Signals.UPDATED_CANDLES, self._on_updated_candles)
            self.signal_emitter.unregister(Signals.NEW_TRADE, self._on_new_trade)
            self.signal_emitter.unregister(Signals.NEW_TICKER_DATA, self._on_new_ticker_data)
            logger.info("Unregistered signal handlers from SignalEmitter.")
        except Exception as e: # Catch broad exceptions if unregister can fail (e.g., if not registered)
            logger.warning(f"Error unregistering signal handlers from AlertDataManager: {e}")

        # AlertDataManager itself was the 'widget' or 'subscriber' context
        subscriber_context = self
        try:
            self.task_manager.unsubscribe(widget=subscriber_context)
            logger.info(f"Unsubscribed AlertDataManager from TaskManager for all its requirements.")
        except Exception as e:
            logger.warning(f"Error unsubscribing AlertDataManager from TaskManager: {e}")
        
        self._subscribed_requirements["candles"].clear()
        self._subscribed_requirements["trades"].clear()
        self._subscribed_requirements["tickers"].clear()
        logger.info("AlertDataManager finished unsubscribing from TaskManager.")

    async def start_monitoring(self):
        """Starts the alert monitoring process."""
        if self._is_running:
            logger.warning("AlertDataManager is already running.")
            return

        logger.info("Starting AlertDataManager monitoring...")
        self._load_and_parse_config()

        if not self.active_alerts_config and not self.global_config: # If config loading failed entirely
            logger.error("Alert configuration could not be loaded. AlertDataManager cannot start.")
            return # Cannot proceed without any config

        # Initialize Notifiers (Phase 5) - needs global_config for notification_settings
        await self._initialize_notifiers()

        if not self.active_alerts_config:
            logger.warning("No active alert rules (active_alerts_config is empty/None). Monitoring will be idle for rules, but notifiers are up.")
            self._is_running = True # Mark as started, but essentially idle for rule processing
            return
        
        # Phase 2: Setup subscriptions and listeners
        self._setup_subscriptions_and_listeners()
        
        # Phase 3: Initialize processors and fetch history
        await self._initialize_processors_and_fetch_history()
            
        self._is_running = True
        logger.info("AlertDataManager started and subscriptions are active.")

    async def stop_monitoring(self):
        """Stops the alert monitoring process and cleans up resources."""
        if not self._is_running:
            logger.info("AlertDataManager is not running or already stopped.")
            return
        
        logger.info("Stopping AlertDataManager monitoring...")
        
        # Phase 2: Teardown subscriptions and listeners
        self._teardown_subscriptions()

        # Phase 5: Stop notifiers
        logger.debug(f"Stopping {len(self.active_notifiers)} active notifiers...")
        for notifier in self.active_notifiers:
            try:
                logger.debug(f"Stopping notifier {type(notifier).__name__}...")
                await notifier.stop()
            except Exception as e:
                logger.error(f"Error stopping notifier {type(notifier).__name__}: {e}", exc_info=True)
        self.active_notifiers.clear()
        logger.info("All active notifiers stopped and cleared.")

        # Future phases cleanup (notifiers, processors, tasks) will go here
        for task in self._data_processing_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._data_processing_tasks, return_exceptions=True)
        self._data_processing_tasks.clear()

        self.cvd_calculators.clear()
        # self.state_manager.save_state() # If persistence is added

        self._is_running = False # Set at the very end of cleanup
        logger.info("AlertDataManager stopped and cleaned up.")

    async def _on_updated_candles(self, exchange: str, symbol: str, timeframe: str, candles: pd.DataFrame):
        if not self._is_running: return
        # The DataFrame of candles is now received as `candles`
        candles_df = candles
        logger.debug(f"Received updated candles for {exchange} {symbol} {timeframe}. Shape: {candles_df.shape}")

        symbol_alert_config = self._get_symbol_config(exchange, symbol)
        if not symbol_alert_config or not hasattr(symbol_alert_config, 'rules') or not symbol_alert_config.rules:
            return

        # Get the interval of the incoming candles_df in minutes
        candle_interval_minutes = self._convert_duration_to_minutes(timeframe)
        if candle_interval_minutes is None:
            logger.warning(f"Could not determine candle interval in minutes for timeframe '{timeframe}' on {exchange} {symbol}. Skipping percentage change checks.")
            return

        for rule_config in symbol_alert_config.rules:
            if getattr(rule_config, 'type', None) == "percentage_change" and getattr(rule_config, 'enabled', True):
                try:
                    lookback_duration_str = getattr(rule_config, 'lookback_duration_str', None)
                    percentage_threshold = float(getattr(rule_config, 'percentage', 0.0))
                    cooldown = int(getattr(rule_config, 'cooldown', 300))
                    price_point_to_use = getattr(rule_config, 'price_point_to_use', 'close').lower()
                    price_precision = getattr(symbol_alert_config, 'price_precision', 2)
                    candle_timeframe_for_rule = getattr(rule_config, 'candle_timeframe', None) # Timeframe this rule is intended for

                    if not lookback_duration_str or percentage_threshold == 0.0:
                        logger.warning(f"Percentage change rule for {exchange} {symbol} is missing lookback_duration_str or percentage. Rule: {rule_config}")
                        continue
                    
                    # Ensure this rule is intended for the timeframe of the incoming candles
                    if candle_timeframe_for_rule and self._format_timeframe(candle_timeframe_for_rule) != timeframe:
                        # logger.debug(f"Skipping % change rule for {exchange} {symbol} {timeframe}. Rule intended for {candle_timeframe_for_rule}.")
                        continue

                    if price_point_to_use not in ['open', 'high', 'low', 'close']:
                        logger.warning(f"Invalid 'price_point_to_use': '{price_point_to_use}' for {exchange} {symbol}. Defaulting to 'close'.")
                        price_point_to_use = 'close'
                    
                    if price_point_to_use not in candles_df.columns:
                        # Attempt to correct for singular vs. plural (e.g., 'close' vs 'closes')
                        corrected_price_point = f"{price_point_to_use}s"
                        if corrected_price_point in candles_df.columns:
                            price_point_to_use = corrected_price_point
                        else:
                            logger.warning(f"Price point '{price_point_to_use}' not found in candles_df columns for {exchange} {symbol} {timeframe}. Columns: {candles_df.columns}")
                            continue

                    lookback_total_minutes = self._convert_duration_to_minutes(lookback_duration_str)
                    if lookback_total_minutes is None:
                        logger.warning(f"Invalid lookback_duration_str '{lookback_duration_str}' for {exchange} {symbol}. Rule: {rule_config}")
                        continue

                    if lookback_total_minutes % candle_interval_minutes != 0:
                        logger.warning(f"Lookback duration {lookback_total_minutes}m is not a multiple of candle interval {candle_interval_minutes}m for {exchange} {symbol} {timeframe}. This may lead to inaccurate calculations. Rule: {rule_config}")
                        # Optionally, skip or adjust. For now, proceed with caution.
                    
                    num_candles_for_lookback = lookback_total_minutes // candle_interval_minutes
                    if num_candles_for_lookback <= 0:
                        logger.warning(f"Calculated num_candles_for_lookback is {num_candles_for_lookback}, must be > 0. {exchange} {symbol}. Rule: {rule_config}")
                        continue

                    if len(candles_df) < num_candles_for_lookback + 1:
                        logger.debug(f"Not enough candle data ({len(candles_df)}) for lookback of {num_candles_for_lookback + 1} candles for {exchange} {symbol} {timeframe}. Rule: {rule_config}")
                        continue

                    current_price = candles_df[price_point_to_use].iloc[-1]
                    start_price = candles_df[price_point_to_use].iloc[-(num_candles_for_lookback + 1)]

                    if pd.isna(current_price) or pd.isna(start_price):
                        logger.warning(f"NaN price encountered for {exchange} {symbol} {timeframe} using {price_point_to_use}. Current: {current_price}, Start: {start_price}. Skipping rule.")
                        continue

                    if start_price == 0:
                        logger.warning(f"Start price is 0 for {exchange} {symbol} {timeframe} using {price_point_to_use}. Cannot calculate percentage change. Skipping rule.")
                        continue
                    
                    calculated_percentage = ((current_price - start_price) / start_price) * 100

                    if abs(calculated_percentage) >= percentage_threshold:
                        rule_id = f"percentage_change_{symbol}_{timeframe}_{price_point_to_use}_{lookback_duration_str}_{percentage_threshold}%"
                        trigger_symbol = getattr(rule_config, 'symbol', symbol)

                        if self.state_manager.can_trigger(trigger_symbol, rule_id, cooldown):
                            self.state_manager.mark_triggered(trigger_symbol, rule_id)

                            direction = "up" if calculated_percentage > 0 else "down"
                            alert_title = f"Price % Change: {exchange} {trigger_symbol} {abs(calculated_percentage):.{price_precision}f}% {direction}"
                            alert_message = (
                                f"{exchange} - {trigger_symbol} ({timeframe} {price_point_to_use}) changed by {calculated_percentage:.{price_precision}f}% "
                                f"over {lookback_duration_str} (threshold: {percentage_threshold}%). "
                                f"Start: {start_price:.{price_precision}f}, Current: {current_price:.{price_precision}f}."
                            )
                            alert_context = {
                                "exchange": exchange,
                                "symbol": trigger_symbol,
                                "rule_type": "percentage_change",
                                "timeframe": timeframe,
                                "price_point_used": price_point_to_use,
                                "lookback_duration": lookback_duration_str,
                                "lookback_candles": num_candles_for_lookback,
                                "percentage_threshold": percentage_threshold,
                                "calculated_percentage": calculated_percentage,
                                "start_price": start_price,
                                "current_price": current_price,
                                "rule_id": rule_id,
                                "cooldown_seconds": cooldown,
                                "price_precision": price_precision
                            }
                            await self._dispatch_alert(alert_title, alert_message, alert_context)
                except Exception as e:
                    logger.error(f"Error evaluating percentage_change rule for {exchange} {symbol} {timeframe}: {e} - Rule: {vars(rule_config) if hasattr(rule_config, '__dict__') else rule_config}", exc_info=True)

    async def _on_new_trade(self, exchange: str, trade_data: dict):
        if not self._is_running: return
        # trade_data is assumed to be a dictionary from SignalEmitter, potentially raw from CCXT
        # The 'symbol' is inside the trade_data dictionary.
        symbol = trade_data.get('symbol')
        if not symbol:
            logger.warning(f"Received trade data for exchange {exchange} without a symbol: {trade_data}")
            return
            
        logger.debug(f"Received new trade: {exchange} {symbol}, Price: {trade_data.get('price')}, Amount: {trade_data.get('amount')}")
        
        unique_key = f"{exchange}_{symbol}"
        
        # Parse the raw dictionary into a TradeData object first.
        trade_obj = TradeData.from_ccxt_trade(trade_data)
        if not trade_obj:
            logger.warning(f"Failed to parse live trade for {unique_key}: {trade_data}")
            return # Cannot proceed without a valid trade object

        calculator = self.cvd_calculators.get(unique_key)

        if calculator:
            try:
                # Add the parsed TradeData object to the calculator
                calculator.add_trade(trade_obj)
            except Exception as e:
                logger.error(f"Error adding live trade to CVDCalculator for {unique_key}: {e} - Data: {trade_data}", exc_info=True)
                return # If CVD update fails, probably best not to evaluate rules based on stale CVD data
        else:
            # No CVD calculator for this symbol, this is fine if no CVD rules are configured for it.
            # However, if CVD rules ARE configured, _initialize_processors_and_fetch_history should have created it.
            # So, if we have CVD rules but no calculator, that's an issue to investigate.
            pass # Continue, as there might be non-CVD rules for trades in the future

        # --- CVD Rule Evaluation --- 
        symbol_alert_config = self._get_symbol_config(exchange, symbol)
        if not symbol_alert_config or not hasattr(symbol_alert_config, 'rules') or not symbol_alert_config.rules:
            return
        
        if not calculator: # No CVD calculator, so cannot evaluate CVD rules
            # Check if any CVD rules exist to log a warning if calculator is missing when it should exist
            if any(getattr(r, 'type', '').startswith("cvd") for r in symbol_alert_config.rules if getattr(r, 'enabled', True)):
                logger.warning(f"CVD rules exist for {unique_key} but CVDCalculator is not initialized. Skipping CVD rule evaluation.")
            return

        price_precision = getattr(symbol_alert_config, 'price_precision', 2)
        volume_precision = getattr(symbol_alert_config, 'volume_precision', 3) # For CVD values

        for rule_config in symbol_alert_config.rules:
            rule_type = getattr(rule_config, 'type', None)
            if not rule_type or not rule_type.startswith("cvd") or not getattr(rule_config, 'enabled', True):
                continue
            
            try:
                cooldown = int(getattr(rule_config, 'cooldown', 300))
                timeframe_duration_str = getattr(rule_config, 'timeframe_duration_str', None) # e.g., "15m", "1h"
                lookback_minutes = None
                if timeframe_duration_str:
                    lookback_minutes = self._convert_duration_to_minutes(timeframe_duration_str)
                    if lookback_minutes is None:
                        logger.warning(f"Invalid 'timeframe_duration_str': '{timeframe_duration_str}' for CVD rule on {exchange} {symbol}. Skipping rule.")
                        continue

                alert_triggered_for_rule = False
                alert_details = {}

                if rule_type == "cvd_change":
                    cvd_threshold = getattr(rule_config, 'cvd_threshold', None)
                    cvd_percentage_threshold = getattr(rule_config, 'cvd_percentage_threshold', None)
                    
                    if cvd_threshold is not None:
                        # Corrected method call from get_cvd_change_value to get_cvd_change
                        cvd_change_val = calculator.get_cvd_change(minutes=lookback_minutes)
                        if cvd_change_val is not None and abs(cvd_change_val) >= float(cvd_threshold):
                            alert_triggered_for_rule = True
                            alert_details = {"type": "value", "value": cvd_change_val, "threshold": float(cvd_threshold)}
                    
                    if not alert_triggered_for_rule and cvd_percentage_threshold is not None:
                        # Assuming a percentage change method might exist or be added later
                        # For now, this part remains as is but depends on a method like get_cvd_change_percentage
                        cvd_change_pct = calculator.get_cvd_change_percentage(minutes=lookback_minutes)
                        if cvd_change_pct is not None and abs(cvd_change_pct) >= float(cvd_percentage_threshold):
                            alert_triggered_for_rule = True
                            alert_details = {"type": "percentage", "percentage": cvd_change_pct, "threshold": float(cvd_percentage_threshold)}
                
                elif rule_type == "cvd_ratio":
                    buy_ratio_threshold = getattr(rule_config, 'buy_ratio_threshold', None)
                    sell_ratio_threshold = getattr(rule_config, 'sell_ratio_threshold', None)
                    ratios = calculator.get_buy_sell_ratio(minutes=lookback_minutes)

                    if ratios:
                        if buy_ratio_threshold is not None and ratios.get('buy_ratio', 0) >= float(buy_ratio_threshold):
                            alert_triggered_for_rule = True
                            alert_details = {"type": "buy_ratio", "ratio": ratios.get('buy_ratio'), "threshold": float(buy_ratio_threshold), "sell_ratio": ratios.get('sell_ratio')}
                        elif sell_ratio_threshold is not None and ratios.get('sell_ratio', 0) >= float(sell_ratio_threshold):
                            alert_triggered_for_rule = True
                            alert_details = {"type": "sell_ratio", "ratio": ratios.get('sell_ratio'), "threshold": float(sell_ratio_threshold), "buy_ratio": ratios.get('buy_ratio')}

                elif rule_type == "cvd_level":
                    cvd_target_level = float(getattr(rule_config, 'cvd_level', 0.0))
                    level_condition = getattr(rule_config, 'level_condition', 'unknown').lower()
                    current_cvd = calculator.get_cvd()

                    if current_cvd is not None:
                        if level_condition == 'above' and current_cvd > cvd_target_level:
                            alert_triggered_for_rule = True
                        elif level_condition == 'below' and current_cvd < cvd_target_level:
                            alert_triggered_for_rule = True
                        if alert_triggered_for_rule:
                             alert_details = {"type": "level", "level": current_cvd, "target": cvd_target_level, "condition": level_condition}
                
                if alert_triggered_for_rule:
                    # Construct a more specific rule_id for CVD alerts
                    specific_id_part = f"{alert_details.get('type', 'general')}_"
                    specific_id_part += f"{alert_details.get('threshold', alert_details.get('target', ''))}"
                    rule_id = f"{rule_type}_{symbol}_{timeframe_duration_str if timeframe_duration_str else 'live'}_{specific_id_part}"
                    trigger_symbol = getattr(rule_config, 'symbol', symbol)

                    if self.state_manager.can_trigger(trigger_symbol, rule_id, cooldown):
                        self.state_manager.mark_triggered(trigger_symbol, rule_id)

                        base_title = f"CVD Alert: {exchange} {trigger_symbol}"
                        message_parts = [f"{exchange} - {trigger_symbol}: "]
                        context = {
                            "exchange": exchange, "symbol": trigger_symbol,
                            "rule_type": rule_type, "rule_id": rule_id,
                            "cooldown_seconds": cooldown,
                            "timeframe_duration": timeframe_duration_str,
                            "lookback_minutes": lookback_minutes
                        }

                        if rule_type == "cvd_change":
                            val_type = alert_details.get("type", "value")
                            val = alert_details.get("value") if val_type == "value" else alert_details.get("percentage")
                            thresh = alert_details.get("threshold")
                            unit = "" if val_type == "value" else "%"
                            base_title += f" CVD Change {val:.{volume_precision}f}{unit}"
                            message_parts.append(f"CVD changed by {val:.{volume_precision}f}{unit} over {timeframe_duration_str} (Threshold: {thresh}{unit}).")
                            context.update({"change_type": val_type, "cvd_change": val, "threshold": thresh})
                        
                        elif rule_type == "cvd_ratio":
                            ratio_type = alert_details.get("type")
                            ratio_val = alert_details.get("ratio")
                            thresh = alert_details.get("threshold")
                            base_title += f" {ratio_type.replace('_', ' ').title()} {ratio_val*100:.1f}%"
                            message_parts.append(f"{ratio_type.replace('_',' ').title()} of {ratio_val*100:.1f}% over {timeframe_duration_str} (Threshold: {thresh*100:.1f}%). B/S Ratio: {alert_details.get('buy_ratio',0)*100:.1f}% / {alert_details.get('sell_ratio',0)*100:.1f}%.")
                            context.update({"ratio_type": ratio_type, "triggered_ratio": ratio_val, "threshold": thresh, "buy_ratio": alert_details.get('buy_ratio'), "sell_ratio": alert_details.get('sell_ratio')})

                        elif rule_type == "cvd_level":
                            level_val = alert_details.get("level")
                            target_lvl = alert_details.get("target")
                            cond = alert_details.get("condition")
                            base_title += f" CVD {cond.title()} {target_lvl:.{volume_precision}f}"
                            message_parts.append(f"CVD at {level_val:.{volume_precision}f}, crossing {cond} threshold of {target_lvl:.{volume_precision}f}.")
                            context.update({"current_cvd_level": level_val, "target_level": target_lvl, "condition": cond})
                        
                        await self._dispatch_alert(base_title, " ".join(message_parts), context)

            except Exception as e:
                logger.error(f"Error evaluating {rule_type} rule for {exchange} {symbol}: {e} - Rule: {vars(rule_config) if hasattr(rule_config, '__dict__') else rule_config}", exc_info=True)

    async def _on_new_ticker_data(self, exchange: str, symbol: str, ticker_data_dict: dict):
        if not self._is_running: return
        # Initial log kept for verbosity during development, can be changed to debug level later
        ticker_data = ticker_data_dict
        logger.info(f"Received ticker: {exchange} {symbol}, Last: {ticker_data.get('last')}, Bid: {ticker_data.get('bid')}, Ask: {ticker_data.get('ask')}")

        symbol_alert_config = self._get_symbol_config(exchange, symbol)
        if not symbol_alert_config or not hasattr(symbol_alert_config, 'rules') or not symbol_alert_config.rules:
            # No specific rules for this symbol/exchange, or structure is not as expected.
            # logger.debug(f"No price level alert rules configured for {exchange} {symbol} or config structure issue.")
            return

        current_price_to_use: Optional[float] = None
        if ticker_data.get('last') is not None:
            current_price_to_use = float(ticker_data['last'])
        elif ticker_data.get('bid') is not None and ticker_data.get('ask') is not None:
            current_price_to_use = (float(ticker_data['bid']) + float(ticker_data['ask'])) / 2
        else:
            logger.warning(f"Ticker for {exchange} {symbol} has insufficient data to determine price (no last, or no bid/ask pair).")
            return

        for rule_config in symbol_alert_config.rules:
            if getattr(rule_config, 'type', None) == "price_level" and getattr(rule_config, 'enabled', True):
                try:
                    target_price = float(getattr(rule_config, 'target_price', 0.0))
                    condition = getattr(rule_config, 'condition', 'unknown').lower()
                    cooldown = int(getattr(rule_config, 'cooldown', 300)) # Default 5 mins cooldown
                    price_precision = getattr(symbol_alert_config, 'price_precision', 2) # From symbol config, default 2

                    if condition not in ["above", "below"]:
                        logger.warning(f"Unknown condition '{condition}' for price_level rule on {exchange} {symbol}. Skipping.")
                        continue
                    
                    condition_met = False
                    if condition == "above" and current_price_to_use > target_price:
                        condition_met = True
                    elif condition == "below" and current_price_to_use < target_price:
                        condition_met = True
                    
                    # Add other conditions like 'crosses', 'crosses_above', 'crosses_below' here if needed.
                    # These would require storing the previous state of the price relative to the target.

                    if condition_met:
                        rule_id = f"price_level_{symbol}_{condition}_{target_price}"
                        # Use symbol_name from rule_config if available, otherwise fallback to the one passed to handler
                        trigger_symbol = getattr(rule_config, 'symbol', symbol) 

                        if self.state_manager.can_trigger(trigger_symbol, rule_id, cooldown):
                            self.state_manager.mark_triggered(trigger_symbol, rule_id)
                            
                            alert_title = f"Price Alert: {exchange} {trigger_symbol} {condition.upper()} {target_price}"
                            alert_message = (
                                f"{exchange} - {trigger_symbol} is now {condition} {target_price}. "
                                f"Current price: {current_price_to_use:.{price_precision}f}."
                            )
                            alert_context = {
                                "exchange": exchange,
                                "symbol": trigger_symbol,
                                "rule_type": "price_level",
                                "condition": condition,
                                "target_price": target_price,
                                "current_price": current_price_to_use,
                                "rule_id": rule_id,
                                "cooldown_seconds": cooldown,
                                "price_precision": price_precision
                            }
                            await self._dispatch_alert(alert_title, alert_message, alert_context)
                except Exception as e:
                    logger.error(f"Error evaluating price_level rule for {exchange} {symbol}: {e} - Rule: {vars(rule_config) if hasattr(rule_config, '__dict__') else rule_config}", exc_info=True)

    def cleanup(self):
        """Called when AlertDataManager is being shut down."""
        self.stop_monitoring()
        logger.info("AlertDataManager cleaned up.")

    async def _initialize_processors_and_fetch_history(self):
        logger.info("Initializing data processors and fetching historical data...")
        if not self.active_alerts_config or not hasattr(self.active_alerts_config, 'symbols') or not isinstance(self.active_alerts_config.symbols, dict):
            logger.warning("No active symbol configurations to initialize processors for.")
            return

        for req_type, details_set in self._subscribed_requirements.items():
            if req_type == "trades":
                for exchange, symbol_name in details_set:
                    # Find all CVD rules for this symbol to determine max lookback needed
                    max_lookback_minutes = 0
                    
                    symbol_config = self._get_symbol_config(exchange, symbol_name)
                    if symbol_config and hasattr(symbol_config, 'rules'):
                        for rule in symbol_config.rules:
                            if rule.type.startswith('cvd_'):
                                # Duration string like "5m", "1h"
                                duration_str = getattr(rule, 'timeframe_duration_str', '5m') # Default to 5m
                                lookback_minutes = self._convert_duration_to_minutes(duration_str)
                                if lookback_minutes and lookback_minutes > max_lookback_minutes:
                                    max_lookback_minutes = lookback_minutes
                    
                    if max_lookback_minutes > 0:
                        unique_key = f"{exchange}_{symbol_name}"
                        if unique_key not in self.cvd_calculators:
                            logger.info(f"Initializing CVDCalculator for {unique_key} with a lookback of {max_lookback_minutes} minutes.")
                            # Pass the lookback period to the calculator
                            self.cvd_calculators[unique_key] = CVDCalculator(lookback_minutes=max_lookback_minutes)

                            # Now, fetch historical data to seed it
                            # The `fetch_candles` method in data_source is for OHLCV, we need raw trades.
                            # Assuming fetch_historical_trades can take a limit and returns newest first typically
                            historical_trades = await self.data_source.fetch_historical_trades(
                                exchange=exchange, 
                                symbol=symbol_name, 
                                limit=900
                            )

                            if historical_trades:
                                # CCXT often returns newest trades first, reverse for chronological order (oldest first for seeding)
                                historical_trades.reverse()
                                calculator = self.cvd_calculators[unique_key]
                                for trade_dict in historical_trades:
                                    # Convert the raw trade dictionary to a TradeData object
                                    trade_obj = TradeData.from_ccxt_trade(trade_dict)
                                    if trade_obj:
                                        # Now pass the object to the calculator
                                        calculator.add_trade(trade_obj)
                                    else:
                                        logger.warning(f"Failed to parse historical trade for {unique_key}: {trade_dict}")
                                logger.info(f"Seeded CVDCalculator for {unique_key} with {len(historical_trades)} trades.")
                            else:
                                logger.info(f"No historical trades returned for {unique_key} for CVD seeding.")
                        else:
                            logger.debug(f"CVDCalculator for {unique_key} already initialized.")
        logger.info("Finished initializing processors and fetching history.")

    async def _initialize_notifiers(self):
        logger.info("Initializing notifiers...")
        self.active_notifiers.clear()

        if not self.global_config or not hasattr(self.global_config, 'notification_settings') or not self.global_config.notification_settings:
            logger.warning("No notification settings found in global config. No external alerts will be sent.")
            return

        if not hasattr(self.global_config.notification_settings, 'notifiers') or not self.global_config.notification_settings.notifiers:
            logger.warning("Notification settings found, but no notifiers are configured. No external alerts will be sent.")
            return

        for notifier_conf in self.global_config.notification_settings.notifiers:
            if not getattr(notifier_conf, 'enabled', False):
                logger.debug(f"Notifier ID '{getattr(notifier_conf, 'id', 'N/A')}' (type: {getattr(notifier_conf, 'type', 'N/A')}) is disabled. Skipping.")
                continue
            
            notifier_instance: Optional[AsyncBaseNotifier] = None
            notifier_type = getattr(notifier_conf, 'type', 'unknown')
            notifier_id = getattr(notifier_conf, 'id', 'N/A')
            specific_config = getattr(notifier_conf, 'config', {}) or {} # Ensure it's a dict

            try:
                logger.info(f"Attempting to initialize notifier ID '{notifier_id}' of type '{notifier_type}'...")
                if notifier_type == "console":
                    notifier_instance = AsyncConsoleNotifier(specific_config)
                elif notifier_type == "email":
                    # Ensure email notifier gets its specific config correctly
                    notifier_instance = AsyncEmailNotifier(specific_config) 
                # Add other notifier types here, e.g.:
                # elif notifier_type == "telegram":
                #     notifier_instance = AsyncTelegramNotifier(specific_config)
                else:
                    logger.warning(f"Unknown or unsupported notifier type: '{notifier_type}' for ID '{notifier_id}'. Skipping.")
                    continue
                
                if notifier_instance:
                    await notifier_instance.start() # For any async setup like connections
                    self.active_notifiers.append(notifier_instance)
                    logger.info(f"Successfully initialized and started notifier: {notifier_type} (ID: {notifier_id})")

            except Exception as e:
                logger.error(f"Failed to initialize or start notifier {notifier_type} (ID: {notifier_id}): {e}", exc_info=True)
        
        if not self.active_notifiers:
            logger.warning("No notifiers were successfully initialized. Alerts will only be logged internally.")
        else:
            logger.info(f"Initialized {len(self.active_notifiers)} notifiers: {[type(n).__name__ for n in self.active_notifiers]}")

    async def _dispatch_alert(self, title: str, message: str, context: Dict[str, Any]):
        """Prepares and logs an alert. Phase 5 will send it via notifiers."""
        logger.info(f"ALERT TRIGGERED: {title}")
        logger.info(f"  Message: {message}")
        logger.info(f"  Context: {context}")

        if not self.active_notifiers:
            logger.warning("ALERT TRIGGERED but no active notifiers to dispatch to.")
            return

        # Format a simple message for the notifier queue
        formatted_message = f"[{title}] {message}"

        logger.info(f"Dispatching alert to {len(self.active_notifiers)} notifiers...")
        notification_tasks = []
        for notifier in self.active_notifiers:
            try:
                # Use the correct method: queue_notification
                task = asyncio.create_task(notifier.queue_notification(message=formatted_message))
                notification_tasks.append(task)
            except Exception as e:
                logger.error(f"Error creating notification task for notifier {type(notifier).__name__} for alert '{title}': {e}", exc_info=True)
        
        if notification_tasks:
            # Wait for all notification tasks to complete
            # We don't want one notifier failing to block others from being attempted if tasks are created.
            # The try-except for task creation handles errors before this point.
            # gather will collect results or exceptions.
            results = await asyncio.gather(*notification_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # The specific notifier that failed can be identified by order if needed, or log its type
                    # For now, just log that a notifier failed during send.
                    logger.error(f"A notifier failed to send alert '{title}': {result}") # Result here is the exception itself
            logger.info(f"Finished dispatching alert attempt for '{title}'.")
        else:
            logger.info(f"No notification tasks were created for alert '{title}'.")

# Example of how it might be run in a standalone script (main_alert_bot.py)
async def main_standalone():
    # 1. Initialize Trade Suite core components (simplified for example)
    #    In a real standalone app, these would be properly configured.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    
    # Create dummy/mock instances for Trade Suite components for this example skeleton
    # In a real standalone app, these would be fully initialized instances.
    class DummyEmitter:
        def register(self, *args, **kwargs): logger.debug(f"DummyEmitter.register called with {args} {kwargs}")
        def unregister(self, *args, **kwargs): logger.debug(f"DummyEmitter.unregister called with {args} {kwargs}")
        def emit(self, *args, **kwargs): logger.debug(f"DummyEmitter.emit called with {args} {kwargs}")

    class DummyData:
        def __init__(self): self.emitter = DummyEmitter() # Data often has its own emitter or uses the global one

    class DummyTaskManager:
        def subscribe(self, *args, **kwargs): logger.info(f"DummyTaskManager.subscribe called with {args} {kwargs}")
        def unsubscribe(self, *args, **kwargs): logger.info(f"DummyTaskManager.unsubscribe called with {args} {kwargs}")

    # Actual StateManager from your alert_bot
    # You'd need to ensure its dependencies (like config path for cooldowns) are met
    # For this skeleton, we'll assume it can be initialized simply.
    # state_manager_config_path = "path/to/state_manager_config.yaml" # Or however it's configured
    state_manager = StateManager() # May need config

    alerts_config_path = "sentinel/alert_bot/config/alerts_config.yaml" # Path to your alerts

    # Instantiate AlertDataManager
    alert_manager = AlertDataManager(
        data_source=DummyData(),       # Replace with actual Data instance
        task_manager=DummyTaskManager(), # Replace with actual TaskManager instance
        signal_emitter=DummyEmitter(), # Replace with actual SignalEmitter instance
        config_file_path=alerts_config_path
    )

    alert_manager.start_monitoring()

    try:
        # Keep the standalone bot running
        # In a real app, this would be a more robust loop, perhaps with signal handling for shutdown
        while True:
            await asyncio.sleep(1) 
            # Periodically, you might want to check health, re-evaluate configs if dynamic, etc.
            # For now, main work is event-driven by signals.
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    finally:
        alert_manager.cleanup()
        # Ensure TaskManager and Data source are also cleaned up if AlertDataManager doesn't own them
        # In standalone, ADM effectively "owns" them.

if __name__ == "__main__":
    # This is just for a conceptual standalone run. 
    # `trade_suite`'s actual TaskManager runs its own asyncio loop in a thread.
    # A standalone alert bot would need to manage its own asyncio lifecycle.
    
    # A more realistic standalone setup:
    # 1. Create SignalEmitter
    # 2. Create Data (needs emitter)
    # 3. Create TaskManager (needs Data) - TaskManager starts its own loop thread.
    # 4. Create StateManager
    # 5. Create AlertDataManager (needs Data, TaskManager, Emitter, StateManager)
    # 6. Call alert_manager.start_monitoring()
    # 7. Have a main loop that keeps the program alive, perhaps processing signals if needed by ADM directly,
    #    or simply waiting for KeyboardInterrupt.
    # 8. On shutdown, call alert_manager.cleanup(), task_manager.cleanup(), etc.
    
    # For now, running this __main__ directly will just show initialization logs
    # and then an error if you try to run the dummy main_standalone without an asyncio loop.
    # To truly test, you'd need to integrate with an asyncio event loop.
    asyncio.run(main_standalone())
    pass 