import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import ccxt
import ccxt.pro as ccxtpro


class CCXTInterface:
    _instances = {}

    """
    This class manages connections to CCXT exchanges.
        exchange_list[exchange_id] = exchange_class (ccxt instance)
    """

    def __init__(self, exchanges: List[str]):
        self.exchanges = exchanges
        self.exchange_list: Dict[str, Dict[str, Any]] = {}

    async def load_exchange(self, exchange_id: str):
        """
        Initialize a single exchange with or without credentials.
        """
        if exchange_id in self._instances:
            logging.info(f"Using existing instance for {exchange_id}.")
            return self._instances[exchange_id]

        credentials = self._get_credentials(exchange_id)

        try:
            if not credentials:
                logging.error(f"Credentials not found for {exchange_id}")
            else:
                logging.info(f"Initializing {exchange_id} with credentials.")
                
            exchange_class: ccxt.Exchange = getattr(ccxtpro, exchange_id)(credentials)

            await exchange_class.load_markets()

            if all(
                feature in exchange_class.has
                for feature in ["watchTrades", "watchOrderBook", "fetchOHLCV"]
            ):

                # Store only the exchange_class instance
                self._instances[exchange_id] = exchange_class
                return exchange_class
            else:
                logging.info(f"{exchange_id} does not support all required features.")
                return None
        except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
            logging.error(f"Error with {exchange_id}: {e}")
        return None

    async def load_exchanges(self, exchanges: List[str] = None):
        """
        Initialize a list of exchanges passed to the function, or if nothing is passed, initialize all exchanges in self.exchangnes
        """
        exchanges_to_load = [exchanges] if exchanges else self.exchanges

        for exchange_id in exchanges_to_load:
            exchange_data = await self.load_exchange(exchange_id)
            if exchange_data:
                self.exchange_list[exchange_id] = exchange_data
                logging.info(f"{exchange_id.capitalize()} has been initialized.")

    async def close_all_exchanges(self):
        """
        The close_all_exchanges function closes all exchanges in the exchange_list.
            It does this by calling close() on each ccxt object in the exchange_list.


        :param self: Represent the instance of the class
        :return: A list of tasks
        :doc-author: Trelent
        """

        async def close_exchange(exchange_id):
            exchange = self.exchange_list[exchange_id]
            try:
                await exchange.close()
                logging.info(f"{exchange_id} closed successfully.")
            except Exception as e:
                logging.error(f"Error closing {exchange_id}: {e}")

        tasks = [
            close_exchange(exchange_id) for exchange_id in self.exchange_list.keys()
        ]
        await asyncio.gather(*tasks)

    def _has_required_features(self, exchange_class):
        return (
            exchange_class.has["watchTrades"]
            and exchange_class.has["watchOrderBook"]
            and exchange_class.has["fetchOHLCV"]
        )

    def _get_credentials(self, exchange_id: str) -> Optional[Dict[str, str]]:
        """
        Retrieve API credentials for a given exchange from environment variables.
        """
        prefix = exchange_id.upper()
        api_key = os.getenv(f"{prefix}_API_KEY")
        secret = os.getenv(f"{prefix}_SECRET")
        password = os.getenv(f"{prefix}_PASSWORD")

        if api_key and secret:
            return {"apiKey": api_key, "secret": secret, "password": password}
        return {}
