import json
import logging
import ccxt
import pandas as pd

from analysis.market_aggregator import MarketAggregator
from ccxt_interface import CCXTInterface
from influx import InfluxDB
from typing import List

class Data(CCXTInterface):
    def __init__(self, influx: InfluxDB, exchanges: List[str] = None):
        super().__init__(influx, exchanges)
        self.agg = MarketAggregator()
        
    async def stream_trades(self, symbols: List[str], since: str = None, limit: int = None, params={}):
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
        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]['ccxt']
            
            if exchange_object.has['watchTradesForSymbols']:
                while True:
                    try:
                        # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
                        trades = await exchange_object.watchTradesForSymbols (symbols, since, limit, params)
                        print(trades)
                        await self.influx.write_trades(exchange_id, trades)                
                        
                        # print(exchange_object.iso8601(exchange_object.milliseconds()), trades)
                        
                        self.agg.calc_trade_stats(exchange_id, trades)
                        self.agg.report_statistics()
                    except Exception as e:
                        logging.error(e)
                        
    # TODO: This
    async def stream_order_book(self, symbol: List[str], limit: int = 100, params = {}):
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
            
            exchange_object = self.exchange_list[exchange_id]['ccxt']
            if exchange_object.has['watchOrderBookForSymbols']:
                while True:
                    try:
                        orderbook = await exchange_object.watchOrderBookForSymbols (symbol, limit, params)

                        # orderbook = dict_keys(['bids', 'asks', 'timestamp', 'datetime', 'nonce', 'symbol'])
                        logging.info(f"{exchange_object.iso8601(exchange_object.milliseconds())}, {symbol}, {orderbook['asks'][0]}, {orderbook['bids'][0]}")
                    except Exception as e:
                        logging.error(e)
                        
    async def fetch_candles(self, exchanges: List[str], symbols: List[str], timeframes: List[str]):
        """
        The fetch_candles function fetches OHLCV data from the exchanges specified in the exchanges list.
            The symbols and timeframes lists are used to specify which symbols and timeframes to fetch.
            
            Args:
                exchanges (List[str]): A list of exchange IDs, e.g., ['binance', 'bitfinex'].
                symbols (List[str]): A list of symbol pairs, e.g., ['BTC/USDT', 'ETH/BTC'].
                timeframes (List[str]): A list of timeframe strings, e.g., ['5m', '1m'].
        
        :param self: Access the class variables and methods
        :param exchanges: List[str]: Specify which exchanges to fetch data from
        :param symbols: List[str]: Specify which symbols to fetch
        :param timeframes: List[str]: Specify the timeframes you want to fetch
        :param returns:
            dict: A nested dictionary structure:
                - Top-level keys are exchange names (e.g., 'coinbasepro').
                - Second-level keys are concatenated strings of symbol and timeframe (e.g., 'BTC/USDT-1m').
                - Values are pandas DataFrames with columns ['open', 'high', 'low', 'close', 'volume'] 
                and 'timestamp' as the index, representing OHLCV data.
        :doc-author: Trelent
        """
        # {exchange_id: ccxt_object}
        exchange_objects = {exchange: self.exchange_list[exchange]['ccxt'] for exchange in exchanges}
        all_candles = {}

        for exchange_name, exchange in exchange_objects.items():
            if exchange.has['fetchOHLCV']:
                for symbol in symbols:
                    
                    # If the exchange doesn't even have the symbol, skip this loop.
                    if symbol not in self.exchange_list[exchange_name]['symbols']:
                        logging.info(f'{symbol} not found on {exchange_name}.')
                        continue
                    
                    all_candles[exchange_name] = all_candles.get(exchange_name, {})
                    for timeframe in timeframes:
                        
                        # If they have the symbol but not timeframe, skip this loop too.
                        if timeframe not in self.exchange_list[exchange_name]['timeframes']:
                            logging.info(f'{timeframe} not found on {exchange_name}.')
                            continue
                    
                        try:
                            
                            candles = await exchange.fetch_ohlcv(symbol, timeframe)
                            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                            df.set_index('timestamp', inplace=True)
                            key = f'{symbol}-{timeframe}'
                            all_candles[exchange_name][key] = df
                            
                        except ccxt.NetworkError as e:
                            logging.error(f"Network error occurred: {e}")
                        except ccxt.ExchangeError as e:
                            logging.error(f"Exchange error occurred: {e}")
                        except Exception as e:
                            logging.error(f"An error occurred: {e}")
            else:
                logging.warning(f"{exchange_name} does not support OHLCV.")
        
        # await self.influx.write_candlesticks(all_candles)
        return all_candles