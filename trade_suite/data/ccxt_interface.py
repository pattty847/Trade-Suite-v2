import asyncio
import logging
import os
from typing import List

import ccxt
import ccxt.pro as ccxtpro

class CCXTInterface:
    '''
    This class manages connections to CCXT exchanges.
        exchange_list[exchange][ccxt/symbols/timeframes]
    '''

    def __init__(self, exchanges: List[str]):
        self.exchanges = exchanges
        self.exchange_list = None


    async def load_exchanges(self):
        """
        The load_exchanges function is used to initialize the exchanges that are supported by ccxt.
            It will load all of the markets for each exchange and then check if they have certain features,
            such as watchTrades, fetchOHLCV, watchOrderBookForSymbols and watchTradesForSymbols. If they do not have these features then it will not be added to the list of supported exchanges.
        
        :param self: Refer to the current instance of a class
        :return: A dict of the exchanges and their symbols
        :doc-author: Trelent
        """
        supported_exchanges = {}
        for exchange_id in self.exchanges:
            try:
                logging.info(f'Initializing {exchange_id}.')
                exchange_class = getattr(ccxtpro, exchange_id)(
                    {
                        'apiKey': os.getenv('COINBASE_KEY'),
                        'secret': os.getenv('COINBASE_SECRET'),
                        'password': os.getenv('COINBASE_PASS'),
                        'newUpdates': True,
                    }
                    if exchange_id == 'coinbasepro'
                    else {}
                )

                await exchange_class.load_markets()
                if (
                    exchange_class.has['watchTrades']
                    and exchange_class.has['fetchOHLCV']
                    and exchange_class.has['watchOrderBookForSymbols']
                    and exchange_class.has['watchTradesForSymbols']
                ):
                    supported_exchanges[exchange_id] = {
                        'ccxt': exchange_class,
                        'symbols': sorted(list(exchange_class.markets)),
                        'timeframes': list(exchange_class.timeframes.keys()),
                    }
                logging.info(f'{exchange_id.capitalize()} has been initialized.')
            except ccxt.NetworkError as e:
                logging.error(f'Network error with {exchange_id}: {e}')
            except ccxt.ExchangeError as e:
                logging.error(f'Exchange error with {exchange_id}: {e}')
            except Exception as e:
                logging.error(f'Unexpected error with {exchange_id}: {e}')
        self.exchange_list = supported_exchanges


    async def close_all_exchanges(self):
        """
        The close_all_exchanges function closes all exchanges in the exchange_list.
            It does this by calling close() on each ccxt object in the exchange_list.
            
        
        :param self: Represent the instance of the class
        :return: A list of tasks
        :doc-author: Trelent
        """
        async def close_exchange(exchange_id):
            exchange = self.exchange_list[exchange_id]['ccxt']
            try:
                await exchange.close()
                logging.info(f'{exchange_id} closed successfully.')
            except Exception as e:
                logging.error(f'Error closing {exchange_id}: {e}')

        tasks = [
            close_exchange(exchange_id) for exchange_id in self.exchange_list.keys()
        ]
        await asyncio.gather(*tasks)

    def get_market_info(self, exchange_id: str, symbol: str):
        """
        Retrieve market information for a given symbol on a specific exchange.
        """
        exchange = self.exchange_list[exchange_id]['ccxt']
        return exchange.market(symbol)

    def adjust_amount_to_precision(self, exchange_id: str, symbol: str, amount: float):
        """
        Adjust the amount to the required precision for a given symbol on a specific exchange.
        """
        exchange = self.exchange_list[exchange_id]['ccxt']
        return exchange.amount_to_precision(symbol, amount)

    def adjust_price_to_precision(self, exchange_id: str, symbol: str, price: float):
        """
        Adjust the price to the required precision for a given symbol on a specific exchange.
        """
        exchange = self.exchange_list[exchange_id]['ccxt']
        return exchange.price_to_precision(symbol, price)