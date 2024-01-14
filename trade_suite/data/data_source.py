import asyncio
import logging
from typing import Dict, List

import ccxt
import pandas as pd

from trade_suite.analysis.market_aggregator import MarketAggregator
from trade_suite.data.ccxt_interface import CCXTInterface
from trade_suite.data.influx import InfluxDB
from trade_suite.gui.signals import SignalEmitter, Signals


class Data(CCXTInterface):
    def __init__(self, influx: InfluxDB, emitter: SignalEmitter, exchanges: List[str] = None):
        super().__init__(exchanges)
        self.agg = MarketAggregator(influx, emitter)
        self.emitter = emitter

    async def watch_trades(
        self, symbols: List[str], 
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
            exchange_object = self.exchange_list[exchange_id]["ccxt"]

            logging.info(f"Starting trade stream for {symbols} on {exchange_id}")
            # TODO: Add a condition to streaming
            while True:
                try:
                    # trades: Contains a dictionary with all the below information. Because we are passing a list of symbols the 'watchTradesForSymbols' function
                    # returns whatever the latest tick was for whichever coin for the exchange.
                    # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
                    trades = await exchange_object.watchTradesForSymbols(
                        symbols
                    )
                    
                    if trades:
                        self.emitter.emit(Signals.NEW_TRADE, exchange=exchange_id, trade_data=trades[0])
                    
                    if track_stats:
                        symbol, stats = self.agg.calc_trade_stats(exchange_id, trades)
                        # self.agg.report_statistics() # print to console
                        self.emitter.emit(Signals.TRADE_STAT_UPDATE, symbol=symbol, stats=stats)

                    if write_stats and write_trades:
                        await self.influx.write_trades(exchange_id, trades)
                        await self.influx.write_stats(exchange_id, stats, symbol)
                except Exception as e:
                    logging.error(e)


    async def watch_orderbook(self, symbols: List[str]):
        """
        The stream_order_book function is a coroutine that streams the order book for a given symbol.
            The function takes in two parameters:
                1) symbol - A list of symbols to stream the order book for.
                    Example: ['BTC/USDT', 'ETH/USDT']
                2) limit - An integer representing how many orders to return on each side of the orderbook (bids and asks).
                    Default value is 100, but can be set as high as 1000 depending on exchange API limits.

        :param self: Represent the instance of the class
        :param symbol: List[str]: Specify the list of symbols you want to stream
        :param limit: int: Limit the number of orders returned in the orderbook
        :param params: Pass additional parameters to the exchange
        :return: A dictionary with the following keys:
        :doc-author: Trelent
        """
        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]["ccxt"]
            logging.info(f"Starting orderbook stream for {symbols} on {exchange_id}")
            if exchange_object.has["watchOrderBookForSymbols"]:
                while True:
                    try:
                        orderbook = await exchange_object.watchOrderBookForSymbols(
                            symbols
                        )
                        # await self.influx.write_order_book(exchange_id, orderbook)
                        # orderbook = dict_keys(['bids': [[price, amount]], 'asks': [[price, amount]], 'timestamp', 'datetime', 'nonce', 'symbol'])
                        self.emitter.emit(Signals.ORDER_BOOK_UPDATE, exchange=exchange_id, orderbook=orderbook)
                        
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logging.error(e)
                        

    async def fetch_candles(self, exchanges: List[str], symbols: List[str], since: str, timeframes: List[str], write_to_db=False) -> Dict[str, Dict[str, pd.DataFrame]]:
        exchange_objects = {exch: self.exchange_list[exch]["ccxt"] for exch in exchanges}
        all_candles = {}

        tasks = []
        for exchange_name, exchange in exchange_objects.items():
            exchange_data = self.exchange_list[exchange_name]
            all_candles.setdefault(exchange_name, {})
            since_timestamp = exchange.parse8601(since)

            for symbol in symbols:
                if symbol not in exchange_data["symbols"]:
                    logging.info(f"{symbol} not found on {exchange_name}.")
                    continue

                for timeframe in timeframes:
                    if timeframe not in exchange_data["timeframes"]:
                        logging.info(f"{timeframe} not found on {exchange_name}.")
                        continue

                    task = asyncio.create_task(
                        self.fetch_and_process_candles(exchange, symbol, timeframe, since_timestamp, exchange_name, all_candles)
                    )
                    tasks.append(task)

        await asyncio.gather(*tasks)

        if write_to_db:
            try:
                await self.influx.write_candles(all_candles)
            except Exception as e:
                logging.error(f"Error writing to DB: {e}")
        
        # If we're just requesting one exchange: symbol/timeframe pair we'll emit it for Charts
        if len(exchanges) == len(symbols) == len(timeframes) == 1 and self.emitter:
            first_exchange = next(iter(all_candles))
            first_symbol_timeframe_key = next(iter(all_candles[first_exchange]))
            first_candle_df = all_candles[first_exchange][first_symbol_timeframe_key]

            # Emitting the data
            if self.emitter:
                self.emitter.emit(Signals.NEW_CANDLES, candles=first_candle_df)

        return all_candles


    async def fetch_and_process_candles(self, exchange, symbol, timeframe, since_timestamp, exchange_name, all_candles):
        try:
            timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe)
            timeframe_duration_in_ms = timeframe_duration_in_seconds * 1000
            now = exchange.milliseconds()
            fetch_since = since_timestamp
            all_ohlcv = []

            while fetch_since < now:
                ohlcv = await self.retry_fetch_ohlcv(exchange, 3, symbol, timeframe, fetch_since)
                if not ohlcv:
                    break
                fetch_since = ohlcv[-1][0] + timeframe_duration_in_ms
                all_ohlcv += ohlcv

            df = pd.DataFrame(all_ohlcv, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            df["dates"] /= 1000
            key = f"{symbol}-{timeframe}"
            all_candles[exchange_name][key] = df

        except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
            logging.error(f"{type(e).__name__} occurred: {e}")
    
    
    async def retry_fetch_ohlcv(self, exchange, max_retries, symbol, timeframe, since):
        num_retries = 0
        while num_retries < max_retries:
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since)
                return ohlcv
            except Exception as e:
                num_retries += 1
                logging.error(f"Attempt {num_retries}: {e}")
                if num_retries >= max_retries:
                    raise Exception(f"Failed to fetch {timeframe} {symbol} OHLCV in {max_retries} attempts")
                
    
    async def fetch_stats_for_symbol(self, exchange, symbol):
        try:
            response = await exchange.publicGetProductsIdStats({'id': symbol})
            return response
        except Exception as e:
            print(f"Error fetching stats for {symbol}: {e}")
            return None

    async def fetch_all_stats(self, exchange, currency: str = "USD"):
        exchange = self.exchange_list[exchange]['ccxt']
        symbols = self.exchange_list[exchange]['symbols']
        
        tasks = [
            self.fetch_stats_for_symbol(exchange, symbol)
            for symbol in symbols
            if not currency or symbol.split('/')[-1] == currency
        ]
        results = await asyncio.gather(*tasks)
        
        results_ = {}
        for stat in results:
            for symbol in symbols:
                results_[symbol] = stat
        
        return results_
    
    async def fetch_highest_volume(self, n: int):
        results = self.fetch_all_stats()