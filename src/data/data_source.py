import asyncio
import json
import logging
import ccxt
import pandas as pd


from src.gui.signals import SignalEmitter, Signals
from src.analysis.market_aggregator import MarketAggregator
from src.data.ccxt_interface import CCXTInterface
from src.data.influx import InfluxDB
from typing import Dict, List


class Data(CCXTInterface):
    def __init__(self, influx: InfluxDB, emitter: SignalEmitter, exchanges: List[str] = None):
        super().__init__(influx, exchanges)
        self.emitter = emitter
        self.agg = MarketAggregator(influx, emitter)

    async def stream_trades(
        self, symbols: List[str], 
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
        chart_tag: str = None,
        params={},
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
                        print(trades)
                    # symbol, stats = self.agg.calc_trade_stats(exchange_id, trades)
                    # self.agg.report_statistics()

                    # await self.influx.write_trades(exchange_id, trades)
                    # await self.influx.write_stats(exchange_id, stats, symbol)
                except Exception as e:
                    logging.error(e)

    async def stream_order_book(self, symbols: List[str], limit: int = 100, params={}):
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
            if exchange_object.has["watchOrderBookForSymbols"]:
                while True:
                    try:
                        orderbook = await exchange_object.watchOrderBookForSymbols(
                            symbols, limit, params
                        )
                        with open('save.json', 'w') as f:
                            json.dump(orderbook, f)
                        
                        break
                    
                        await self.influx.write_order_book(exchange_id, orderbook)
                        # orderbook = dict_keys(['bids': [[price, amount]], 'asks': [[price, amount]], 'timestamp', 'datetime', 'nonce', 'symbol'])
                        # logging.info(f"{exchange_object.iso8601(exchange_object.milliseconds())}, {orderbook['symbol']}, {orderbook['asks'][0]} ({len(orderbook['asks'])}), {orderbook['bids'][0]} ({len(orderbook['bids'])})")
                    except Exception as e:
                        logging.error(e)

    async def stream_ob_and_trades(
        self, symbols: List[str], since: str = None, limit: int = None, params={}
    ):
        """
        The stream_ob_and_trades function is a coroutine that streams order book and trade data for the given symbols.
            It does this by calling the stream_for_exchange function on each exchange in self.exchange_list, which returns an asyncio task object.
            The tasks are then gathered together using asyncio's gather method, which allows them to run concurrently.

        :param self: Represent the instance of the class
        :param symbols: List[str]: Specify the symbols to stream
        :param since: str: Get the trades that have occurred since a certain time
        :param limit: int: Limit the amount of data that is returned
        :param params: Pass in the parameters for the websocket connection
        :return: A list of tasks
        :doc-author: Trelent
        """
        tasks = []
        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]["ccxt"]
            if (
                exchange_object.has["watchTradesForSymbols"]
                and exchange_object.has["watchOrderBookForSymbols"]
            ):
                tasks.append(
                    self.stream_ob_and_trades_(
                        exchange_id, exchange_object, symbols, since, limit, params
                    )
                )
        await asyncio.gather(*tasks)

    async def stream_ob_and_trades_(
        self, exchange_id, exchange_object, symbols, since, limit, params
    ):
        """
        The stream_for_exchange function is a coroutine that takes in an exchange_id, exchange_object, symbols, since and limit.
        It then uses the ccxt library to stream trades and order books for the given symbols on the given exchange.
        The function will continue to run until it encounters an error or is stopped by another process.

        :param self: Represent the instance of the class
        :param exchange_id: Identify which exchange the data is coming from
        :param exchange_object: Call the watchtradesforsymbols and watchorderbookforsymbols functions
        :param symbols: Specify which symbols to stream for
        :param since: Get trades from a certain time
        :param limit: Limit the number of trades and order book entries returned by the exchange
        :param params: Pass in the parameters for the watchtradesforsymbols and watchorderbookforsymbols functions
        :return: A coroutine object
        :doc-author: Trelent
        """
        logging.info(
            f"Starting trade and order book stream for {symbols} on {exchange_id}"
        )
        while True:
            try:
                trades = await exchange_object.watchTradesForSymbols(
                    symbols, since, limit, params
                )
                orderbook = await exchange_object.watchOrderBookForSymbols(
                    symbols, limit, params
                )
                await self.influx.write_ob_and_trades(exchange_id, trades, orderbook)
            except ccxt.NetworkError as e:
                logging.error(f"Network error occurred: {e}")
            except ccxt.ExchangeError as e:
                logging.error(f"Exchange error occurred: {e}")
            except Exception as e:
                logging.error(e)

    async def fetch_candles(self, exchanges: List[str], symbols: List[str], timeframes: List[str], write_to_db) -> Dict[str, Dict[str, pd.DataFrame]]:
        exchange_objects = {exch: self.exchange_list[exch]["ccxt"] for exch in exchanges}
        all_candles = {}

        for exchange_name, exchange in exchange_objects.items():
            exchange_data = self.exchange_list[exchange_name]
            all_candles.setdefault(exchange_name, {})

            for symbol in symbols:
                if symbol not in exchange_data["symbols"]:
                    logging.info(f"{symbol} not found on {exchange_name}.")
                    continue

                for timeframe in timeframes:
                    if timeframe not in exchange_data["timeframes"]:
                        logging.info(f"{timeframe} not found on {exchange_name}.")
                        continue

                    try:
                        candles = await exchange.fetch_ohlcv(symbol, timeframe)
                        df = pd.DataFrame(candles, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
                        df["dates"] /= 1000
                        key = f"{symbol}-{timeframe}"
                        all_candles[exchange_name][key] = df

                    except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
                        logging.error(f"{type(e).__name__} occurred: {e}")

                    if len(exchanges) == len(symbols) == len(timeframes) == 1:
                        self.emitter.emit(Signals.NEW_CANDLES, candles=df)

        self.emitter.emit(Signals.NEW_CANDLES, candles=all_candles)

        if write_to_db:
            try:
                await self.influx.write_candles(all_candles)
            except Exception as e:
                logging.error(f"Error writing to DB: {e}")

        return all_candles
