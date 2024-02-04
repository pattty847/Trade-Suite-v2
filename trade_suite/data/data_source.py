import asyncio
import logging
import os
from typing import Dict, List

import ccxt
import pandas as pd

from analysis.market_aggregator import MarketAggregator
from data.ccxt_interface import CCXTInterface
from data.influx import InfluxDB
from gui.signals import SignalEmitter, Signals


# TODO: Make functions that watch one symbol at a time. Start/stop them with task manager


class Data(CCXTInterface):
    def __init__(
        self, influx: InfluxDB, emitter: SignalEmitter, exchanges: List[str] = None
    ):
        super().__init__(exchanges)
        self.agg = MarketAggregator(influx, emitter)
        self.emitter = emitter
        
        self.cache_dir = 'data/cache'
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.is_running = True

    async def watch_trades_list(
        self,
        symbols: List[str],
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
    ):
        """
        The stream_trades function is a coroutine that streams trades from the exchanges in exchange_list.

        :param self: Represent the instance of the class
        :param symbols: List[str]: Specify which symbols to stream trades for
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
            while self.is_running:
                try:
                    # trades: Contains a dictionary with all the below information. Because we are passing a list of symbols the 'watchTradesForSymbols' function
                    # returns whatever the latest tick was for whichever coin for the exchange.
                    # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
                    trades = await exchange_object.watchTradesForSymbols(symbols)

                    if trades:
                        self.emitter.emit(
                            Signals.NEW_TRADE,
                            exchange=exchange_id,
                            trade_data=trades[0],
                        )

                    if track_stats:
                        symbol, stats = self.agg.calc_trade_stats(exchange_id, trades)
                        # self.agg.report_statistics() # logging.info to console
                        self.emitter.emit(
                            Signals.TRADE_STAT_UPDATE, symbol=symbol, stats=stats
                        )

                    if write_stats and write_trades:
                        await self.influx.write_trades(exchange_id, trades)
                        await self.influx.write_stats(exchange_id, stats, symbol)
                except Exception as e:
                    logging.error(e)

    async def watch_trades(
        self,
        tab: str,
        symbol: str,
        exchange: str,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
    ):
        """
        The watch_trades function is a coroutine that will continuously stream trades from the exchange.
            It will also calculate trade statistics and write them to InfluxDB if enabled.

        :param self: Represent the instance of the class
        :param tab: str: Identify the tab that is being used
        :param symbol: str: Specify which coin you want to watch
        :param exchange: str: Identify which exchange the data is coming from
        :param track_stats: bool: Determine whether or not we want to track statistics
        :param write_trades: bool: Write the trades to influxdb
        :param write_stats: bool: Write the statistics to a database
        :param : Determine which tab the data is being sent to
        :return: The following:
        :doc-author: Trelent
        """
        exchange_object = self.exchange_list[exchange]
        logging.info(f"Starting trade stream for {symbol} on {exchange} tab {tab}")
        # TODO: Add a condition to streaming
        while self.is_running:
            try:
                # trades: Contains a dictionary with all the below information. Because we are passing a list of symbols the 'watchTradesForSymbols' function
                # returns whatever the latest tick was for whichever coin for the exchange.
                # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
                trades = await exchange_object.watch_trades(symbol)

                if trades:
                    self.emitter.emit(
                        Signals.NEW_TRADE,
                        tab=tab,
                        exchange=exchange,
                        trade_data=trades[0],
                    )

                if track_stats:
                    symbol, stats = self.agg.calc_trade_stats(exchange, trades)
                    # self.agg.report_statistics() # logging.info to console
                    self.emitter.emit(
                        Signals.TRADE_STAT_UPDATE, symbol=symbol, stats=stats
                    )

                if write_stats and write_trades:
                    await self.influx.write_trades(exchange, trades)
                    await self.influx.write_stats(exchange, stats, symbol)
            except Exception as e:
                logging.error(e)

    async def watch_orderbooks(self, symbols: List[str]):
        """
        The watch_orderbooks function is a coroutine that takes in a list of symbols and returns an orderbook for each symbol on the exchange.
        The function will continue to run until it encounters an error, at which point it will log the error and restart itself.

        :param self: Make the function a method of the class
        :param symbols: List[str]: Specify which symbols you want to watch
        :return: An orderbook, which is a dictionary with the following keys:
        :doc-author: Trelent
        """

        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]
            logging.info(f"Starting orderbook stream for {symbols} on {exchange_id}")
            if exchange_object.has["watchOrderBookForSymbols"]:
                while self.is_running:
                    try:
                        orderbook = await exchange_object.watchOrderBookForSymbols(
                            symbols
                        )
                        # await self.influx.write_order_book(exchange_id, orderbook)
                        # orderbook = dict_keys(['bids': [[price, amount]], 'asks': [[price, amount]], 'timestamp', 'datetime', 'nonce', 'symbol'])
                        self.emitter.emit(
                            Signals.ORDER_BOOK_UPDATE,
                            exchange=exchange_id,
                            orderbook=orderbook,
                        )

                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logging.error(e)

    async def watch_orderbook(self, tab, exchange: str, symbol: str):
        """
        The watch_orderbook function is a coroutine that takes in the tab, exchange and symbol as parameters.
        It then creates an exchange_object variable which is equal to the ccxt object of the given exchange.
        Then it logs that it has started streaming orderbooks for a given symbol on a given exchange.
        Next, while True: (meaning forever) try: to create an orderbook variable which is equal to await
        the watch_orderbook function from ccxt with the parameter of symbol (which was passed into this function).
        Then emit Signals.ORDER_BOOK_UPDATE with parameters tab=tab,exchange

        :param self: Access the class attributes and methods
        :param tab: Identify the tab that is being updated
        :param exchange: str: Identify the exchange that we want to get the orderbook from
        :param symbol: str: Specify what symbol to watch
        :return: A dictionary with the following keys:
        :doc-author: Trelent
        """
        exchange_object = self.exchange_list[exchange]
        logging.info(f"Starting orderbook stream for {symbol} on {exchange}")
        while self.is_running:
            try:
                orderbook = await exchange_object.watch_order_book(symbol)
                # await self.influx.write_order_book(exchange_id, orderbook)
                # orderbook = dict_keys(['bids': [[price, amount]], 'asks': [[price, amount]], 'timestamp', 'datetime', 'nonce', 'symbol'])
                self.emitter.emit(
                    Signals.ORDER_BOOK_UPDATE,
                    tab=tab,
                    exchange=exchange,
                    orderbook=orderbook,
                )

                await asyncio.sleep(0.3)
            except Exception as e:
                logging.error(e)

    async def fetch_candles(
        self,
        tab: str,
        exchanges: List[str],
        symbols: List[str],
        since: str,
        timeframes: List[str],
        write_to_db=False,
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        The fetch_candles function is used to fetch candles from the exchanges.

        :param self: Access the attributes and methods of the class
        :param tab: str: Identify the tab in which the data is being requested from
        :param exchanges: List[str]: Specify which exchanges to get data from
        :param symbols: List[str]: Define the symbols that we want to fetch data for
        :param since: str: Specify the start date of the candles that we want to fetch
        :param timeframes: List[str]: Specify the timeframes to fetch candles for
        :param write_to_db: Write the data to the database
        :param : Determine the exchange, symbol and timeframe for which we want to fetch candles
        :return: A dictionary of dictionaries
        :doc-author: Trelent
        """
        all_candles = {}

        tasks = []
        for exchange in exchanges:
            if exchange in self.exchange_list:
                exchange_class = self.exchange_list[exchange]
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

        # If we're just requesting one exchange: symbol/timeframe pair we'll just emit that one
        if len(exchanges) == len(symbols) == len(timeframes) == 1 and self.emitter:
            first_exchange = next(iter(all_candles))
            first_symbol_timeframe_key = next(iter(all_candles[first_exchange]))
            first_candle_df = all_candles[first_exchange][first_symbol_timeframe_key]

            # Emitting the data
            if self.emitter:
                self.emitter.emit(
                    Signals.NEW_CANDLES,
                    tab=tab,
                    exchange=exchanges[0],
                    candles=first_candle_df,
                )
                return

        return all_candles

    async def fetch_and_process_candles(self, exchange, symbol, timeframe, since_timestamp, exchange_name, all_candles):
        key = self._generate_cache_key(exchange.id, symbol, timeframe)
        path = f"{self.cache_dir}/{key}.csv"
        logging.debug(f"Path: {path}")
        timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe)
        timeframe_duration_in_ms = timeframe_duration_in_seconds * 1000
        now = exchange.milliseconds()
        
        try:
            existing_df = None
            if os.path.exists(path):
                logging.debug(f"Cache found: {path}")
                existing_df = pd.read_csv(path)
                first_cached_timestamp = existing_df['dates'].iloc[0]
                last_cached_timestamp = existing_df['dates'].iloc[-1]
                logging.debug(f"Last timestamp: {last_cached_timestamp} - First timestamp: {first_cached_timestamp}")
                
                # Determine if we need to prepend
                if since_timestamp < first_cached_timestamp:
                    prepend_since = since_timestamp
                    logging.debug(f"Prepend since: {prepend_since}")
                    while prepend_since < first_cached_timestamp:
                        prepend_ohlcv = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, prepend_since)
                        if prepend_ohlcv:
                            prepend_since = prepend_ohlcv[-1][0] + (timeframe_duration_in_ms)  # Adjust for next batch
                            # Prepend this data
                            prepend_df = pd.DataFrame(prepend_ohlcv, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
                            if not prepend_df.empty:
                                existing_df = pd.concat([prepend_df, existing_df]).drop_duplicates().reset_index(drop=True)
                        else:
                            break  # No more data to prepend

                fetch_since = last_cached_timestamp  # Start timestamp for appending
            else:
                fetch_since = since_timestamp
                existing_df = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            
            # Fetch and append new data
            while fetch_since < now:
                logging.debug(f"Now: {now} - Fetch since: {fetch_since}")
                append_ohlcv = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, fetch_since)
                if append_ohlcv:
                    fetch_since = append_ohlcv[-1][0] + (timeframe_duration_in_ms)  # Adjust for next batch
                    append_df = pd.DataFrame(append_ohlcv, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
                    # Ensure append_df is not empty before attempting concatenation
                    if not append_df.empty:
                        # Optionally, filter out columns that are entirely NA if necessary
                        # append_df = append_df.dropna(axis=1, how='all')
                        
                        # Concatenate DataFrames while ensuring no entirely empty or all-NA columns are causing issues
                        existing_df = pd.concat([existing_df, append_df]).drop_duplicates().reset_index(drop=True)
                else:
                    break  # No more data to append
                
            directory = os.path.dirname(path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                
            existing_df = existing_df.drop_duplicates(subset=['dates'], keep='last').reset_index(drop=True)

            # Save the updated DataFrame to CSV
            existing_df.to_csv(path, index=False)

            # Update in-memory cache
            all_candles[exchange_name][key] = existing_df

        except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
            logging.error(f"{type(e).__name__} occurred: {e}")



    async def retry_fetch_ohlcv(self, exchange, symbol, timeframe, since):
        max_retries = 3
        num_retries = 0
        while num_retries < max_retries:
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, int(since))
                logging.info(f"Fetched {len(ohlcv)} candles.")
                return ohlcv
            except Exception as e:
                num_retries += 1
                logging.error(f"Attempt {num_retries}: {e}")
                if num_retries >= max_retries:
                    raise Exception(
                        f"Failed to fetch {timeframe} {symbol} OHLCV in {max_retries} attempts"
                    )
                    
    def _generate_cache_key(self, exchange: str, symbol: str, timeframe: str):
        symbol = symbol.replace("/", "-")
        cache = f"{exchange}_{symbol}_{timeframe}"
        logging.info(f"cache: {cache}")
        return cache

    async def fetch_stats_for_symbol(self, exchange, symbol):
        try:
            response = await exchange.publicGetProductsIdStats({"id": symbol})
            return response
        except Exception as e:
            logging.info(f"Error fetching stats for {symbol}: {e}")
            return None

    async def fetch_all_stats(self, exchange, currency: str = "USD"):
        exchange = self.exchange_list[exchange]
        symbols = exchange.symbols

        tasks = [
            self.fetch_stats_for_symbol(exchange, symbol)
            for symbol in symbols
            if not currency or symbol.split("/")[-1] == currency
        ]
        results = await asyncio.gather(*tasks)

        results_ = {}
        for stat in results:
            for symbol in symbols:
                results_[symbol] = stat

        return results_

    async def fetch_highest_volume(self, n: int):
        results = self.fetch_all_stats()
