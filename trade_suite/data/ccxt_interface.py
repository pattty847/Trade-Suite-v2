import asyncio
import json
import logging
import os
from typing import List

import ccxt
import ccxt.pro as ccxtpro


class CCXTInterface:
    """
    This class manages connections to CCXT exchanges.
        exchange_list[exchange][ccxt/symbols/timeframes]
    """

    def __init__(self, exchanges: List[str]):
        self.exchanges = exchanges
        self.exchange_list = None

    async def load_exchange(self, exchange_id: str):
        """
        Initialize a single exchange and add it to the supported exchanges list.
        """
        try:
            logging.info(f"Initializing {exchange_id}.")
            exchange_class = getattr(ccxtpro, exchange_id)(
                {
                    "apiKey": os.getenv("COINBASE_KEY"),
                    "secret": os.getenv("COINBASE_SECRET"),
                    "password": os.getenv("COINBASE_PASS"),
                    "newUpdates": True,
                }
                if exchange_id == "coinbasepro"
                else {}
            )

            await exchange_class.load_markets()

            if (
                exchange_class.has["watchTrades"]
                and exchange_class.has["fetchOHLCV"]
            ):
                return {
                    "ccxt": exchange_class,  # type: ccxt.Exchange
                    "symbols": sorted(list(exchange_class.markets)),
                    "timeframes": list(exchange_class.timeframes.keys()),
                }
            else:
                logging.info(f"{exchange_id} does not support all required features.")
                return None
        except ccxt.NetworkError as e:
            logging.error(f"Network error with {exchange_id}: {e}")
        except ccxt.ExchangeError as e:
            logging.error(f"Exchange error with {exchange_id}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error with {exchange_id}: {e}")
        return None

    async def load_exchanges(self, exchange: str = None):
        """
        Initialize the exchanges that are supported by ccxt. Optionally initialize a single exchange if provided.
        """
        supported_exchanges = self.exchange_list if self.exchange_list else {}

        exchanges_to_load = [exchange] if exchange else self.exchanges

        for exchange_id in exchanges_to_load:
            exchange_data = await self.load_exchange(exchange_id)
            if exchange_data:
                supported_exchanges[exchange_id] = exchange_data
                logging.info(f"{exchange_id.capitalize()} has been initialized.")

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
            exchange = self.exchange_list[exchange_id]["ccxt"]
            try:
                await exchange.close()
                logging.info(f"{exchange_id} closed successfully.")
            except Exception as e:
                logging.error(f"Error closing {exchange_id}: {e}")

        tasks = [
            close_exchange(exchange_id) for exchange_id in self.exchange_list.keys()
        ]
        await asyncio.gather(*tasks)

    def get_market_info(self, exchange_id: str, symbol: str):
        """
        Retrieve market information for a given symbol on a specific exchange.
        """
        exchange = self.exchange_list[exchange_id]["ccxt"]
        return exchange.market(symbol)

    def adjust_amount_to_precision(self, exchange_id: str, symbol: str, amount: float):
        """
        Adjust the amount to the required precision for a given symbol on a specific exchange.
        """
        exchange = self.exchange_list[exchange_id]["ccxt"]
        return exchange.amount_to_precision(symbol, amount)

    def adjust_price_to_precision(self, exchange_id: str, symbol: str, price: float):
        """
        Adjust the price to the required precision for a given symbol on a specific exchange.
        """
        exchange = self.exchange_list[exchange_id]["ccxt"]
        return exchange.price_to_precision(symbol, price)
