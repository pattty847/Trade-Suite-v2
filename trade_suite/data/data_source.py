import asyncio
import logging
import os
from typing import Dict, List, Tuple

import ccxt
import pandas as pd

from trade_suite.analysis.market_aggregator import MarketAggregator
from trade_suite.data.ccxt_interface import CCXTInterface
from trade_suite.data.influx import InfluxDB
from trade_suite.gui.signals import SignalEmitter, Signals


# TODO: Make functions that watch one symbol at a time. Start/stop them with task manager


class Data(CCXTInterface):
    def __init__(
        self, influx: InfluxDB, emitter: SignalEmitter, exchanges: List[str] = None, force_public: bool = False
    ):
        super().__init__(exchanges, force_public=force_public)
        self.agg = MarketAggregator(influx, emitter)
        self.emitter = emitter
        
        # Reference to the asyncio event-loop that owns the GUI thread (or the
        # TaskManager loop if that is what we target).  It can be injected after
        # the Data instance has been created via ``set_ui_loop``.
        self._ui_loop: asyncio.AbstractEventLoop | None = None  # new
        self.exchange_semaphores: Dict[str, asyncio.Semaphore] = {} # New line for semaphores
        
        self.cache_dir = 'data/cache'
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    # --------------------------------------------------------------
    # Helper – allows TaskManager (or any caller) to provide the loop
    # on which GUI callbacks should be executed.
    # --------------------------------------------------------------
    def set_ui_loop(self, loop: asyncio.AbstractEventLoop):
        """Inject the target *loop* used for thread-safe signal emission.

        When a loop is registered we will prefer ``emit_threadsafe`` to bypass
        the fallback SignalEmitter queue.  If not set, we keep the legacy
        behaviour and fall back to ``emit``.
        """
        self._ui_loop = loop

    async def watch_trades_list(
        self,
        symbols: List[str],
        stop_event: asyncio.Event,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
    ):
        """
        The stream_trades function is a coroutine that streams trades from the exchanges in exchange_list.

        :param self: Represent the instance of the class
        :param symbols: List[str]: Specify which symbols to stream trades for
        :param stop_event: asyncio.Event: Event to signal when to stop the stream.
        :param since: str: Get trades after a certain timestamp
        :param limit: int: Limit the number of trades returned
        :param params: Pass additional parameters to the exchange
        :return: A list of dictionaries
        :doc-author: Trelent
        """

        # For each exchange pass start watching for trades for the list of symbols passed
        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]

            logging.info(f"Starting trade stream for {symbols} on {exchange_id}")
            # TODO: Add a condition to streaming
            while not stop_event.is_set():
                try:
                    # trades: Contains a dictionary with all the below information. Because we are passing a list of symbols the 'watchTradesForSymbols' function
                    # returns whatever the latest tick was for whichever coin for the exchange.
                    # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
                    trades = await exchange_object.watchTradesForSymbols(symbols)

                    if trades:
                        if self._ui_loop:
                            # Fast-path: schedule directly on the UI loop.
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.NEW_TRADE,
                                exchange=exchange_id,
                                trade_data=trades[0],
                            )
                        else:
                            # Fallback to queue-based emission.
                            self.emitter.emit(
                                Signals.NEW_TRADE,
                                exchange=exchange_id,
                                trade_data=trades[0],
                            )

                    if track_stats:
                        symbol, stats = self.agg.calc_trade_stats(exchange_id, trades)
                        # self.agg.report_statistics() # logging.info to console
                        if self._ui_loop:
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.TRADE_STAT_UPDATE,
                                symbol=symbol,
                                stats=stats,
                            )
                        else:
                            self.emitter.emit(
                                Signals.TRADE_STAT_UPDATE,
                                symbol=symbol,
                                stats=stats,
                            )

                    if write_stats and write_trades:
                        await self.influx.write_trades(exchange_id, trades)
                        await self.influx.write_stats(exchange_id, stats, symbol)
                except asyncio.CancelledError:
                    logging.info(f"Trade list stream for {symbols} on {exchange_id} cancelled.")
                    break # Exit loop on cancellation
                except Exception as e:
                    logging.error(e)
            logging.info(f"Trade list stream for {symbols} on {exchange_id} stopped.")

    async def watch_trades(
        self,
        symbol: str,
        exchange: str,
        stop_event: asyncio.Event,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
    ):
        """
        The watch_trades function is a method of the Data class that watches for trades on a specific exchange and symbol.
        It uses the ccxt library to connect to the exchange, then loops indefinitely, waiting for new trades.
        When new trades are received, they are processed and emitted via the NEW_TRADE signal.

        :param self: Refer to the object itself
        :param symbol: str: Specify the symbol to watch trades for
        :param exchange: str: Identify which exchange the data is coming from
        :param stop_event: asyncio.Event: Event to signal when to stop the stream.
        :param track_stats: bool: Determine whether or not we want to track statistics
        :param write_trades: bool: Write the trades to influxdb
        :param write_stats: bool: Write the statistics to a database
        :return: The following:
        :doc-author: Trelent
        """
        exchange_object = self.exchange_list[exchange]
        logging.info(f"Starting trade stream for {symbol} on {exchange}")
        stop_event.clear() # Ensure the event is clear initially
        # TODO: Add a condition to streaming
        while not stop_event.is_set():
            try:
                # trades: Contains a dictionary with all the below information. Because we are passing a list of symbols the 'watchTradesForSymbols' function
                # returns whatever the latest tick was for whichever coin for the exchange.
                # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
                logging.debug(f"Awaiting trades for {symbol}...")
                trades = await exchange_object.watch_trades(symbol)
                logging.debug(f"Received trades: {'Yes' if trades else 'No'}, Count: {len(trades) if trades else 0}")

                if trades:
                    logging.debug(f"Emitting NEW_TRADE signal...")
                    # Ensure we explicitly pass the exchange and trade_data parameters
                    if self._ui_loop:
                        # Fast-path: schedule directly on the UI loop.
                        self.emitter.emit_threadsafe(
                            self._ui_loop,
                            Signals.NEW_TRADE,
                            exchange=exchange,
                            trade_data=trades[0],
                        )
                    else:
                        # Fallback to queue-based emission.
                        self.emitter.emit(
                            Signals.NEW_TRADE,
                            exchange=exchange,
                            trade_data=trades[0],
                        )

                if track_stats:
                    symbol_key, stats = self.agg.calc_trade_stats(exchange, trades)
                    # self.agg.report_statistics() # logging.info to console
                    if self._ui_loop:
                        self.emitter.emit_threadsafe(
                            self._ui_loop,
                            Signals.TRADE_STAT_UPDATE,
                            symbol=symbol_key,
                            stats=stats,
                        )
                    else:
                        self.emitter.emit(
                            Signals.TRADE_STAT_UPDATE,
                            symbol=symbol_key,
                            stats=stats,
                        )

                if write_stats and write_trades:
                    await self.influx.write_trades(exchange, trades)
                    await self.influx.write_stats(exchange, stats, symbol_key)
            except asyncio.CancelledError:
                logging.info(f"Trade stream for {symbol} on {exchange} cancelled.")
                break # Exit loop on cancellation
            except Exception as e:
                logging.error(e)
        logging.info(f"Trade stream for {symbol} on {exchange} stopped.")

    async def watch_orderbooks(self, symbols: List[str], stop_event: asyncio.Event):
        """
        The watch_orderbooks function is a coroutine that takes in a list of symbols and returns an orderbook for each symbol on the exchange.
        The function will continue to run until it encounters an error, at which point it will log the error and restart itself.

        :param self: Make the function a method of the class
        :param symbols: List[str]: Specify which symbols you want to watch
        :param stop_event: asyncio.Event: Event to signal when to stop the stream.
        :return: An orderbook, which is a dictionary with the following keys:
        :doc-author: Trelent
        """

        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]
            logging.info(f"Starting orderbook stream for {symbols} on {exchange_id}")
            if exchange_object.has["watchOrderBookForSymbols"]:
                while not stop_event.is_set():
                    try:
                        orderbook = await exchange_object.watchOrderBookForSymbols(
                            symbols
                        )
                        # await self.influx.write_order_book(exchange_id, orderbook)
                        # orderbook = dict_keys(['bids': [[price, amount]], 'asks': [[price, amount]], 'timestamp', 'datetime', 'nonce', 'symbol'])
                        if self._ui_loop:
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange_id,
                                orderbook=orderbook,
                            )
                        else:
                            self.emitter.emit(
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange_id,
                                orderbook=orderbook,
                            )

                        await asyncio.sleep(0.3)
                    except asyncio.CancelledError:
                        logging.info(f"Orderbook list stream for {symbols} on {exchange_id} cancelled.")
                        break # Exit inner loop on cancellation
                    except Exception as e:
                        logging.error(e)
                # If the outer loop should also stop on cancellation, check event here or re-raise
                if not stop_event.is_set():
                    logging.info(f"Orderbook list stream stopping for {exchange_id} due to event clear.")
                    break # Exit outer loop if event is cleared
            logging.info(f"Orderbook list stream for {symbols} on {exchange_id} stopped.")

    async def watch_orderbook(self, exchange: str, symbol: str, stop_event: asyncio.Event):
        """
        The watch_orderbook function is a coroutine that takes in the exchange and symbol as parameters.
        It then creates an exchange_object variable which is equal to the ccxt object of the given exchange.
        Then it logs that it has started streaming orderbooks for a given symbol on a given exchange.
        Next, while True: (meaning forever) try: to create an orderbook variable which is equal to await
        the watch_orderbook function from ccxt with the parameter of symbol (which was passed into this function).
        Then emit Signals.ORDER_BOOK_UPDATE with parameters exchange and orderbook.

        :param self: Access the class attributes and methods
        :param exchange: str: Identify the exchange that we want to get the orderbook from
        :param symbol: str: Specify what symbol to watch
        :param stop_event: asyncio.Event: Event to signal when to stop the stream.
        :return: A dictionary with the following keys:
        :doc-author: Trelent
        """
        exchange_object = self.exchange_list[exchange]
        logging.info(f"Starting orderbook stream for {symbol} on {exchange}")
        stop_event.clear() # Ensure the event is clear initially
        
        # Throttle orderbook signal emission
        last_emit_time = 0
        throttle_interval = 0.5  # Emit max 2 times per second (500ms interval)
        latest_orderbook = None # Store the most recent orderbook
        
        while not stop_event.is_set():
            try:
                # logging.debug(f"Awaiting order book for {symbol}...") # Changed from INFO to DEBUG
                orderbook = await exchange_object.watch_order_book(symbol)
                # logging.debug(f"Received order book: {'Yes' if orderbook else 'No'}") # Changed from INFO to DEBUG

                if orderbook:
                    latest_orderbook = orderbook # Always store the latest received book

                # Check if throttle interval has passed and we have a book to send
                current_time = asyncio.get_event_loop().time()
                if latest_orderbook and (current_time - last_emit_time >= throttle_interval):
                    logging.debug(f"Throttled emit: Emitting ORDER_BOOK_UPDATE signal...")
                    # This emit call now seems redundant as TaskManager handles queuing and emission.
                    # However, keeping it for now preserves original logic flow if direct calls were intended.
                    # TODO: Review if this emit call can be removed entirely after TaskManager refactor.
                    if self._ui_loop:
                        self.emitter.emit_threadsafe(
                            self._ui_loop,
                            Signals.ORDER_BOOK_UPDATE,
                            exchange=exchange,
                            orderbook=latest_orderbook,  # Emit the latest stored book
                        )
                    else:
                        self.emitter.emit(
                            Signals.ORDER_BOOK_UPDATE,
                            exchange=exchange,
                            orderbook=latest_orderbook,  # Emit the latest stored book
                        )
                    last_emit_time = current_time
                    latest_orderbook = None # Clear after sending to avoid re-sending same data if no new book arrives

                # No explicit sleep needed here as watch_order_book implicitly waits

            except asyncio.CancelledError:
                logging.info(f"Orderbook stream for {symbol} on {exchange} cancelled.")
                break # Exit the loop if task is cancelled
            except Exception as e:
                logging.error(f"Error in orderbook stream for {symbol} on {exchange}: {e}")
                # Optional: Add a delay before retrying after an error
                await asyncio.sleep(1)
        logging.info(f"Orderbook stream for {symbol} on {exchange} stopped.")

    async def fetch_candles(
        self,
        exchanges: List[str],
        symbols: List[str],
        since: str,
        timeframes: List[str],
        write_to_db=False,
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        The fetch_candles function is used to fetch candles from the exchanges.

        :param self: Access the attributes and methods of the class
        :param exchanges: List[str]: Specify which exchanges to get data from
        :param symbols: List[str]: Define the symbols that we want to fetch data for
        :param since: str: Specify the start date of the candles that we want to fetch
        :param timeframes: List[str]: Specify the timeframes to fetch candles for
        :param write_to_db: Write the data to the database
        :return: A dictionary of dictionaries
        :doc-author: Trelent
        """
        all_candles = {}

        tasks = []
        for exchange in exchanges:
            if exchange in self.exchange_list:
                exchange_class = self.exchange_list[exchange]
                # Initialize semaphore for the exchange if it doesn't exist
                if exchange_class.id not in self.exchange_semaphores:
                    self.exchange_semaphores[exchange_class.id] = asyncio.Semaphore(5) # CONCURRENCY_PER_EXCHANGE = 5
                    logging.debug(f"Initialized semaphore for {exchange_class.id} with concurrency 5.")

                all_candles.setdefault(exchange, {})
                since_timestamp = exchange_class.parse8601(since)

                for symbol in symbols:
                    if symbol not in exchange_class.symbols:
                        logging.info(f"{symbol} not found on {exchange}.")
                        continue

                    for timeframe in timeframes:
                        if timeframe not in list(exchange_class.timeframes.keys()):
                            logging.info(f"{timeframe} not found on {exchange}.")
                            continue

                        task = asyncio.create_task(
                            self.fetch_and_process_candles(
                                exchange_class,
                                symbol,
                                timeframe,
                                since_timestamp,
                                exchange,
                                all_candles,
                            )
                        )
                        tasks.append(task)

        await asyncio.gather(*tasks)
        
        logging.info(all_candles)

        if write_to_db:
            try:
                await self.influx.write_candles(all_candles)
            except Exception as e:
                logging.error(f"Error writing to DB: {e}")

        return all_candles

    async def _load_cache(self, path: str, key: str) -> tuple[pd.DataFrame, int | None, int | None, bool]:
        """Loads candle data from a CSV cache file."""
        existing_df = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
        first_cached_timestamp = None
        last_cached_timestamp = None
        data_loaded_from_cache = False

        if os.path.exists(path):
            logging.debug(f"Cache found: {path}")
            try:
                # Ensure 'dates' is read as integer if possible, handle if not present during read.
                # This addresses a potential correctness issue from the feedback.
                cached_df = pd.read_csv(path, dtype={"dates": "Int64"}) # Use Int64 for nullable integers
                if not cached_df.empty and 'dates' in cached_df.columns and not cached_df['dates'].isnull().all():
                    # Ensure dates are sorted if loaded from cache, as subsequent logic relies on it.
                    cached_df = cached_df.sort_values(by='dates').reset_index(drop=True)
                    existing_df = cached_df
                    data_loaded_from_cache = True
                    first_cached_timestamp = existing_df['dates'].iloc[0]
                    last_cached_timestamp = existing_df['dates'].iloc[-1]
                    logging.debug(f"Cache for {key}: First ts: {first_cached_timestamp}, Last ts: {last_cached_timestamp}, Rows: {len(existing_df)}")
                else:
                    logging.debug(f"Cache file {path} is empty, malformed, or 'dates' column is missing/empty. Will fetch fresh data.")
            except pd.errors.EmptyDataError:
                logging.debug(f"Cache file {path} is empty. Will fetch fresh data.")
            except Exception as e:
                logging.error(f"Error loading cache {path}: {e}. Will attempt to fetch fresh data.")
                # existing_df is already initialized to empty, so no change needed here.
        return existing_df, first_cached_timestamp, last_cached_timestamp, data_loaded_from_cache

    async def _save_cache(self, df: pd.DataFrame, path: str, key: str, exchange_id: str, symbol: str, timeframe: str):
        """Saves candle data to a CSV cache file with metadata."""
        if not df.empty:
            directory = os.path.dirname(path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            # Ensure df is a copy to avoid SettingWithCopyWarning if it's a slice
            df_to_save = df.copy()

            # Add metadata columns
            df_to_save['exchange'] = exchange_id
            df_to_save['symbol'] = symbol
            df_to_save['timeframe'] = timeframe

            desired_columns = ['dates', 'opens', 'highs', 'lows', 'closes', 'volumes', 'exchange', 'symbol', 'timeframe']
            columns_to_save = [col for col in desired_columns if col in df_to_save.columns]
            
            df_to_save[columns_to_save].to_csv(path, index=False)
            logging.debug(f"Saved data for {key} to {path} with metadata columns. Rows: {len(df_to_save)}")
        else:
            logging.info(f"No data to save for {key} (DataFrame is empty). CSV not created/updated at {path}.")

    async def _prepend_historic_candles(self, exchange: ccxt.Exchange, symbol: str, timeframe: str,
                                        requested_since_timestamp: int,
                                        current_cache_start_timestamp: int,
                                        existing_df: pd.DataFrame,
                                        timeframe_duration_ms: int,
                                        cache_key: str) -> Tuple[pd.DataFrame, int | None]:
        """
        Fetches historic candle data to prepend to an existing cached DataFrame.
        This is used when the cache exists but starts later than the `requested_since_timestamp`.
        """
        prepend_fetch_until = current_cache_start_timestamp
        current_prepend_since = requested_since_timestamp
        prepended_ohlcv_list = []

        while current_prepend_since < prepend_fetch_until:
            logging.debug(f"Prepending {cache_key}: fetching from {current_prepend_since} up to {prepend_fetch_until}")
            # Use exchange's default limit or a common large number like 1000
            limit_for_prepend = exchange.options.get('fetchOHLCVLimit', 1000)
            
            ohlcv_prepend_batch = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, current_prepend_since, limit_for_prepend)
            
            if ohlcv_prepend_batch:
                # Filter out any data at or after the point where existing cache begins to avoid overlap before concat
                ohlcv_prepend_batch = [c for c in ohlcv_prepend_batch if c[0] < prepend_fetch_until]
                if not ohlcv_prepend_batch:
                    break  # No relevant data in batch
                prepended_ohlcv_list.extend(ohlcv_prepend_batch)
                last_ts_in_batch = ohlcv_prepend_batch[-1][0]
                current_prepend_since = last_ts_in_batch + timeframe_duration_ms
                if current_prepend_since >= prepend_fetch_until:
                    break  # Reached the start of existing cache
            else:
                break  # No more data available for prepending
        
        updated_df = existing_df
        new_first_cached_timestamp = current_cache_start_timestamp  # Default to old if no prepend occurred
        if prepended_ohlcv_list:
            prepend_df = pd.DataFrame(prepended_ohlcv_list, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            prepend_df['dates'] = prepend_df['dates'].astype('int64')
            # Concatenate, drop duplicates (keeping the newly fetched ones if any conflict, though filtering should prevent this), sort
            updated_df = pd.concat([prepend_df, existing_df]).drop_duplicates(subset=['dates'], keep='first').sort_values(by='dates').reset_index(drop=True)
            logging.debug(f"Prepended {len(prepend_df)} new rows to {cache_key}. Total rows now: {len(updated_df)}.")
            if not updated_df.empty:
                new_first_cached_timestamp = updated_df['dates'].iloc[0]
        
        return updated_df, new_first_cached_timestamp

    async def _fetch_candle_data_after_timestamp(self, exchange: ccxt.Exchange, symbol: str, timeframe: str,
                                                 fetch_from_timestamp: int,
                                                 fetch_until_timestamp: int, # typically 'now'
                                                 timeframe_duration_ms: int,
                                                 is_initial_cache_fill: bool) -> List[list]:
        """
        Fetches candle data in batches starting from `fetch_from_timestamp` up to `fetch_until_timestamp`.
        Includes logic to find the actual first candle if `is_initial_cache_fill` is true and no data is found initially.
        """
        all_newly_fetched_ohlcv = []
        current_loop_fetch_timestamp = fetch_from_timestamp
        
        # This flag helps manage the special "find first candle" logic for an initial fill scenario.
        attempting_first_batch_for_initial_fill = is_initial_cache_fill

        while current_loop_fetch_timestamp < fetch_until_timestamp:
            logging.debug(f"Fetching {symbol} {timeframe} from {pd.to_datetime(current_loop_fetch_timestamp, unit='ms', errors='coerce')} for {exchange.id}")
            
            # Rely on CCXT's default limit for incremental fetches unless a specific one is needed.
            ohlcv_batch = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, current_loop_fetch_timestamp)

            if ohlcv_batch:
                all_newly_fetched_ohlcv.extend(ohlcv_batch)
                current_loop_fetch_timestamp = ohlcv_batch[-1][0] + timeframe_duration_ms # Update the timestamp for the next fetch
                attempting_first_batch_for_initial_fill = False # Successful fetch, no longer the special first attempt
            else: # No data in batch (since timestamp was older than the oldest available candle)
                if attempting_first_batch_for_initial_fill:
                    logging.info(f"Initial fetch for {exchange.id} {symbol} {timeframe} from {pd.to_datetime(fetch_from_timestamp, unit='ms', errors='coerce')} yielded no data. Attempting to find actual first candle.")
                    # Try to find the very first candle available for this asset. Limit to 1 to get the timestamp.
                    first_ever_ohlcv_batch = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, since=1, limit=1) # since=1 is the oldest timestamp
                    
                    attempting_first_batch_for_initial_fill = False # This special attempt is now concluded.

                    if first_ever_ohlcv_batch:
                        actual_listing_timestamp = first_ever_ohlcv_batch[0][0]
                        logging.info(f"Found first actual candle for {exchange.id} {symbol} {timeframe} at {pd.to_datetime(actual_listing_timestamp, unit='ms', errors='coerce')}.")
                        
                        if actual_listing_timestamp >= current_loop_fetch_timestamp: # current_loop_fetch_timestamp is fetch_from_timestamp here
                             current_loop_fetch_timestamp = actual_listing_timestamp 
                             continue # Restart loop from this newly found actual_listing_timestamp
                        else:
                            # First candle is older than where we started, but we found nothing there.
                            # This implies no data in the requested range [fetch_from_timestamp, now).
                            logging.info(f"First candle for {exchange.id} {symbol} {timeframe} is at {pd.to_datetime(actual_listing_timestamp, unit='ms', errors='coerce')}, "
                                         f"which is before our initial targeted fetch from {pd.to_datetime(fetch_from_timestamp, unit='ms', errors='coerce')}. "
                                         f"No data found for the requested period. Stopping fetch for this symbol.")
                            break 
                    else:
                        logging.info(f"Could not find any candles for {exchange.id} {symbol} {timeframe} even when checking from earliest time. Stopping fetch.")
                        break 
                else: # Not the first attempt for an initial fill, or not an initial fill at all
                    logging.debug(f"No further data found for {exchange.id} {symbol} {timeframe} from {pd.to_datetime(current_loop_fetch_timestamp, unit='ms', errors='coerce')}. Ending fetch.")
                    break 
        
        return all_newly_fetched_ohlcv

    async def fetch_and_process_candles(self, exchange, symbol, timeframe, since_timestamp, exchange_name, all_candles):
        """First fetch of a new symbol/timeframe pair."""
        key = self._generate_cache_key(exchange.id, symbol, timeframe)
        path = f"{self.cache_dir}/{key}.csv"
        timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe)
        timeframe_duration_in_ms = timeframe_duration_in_seconds * 1000
        now = exchange.milliseconds()
        
        existing_df, first_cached_timestamp, last_cached_timestamp, data_loaded_from_cache = await self._load_cache(path, key)

        # Prepend logic: if cache was loaded and starts after `since_timestamp`
        if data_loaded_from_cache and first_cached_timestamp is not None and since_timestamp < first_cached_timestamp:
            logging.debug(f"Need to prepend data for {key}. Cache starts at {pd.to_datetime(first_cached_timestamp, unit='ms')}, requested since {pd.to_datetime(since_timestamp, unit='ms')}")
            existing_df, first_cached_timestamp = await self._prepend_historic_candles(
                exchange, symbol, timeframe, since_timestamp,
                first_cached_timestamp, existing_df, timeframe_duration_in_ms, key
            )
            # After prepending, the effective last_cached_timestamp might need re-evaluation if the original cache was empty past its declared first_timestamp
            # However, _load_cache ensures existing_df is sensible. If prepending occurred, existing_df is updated.
            # The 'last_cached_timestamp' from the initial load is still relevant for determining the start of *new* data fetching.

        # Determine where to start fetching new/initial data from
        if data_loaded_from_cache and last_cached_timestamp is not None:
            # Start fetching from the candle *after* the last cached one
            fetch_from_ts_for_new_data = last_cached_timestamp + timeframe_duration_in_ms 
        else:
            # No cache, or cache is empty/malformed, so start from the original 'since_timestamp'
            fetch_from_ts_for_new_data = since_timestamp

        # Primary fetching loop (for new data or initial fill if cache was empty before any operations)
        # 'is_initial_cache_fill_for_fetch' is true if we didn't load any valid data from cache initially.
        # This state determines if _fetch_candle_data_after_timestamp should try its "find first candle" logic.
        is_initial_cache_fill_for_fetch = not data_loaded_from_cache 
        
        all_newly_fetched_ohlcv = await self._fetch_candle_data_after_timestamp(
            exchange, symbol, timeframe, 
            fetch_from_ts_for_new_data, # Where to start this new fetching operation
            now, # Fetch up to current time
            timeframe_duration_in_ms,
            is_initial_cache_fill_for_fetch 
        )

        if all_newly_fetched_ohlcv:
            new_data_df = pd.DataFrame(all_newly_fetched_ohlcv, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            # Ensure 'dates' in new_data_df is int64 for consistent concatenation
            new_data_df['dates'] = new_data_df['dates'].astype('int64')
            if not new_data_df.empty: # This check is somewhat redundant if all_newly_fetched_ohlcv is not empty
                # existing_df is initialized by _load_cache (even if to an empty DF)
                existing_df = pd.concat([existing_df, new_data_df]).drop_duplicates(subset=['dates'], keep='last').sort_values(by='dates').reset_index(drop=True)
                logging.info(f"Fetched/updated {len(new_data_df)} new rows for {key}. Total rows now: {len(existing_df)}.")

        # Save the potentially modified (prepended and/or appended) existing_df to cache
        if not existing_df.empty:
            await self._save_cache(existing_df, path, key, exchange.id, symbol, timeframe)
            # The DataFrame stored in all_candles should ideally be without the extra metadata columns
            # if downstream code expects pure OHLCV. Or, ensure downstream code handles them.
            # For now, storing the df as saved (with metadata) for consistency with _save_cache.
            all_candles[exchange_name][key] = existing_df.copy() # Store a copy
        else:
            logging.info(f"No data fetched or found in cache for {exchange.id} {symbol} {timeframe}. CSV not created/updated at {path}.")
            # Ensure the key exists for this exchange_name even if df is empty, to prevent KeyErrors downstream
            if exchange_name not in all_candles:
                all_candles[exchange_name] = {}
            all_candles[exchange_name][key] = pd.DataFrame() 

    async def retry_fetch_ohlcv(self, exchange, symbol, timeframe, since, limit=None):
        """
        Retries fetching OHLCV data from the exchange with a specified number of retries.
        Passes the limit to fetch_ohlcv if provided.
        """
        max_retries = 3
        num_retries = 0
        
        # Ensure semaphore exists for this exchange, default to 5 if not already created by fetch_candles
        # This is a fallback; ideally, fetch_candles populates this for all exchanges it will use.
        if exchange.id not in self.exchange_semaphores:
            # This might indicate an issue if retry_fetch_ohlcv is called outside fetch_candles context
            # or before fetch_candles initializes semaphores for this exchange.
            # For robustness, create it here, but ideally it's pre-created.
            logging.warning(f"Semaphore for {exchange.id} not pre-initialized by fetch_candles. Creating with default concurrency 5.")
            self.exchange_semaphores[exchange.id] = asyncio.Semaphore(5) 
            
        semaphore = self.exchange_semaphores[exchange.id]

        # CCXT's fetch_ohlcv typically takes since, limit as direct args, not in params for this.
        # The default limit handling by CCXT is usually per-exchange or a CCXT-defined default (e.g., 1000 candles).
        
        while num_retries < max_retries:
            async with semaphore: # Acquire semaphore
                try:
                    # If limit is None, ccxt will use its default for fetch_ohlcv for that exchange.
                    # If limit is provided (e.g., 1 for first candle, or a specific batch size for prepending), it's used.
                    logging.debug(f"Attempting to fetch OHLCV for {symbol} {timeframe} on {exchange.id} since {pd.to_datetime(since, unit='ms', errors='coerce')} with limit {limit if limit is not None else 'default'}")
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, int(since), limit=limit)
                    
                    logging.debug(f"Fetched {len(ohlcv)} candles for {symbol} {timeframe} since {pd.to_datetime(since, unit='ms', errors='coerce')}" + (f" with limit {limit}" if limit is not None else "") + f" on {exchange.id}.")
                    return ohlcv
                except ccxt.RateLimitExceeded as e:
                    num_retries += 1
                    logging.warning(f"Rate limit exceeded for {symbol} on {exchange.id}. Attempt {num_retries}/{max_retries}. Retrying after delay... Error: {e}")
                    if num_retries >= max_retries:
                        logging.error(f"Failed to fetch {timeframe} {symbol} OHLCV on {exchange.id} due to rate limiting after {max_retries} attempts from {since}.")
                        return [] # Return empty list on failure
                    # Release semaphore before sleeping if error handling might suspend for long
                    # However, `async with` handles release on exit from block, including exceptions.
                    # The sleep for rate limit should ideally be outside the semaphore lock if it was acquired manually
                    # But with `async with`, the lock is held during sleep. This might be acceptable for rate limit backoff
                    # as it effectively reduces concurrency further during backoff periods for that specific task.
                    await asyncio.sleep(exchange.rateLimit / 1000 * (2 ** num_retries)) # Exponential backoff based on exchange rateLimit
                except ccxt.NetworkError as e:
                    num_retries += 1
                    logging.warning(f"Network error for {symbol} on {exchange.id}. Attempt {num_retries}/{max_retries}. Error: {e}")
                    if num_retries >= max_retries:
                        logging.error(f"Failed to fetch {timeframe} {symbol} OHLCV on {exchange.id} due to network issues after {max_retries} attempts from {since}.")
                        return []
                    await asyncio.sleep(1 * (2 ** num_retries)) # Simple exponential backoff
                except Exception as e:
                    num_retries += 1
                    logging.error(f"Error fetching {symbol} on {exchange.id}. Attempt {num_retries}/{max_retries}. Error: {type(e).__name__} - {e}")
                    if num_retries >= max_retries:
                        logging.error(f"Failed to fetch {timeframe} {symbol} OHLCV on {exchange.id} after {max_retries} attempts from {since} due to {type(e).__name__}.")
                        return [] # Return empty list on other critical failures
        return [] # Should be unreachable if max_retries is hit, but as a fallback.
            
    def _generate_cache_key(self, exchange_id: str, symbol: str, timeframe: str):
        """Generates a standardized cache key (filename part) for a given asset and timeframe."""
        # Sanitize symbol for use in filename (e.g., replace '/' with '-')
        safe_symbol = symbol.replace("/", "-")
        key = f"{exchange_id}_{safe_symbol}_{timeframe}"
        # The .csv extension is added when constructing the full path in fetch_and_process_candles
        logging.debug(f"Generated cache key: {key}") # Changed from info to debug as it can be verbose
        return key