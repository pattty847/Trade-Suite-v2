import asyncio
import logging
from typing import Dict, Any, Set, Tuple
import pandas as pd
from datetime import datetime, timedelta

# Trade Suite components (adjust path if necessary)
from trade_suite.data.data_source import Data
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.signals import SignalEmitter, Signals

# Alert Bot components
from sentinel.alert_bot.config.loader import load_alerts_from_yaml
from sentinel.alert_bot.state.manager import StateManager
from sentinel.alert_bot.models.trade_data import TradeData
from sentinel.alert_bot.processors.cvd_calculator import CVDCalculator

# Placeholder for rule engine and notifiers, will be used later
# from sentinel.alert_bot.rules.engine import RuleEngine
# from sentinel.alert_bot.notifier.base import Notifier # Or specific notifier instances

class AlertDataManager:
    def __init__(self, 
                 data_source: Data, 
                 task_manager: TaskManager, 
                 signal_emitter: SignalEmitter,
                 state_manager: StateManager,
                 alerts_config_path: str):
        self.data_source = data_source
        self.task_manager = task_manager
        self.signal_emitter = signal_emitter
        self.state_manager = state_manager
        self.alerts_config_path = alerts_config_path
        
        self.active_alerts_config: Dict[str, Any] = {}
        self.subscribed_resources_tracker: Dict[str | Tuple, Dict] = {}
        self.cvd_calculators: Dict[Tuple[str, str], CVDCalculator] = {}

        # Potentially initialize rule engine and notifiers here or in a start method
        # self.rule_engine = RuleEngine() 
        # self.notifiers = [] # List of configured notifier instances

        self._register_signal_handlers()
        logging.info("AlertDataManager initialized.")

    @staticmethod
    def _format_timeframe(time_value: Any) -> str | None:
        """Converts various timeframe representations to CCXT string format."""
        if isinstance(time_value, str):
            # Assume if it's a string, it's already in a valid or near-valid format
            # Basic validation could be added, e.g., checking for 'm', 'h', 'd'
            return time_value.lower()
        if isinstance(time_value, int):
            if time_value < 60:
                return f"{time_value}m"
            elif time_value < 1440: # Less than 24 * 60
                if time_value % 60 == 0:
                    return f"{time_value // 60}h"
                else:
                    # Or handle as minutes if not perfectly divisible, e.g. 90 -> "90m"
                    # For now, let's assume we want whole hours or just minutes
                    logging.warning(f"Timeframe in minutes ({time_value}) not a whole hour, using minutes.")
                    return f"{time_value}m" 
            else: # Daily or more
                if time_value % 1440 == 0:
                    return f"{time_value // 1440}d"
                else:
                    logging.warning(f"Timeframe in minutes ({time_value}) not a whole day, using minutes.")
                    return f"{time_value}m"
        logging.warning(f"Unsupported timeframe format: {time_value}. Returning None.")
        return None

    def _register_signal_handlers(self):
        """Registers handlers for relevant signals from SignalEmitter."""
        # self.signal_emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        # self.signal_emitter.register(Signals.NEW_TRADE, self._on_new_trade)
        # self.signal_emitter.register(Signals.NEW_TICKER_DATA, self._on_new_ticker_data)
        # Commented out until methods are implemented to avoid errors
        logging.info("Signal handlers registered (placeholders).")

    def load_and_parse_config(self):
        """Loads alerts from the YAML file and parses them."""
        try:
            self.active_alerts_config = load_alerts_from_yaml(self.alerts_config_path)
            logging.info(f"Alerts configuration loaded successfully from {self.alerts_config_path}.")
            # Further parsing or validation of the loaded config can happen here
        except Exception as e:
            logging.error(f"Failed to load or parse alerts configuration from {self.alerts_config_path}: {e}", exc_info=True)
            self.active_alerts_config = {} # Ensure it's empty on failure

    async def start_monitoring(self):
        """
        Parses the alert configuration and subscribes to all necessary data streams
        via the TaskManager. Also initializes and seeds CVD calculators.
        """
        self.load_and_parse_config()
        if not self.active_alerts_config:
            logging.warning("No active alerts configured or failed to load config. Monitoring will not start effectively.")
            return

        logging.info("Starting monitoring: Subscribing to data streams based on alert configuration...")
        
        unique_candle_requirements: Set[Tuple[str, str, str]] = set()
        unique_trade_stream_requirements: Set[Tuple[str, str]] = set()
        unique_ticker_requirements: Set[Tuple[str, str]] = set()

        # --- CONFIG PARSING AND REQUIREMENT GATHERING ---
        for symbol_key, alert_config_for_symbol in self.active_alerts_config.items():
            exchange_id = getattr(alert_config_for_symbol, 'exchange', 'coinbase') 

            if hasattr(alert_config_for_symbol, 'price_levels') and alert_config_for_symbol.price_levels:
                unique_ticker_requirements.add((exchange_id, symbol_key))

            if hasattr(alert_config_for_symbol, 'percentage_changes') and alert_config_for_symbol.percentage_changes:
                for rule in alert_config_for_symbol.percentage_changes:
                    raw_tf = getattr(rule, 'timeframe', None)
                    if raw_tf:
                        formatted_tf = self._format_timeframe(raw_tf)
                        if formatted_tf:
                            unique_candle_requirements.add((exchange_id, symbol_key, formatted_tf))
                        else:
                            logging.warning(f"Invalid timeframe {raw_tf} for {symbol_key} percentage_change alert. Skipping candle subscription for this rule.")
                    else:
                        logging.warning(f"Missing timeframe for {symbol_key} percentage_change alert. Skipping candle subscription.")

            if hasattr(alert_config_for_symbol, 'cvd') and alert_config_for_symbol.cvd:
                unique_trade_stream_requirements.add((exchange_id, symbol_key))
                # Assuming cvd rules might also have a specific lookback_minutes for the calculator itself
                # For now, using a default lookback for CVDCalculator or a fixed one for seeding.

        # --- INITIALIZE AND SEED CVD CALCULATORS ---
        for ex, sym in unique_trade_stream_requirements:
            if (ex, sym) not in self.cvd_calculators:
                # TODO: Allow lookback_minutes to be configured per symbol/CVD rule in alerts_config.yaml
                cvd_lookback_minutes = 60 # Default or from config
                self.cvd_calculators[(ex, sym)] = CVDCalculator(lookback_minutes=cvd_lookback_minutes)
                logging.info(f"Initialized CVDCalculator for {ex} {sym} with {cvd_lookback_minutes}m lookback.")

                # Seed with historical trades
                # Calculate `since` timestamp for fetching historical trades
                # Fetch trades from (now - lookback_minutes - buffer) to ensure we have enough data
                # For simplicity, let's fetch trades from the last `cvd_lookback_minutes` + a small buffer (e.g., 5 min)
                # to ensure the period is covered. CCXT `since` is in milliseconds.
                since_datetime = datetime.now() - timedelta(minutes=cvd_lookback_minutes + 5)
                since_timestamp_ms = int(since_datetime.timestamp() * 1000)
                
                logging.info(f"Fetching historical trades for {ex} {sym} since {since_datetime} to seed CVDCalculator.")
                historical_trades_raw = await self.data_source.fetch_historical_trades(
                    exchange_id=ex, 
                    symbol=sym, 
                    since_timestamp=since_timestamp_ms,
                    limit=1000 # Fetch up to 1000 trades, might need adjustment
                )

                if historical_trades_raw:
                    parsed_historical_trades = []
                    for trade_raw in historical_trades_raw:
                        parsed_trade = TradeData.from_ccxt_trade(trade_raw)
                        if parsed_trade:
                            parsed_historical_trades.append(parsed_trade)
                    
                    # Sort by timestamp before adding to ensure correct order for CVD calculation
                    parsed_historical_trades.sort(key=lambda t: t.timestamp)
                    
                    cvd_calc = self.cvd_calculators[(ex, sym)]
                    for trade in parsed_historical_trades:
                        cvd_calc.add_trade(trade)
                    logging.info(f"Seeded CVDCalculator for {ex} {sym} with {len(parsed_historical_trades)} historical trades. Current CVD: {cvd_calc.get_cvd():.2f}")
                else:
                    logging.warning(f"No historical trades found to seed CVDCalculator for {ex} {sym}.")

        # --- PERFORMING SUBSCRIPTIONS ---
        for ex, sym, tf in unique_candle_requirements:
            req_dict = {'type': 'candles', 'exchange': ex, 'symbol': sym, 'timeframe': tf}
            logging.info(f"Subscribing to candles: {req_dict}")
            self.task_manager.subscribe(self, req_dict) # Pass AlertDataManager instance as subscriber ID
            self.subscribed_resources_tracker[('candles', ex, sym, tf)] = req_dict

        for ex, sym in unique_trade_stream_requirements:
            req_dict = {'type': 'trades', 'exchange': ex, 'symbol': sym}
            logging.info(f"Subscribing to trades: {req_dict}")
            self.task_manager.subscribe(self, req_dict)
            self.subscribed_resources_tracker[('trades', ex, sym)] = req_dict

        for ex, sym in unique_ticker_requirements:
            req_dict = {'type': 'ticker', 'exchange': ex, 'symbol': sym}
            logging.info(f"Subscribing to ticker: {req_dict}")
            self.task_manager.subscribe(self, req_dict)
            self.subscribed_resources_tracker[('ticker', ex, sym)] = req_dict
        
        # After subscribing, make sure signal handlers are active
        # These should be registered once, perhaps in __init__ or here if we want to be sure.
        # Re-registering is usually safe if the emitter handles duplicates, but let's ensure they are active.
        self.signal_emitter.unregister(Signals.UPDATED_CANDLES, self._on_updated_candles) # Try unregister first in case of re-start
        self.signal_emitter.unregister(Signals.NEW_TRADE, self._on_new_trade)
        self.signal_emitter.unregister(Signals.NEW_TICKER_DATA, self._on_new_ticker_data)
        
        self.signal_emitter.register(Signals.UPDATED_CANDLES, self._on_updated_candles)
        self.signal_emitter.register(Signals.NEW_TRADE, self._on_new_trade)
        self.signal_emitter.register(Signals.NEW_TICKER_DATA, self._on_new_ticker_data)
        logging.info("Signal handlers ensured and active.")

    def stop_monitoring(self):
        """Unsubscribes from all data streams and cleans up resources."""
        logging.info("Stopping monitoring: Unsubscribing from all data streams...")
        
        # Unregister signal handlers first to prevent processing further updates during shutdown
        try:
            self.signal_emitter.unregister(Signals.UPDATED_CANDLES, self._on_updated_candles)
            self.signal_emitter.unregister(Signals.NEW_TRADE, self._on_new_trade)
            self.signal_emitter.unregister(Signals.NEW_TICKER_DATA, self._on_new_ticker_data)
            logging.info("Signal handlers unregistered.")
        except ValueError:
            # This can happen if a handler wasn't registered (e.g., if start_monitoring failed before full registration)
            logging.warning("Attempted to unregister signal handlers, some may not have been registered.")

        # Unsubscribe AlertDataManager from all resources it subscribed to with TaskManager.
        # TaskManager.unsubscribe(widget) is designed to look up all subscriptions for that widget (self in this case)
        # and decrement reference counts, cleaning up resources if counts reach zero.
        if not self.subscribed_resources_tracker:
            logging.info("No resources were actively subscribed to by AlertDataManager, or tracker is empty.")
        else:
            logging.info(f"AlertDataManager is unsubscribing from {len(self.subscribed_resources_tracker)} tracked resource groups.")
            # Pass self (the AlertDataManager instance) to unsubscribe from all its previous subscriptions.
            self.task_manager.unsubscribe(self) 
        
        self.subscribed_resources_tracker.clear() # Clear our local tracker
        self.active_alerts_config.clear() # Clear loaded config
        self.cvd_calculators.clear() # Clear CVD calculators

        logging.info("Monitoring stopped and resources unsubscribed.")

    async def _on_updated_candles(self, exchange: str, symbol: str, timeframe: str, candles_df: pd.DataFrame):
        """Handles incoming OHLCV data."""
        # logging.debug(f"Received candle update for {exchange} {symbol} {timeframe}. Data length: {len(candles_df)}")
        # TODO: 
        # 1. Identify which alert rules need this specific (exchange, symbol, timeframe) data.
        # 2. For each relevant rule:
        #    a. Get the rule's conditions from self.active_alerts_config.
        #    b. Pass candles_df (and other necessary data like CVD if the rule needs it) to the rule engine.
        #    c. If rule triggers:
        #       i. Check self.state_manager.can_trigger(alert_id, rule_id_or_unique_condition_id)
        #       ii. If can_trigger is True:
        #           - self.state_manager.mark_triggered(...)
        #           - Dispatch notification via configured notifiers.
        pass

    async def _on_new_trade(self, exchange: str, trade_data: Dict):
        """Handles incoming raw trade data (for CVD, etc.)."""
        symbol = trade_data.get('symbol')
        if not symbol:
            logging.warning(f"Received trade data without symbol from exchange {exchange}: {trade_data}")
            return

        logging.debug(f"Received new trade for {exchange} {symbol}.")
        
        parsed_trade = TradeData.from_ccxt_trade(trade_data)
        if not parsed_trade:
            logging.warning(f"Failed to parse trade data for {exchange} {symbol}: {trade_data}")
            return

        cvd_calc_key = (exchange, symbol)
        if cvd_calc_key in self.cvd_calculators:
            cvd_calc = self.cvd_calculators[cvd_calc_key]
            cvd_calc.add_trade(parsed_trade)
            # logging.info(f"Updated CVD for {exchange} {symbol}: {cvd_calc.get_cvd():.2f}")
            # Further logic will be to check rules that depend on this CVD update.
            # For example, get all CVD related metrics:
            # current_cvd_value = cvd_calc.get_cvd()
            # cvd_change_5m = cvd_calc.get_cvd_change(5)
            # buy_sell_ratio_15m = cvd_calc.get_buy_sell_ratio(15)
            # Then pass these to the rule engine for evaluation.
        else:
            # This case should ideally not happen if subscriptions and calculator setup are correct
            logging.debug(f"Received trade for {exchange} {symbol}, but no CVD calculator is active for it.")

    async def _on_new_ticker_data(self, exchange: str, symbol: str, ticker_data_dict: Dict):
        """Handles incoming ticker data."""
        # logging.debug(f"Received ticker update for {exchange} {symbol}: {ticker_data_dict}")
        # TODO: 
        # 1. Store/process this ticker data as needed.
        # 2. Identify alert rules that need this specific (exchange, symbol) ticker data.
        # 3. Evaluate those rules (similar to _on_updated_candles logic).
        pass

    def cleanup(self):
        """Called when AlertDataManager is being shut down."""
        self.stop_monitoring()
        logging.info("AlertDataManager cleaned up.")

# Example of how it might be run in a standalone script (main_alert_bot.py)
async def main_standalone():
    # 1. Initialize Trade Suite core components (simplified for example)
    #    In a real standalone app, these would be properly configured.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    
    # Create dummy/mock instances for Trade Suite components for this example skeleton
    # In a real standalone app, these would be fully initialized instances.
    class DummyEmitter:
        def register(self, *args, **kwargs): logging.debug(f"DummyEmitter.register called with {args} {kwargs}")
        def unregister(self, *args, **kwargs): logging.debug(f"DummyEmitter.unregister called with {args} {kwargs}")
        def emit(self, *args, **kwargs): logging.debug(f"DummyEmitter.emit called with {args} {kwargs}")

    class DummyData:
        def __init__(self): self.emitter = DummyEmitter() # Data often has its own emitter or uses the global one

    class DummyTaskManager:
        def subscribe(self, *args, **kwargs): logging.info(f"DummyTaskManager.subscribe called with {args} {kwargs}")
        def unsubscribe(self, *args, **kwargs): logging.info(f"DummyTaskManager.unsubscribe called with {args} {kwargs}")

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
        state_manager=state_manager,
        alerts_config_path=alerts_config_path
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
        logging.info("Keyboard interrupt received, shutting down...")
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