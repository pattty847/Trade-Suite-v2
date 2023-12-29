import asyncio
import logging
from typing import Dict, List

import ccxt
import pandas as pd

from src.analysis.market_aggregator import MarketAggregator
from src.data.ccxt_interface import CCXTInterface
from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter, Signals


class Data(CCXTInterface):
    def __init__(self, influx: InfluxDB, emitter: SignalEmitter, exchanges: List[str] = None):
        super().__init__(influx, exchanges)
        self.agg = MarketAggregator(influx, emitter)
        self.emitter = emitter

    async def stream_trades(
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


    async def stream_order_book(self, symbols: List[str]):
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
