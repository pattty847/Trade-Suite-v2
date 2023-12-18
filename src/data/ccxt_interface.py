import asyncio
import json
import os
import ccxt
import ccxt.pro as ccxtpro
import logging

from typing import List

from src.data.influx import InfluxDB


class CCXTInterface:
    """
    This class manages connections to CCXT exchanges.
    """

    def __init__(self, influx: InfluxDB, exchanges: List[str]):
        self.exchanges = exchanges
        self.exchange_list = None
        self.influx = influx

    async def load_exchanges(self):
        supported_exchanges = {}
        for exchange_id in self.exchanges:
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
                    and exchange_class.has["watchOrderBookForSymbols"]
                    and exchange_class.has["watchTradesForSymbols"]
                ):
                    supported_exchanges[exchange_id] = {
                        "ccxt": exchange_class,
                        "symbols": sorted(list(exchange_class.markets)),
                        "timeframes": list(exchange_class.timeframes.keys()),
                    }
                logging.info(f"{exchange_id.capitalize()} has been initialized.")
            except ccxt.NetworkError as e:
                logging.error(f"Network error with {exchange_id}: {e}")
            except ccxt.ExchangeError as e:
                logging.error(f"Exchange error with {exchange_id}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error with {exchange_id}: {e}")
        self.exchange_list = supported_exchanges

    async def set_exchanges(self, exchanges: List[str]):
        self.exchanges = exchanges
        await self.load_exchanges()

    async def __aenter__(self):
        await self.load_exchanges()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_all_exchanges()

    async def close_all_exchanges(self):
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
