import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import ccxt
import ccxt.pro as ccxtpro


class CCXTInterface:
    def __init__(self, exchanges: List[str], force_public: bool = False):
        self.target_exchanges = exchanges
        self.exchange_list: Dict[str, ccxtpro.Exchange] = {}
        self.failed_exchanges: Dict[str, str] = {}
        self.force_public = force_public

    async def _create_and_load_exchange(self, exchange_id: str) -> Optional[ccxtpro.Exchange]:
        """
        Internal method to create, load markets, and check features for a single exchange.
        Updates self.failed_exchanges internally if loading fails.
        """
        credentials = self._get_credentials(exchange_id)
        exchange_class: Optional[ccxtpro.Exchange] = None

        try:
            if credentials:
                logging.debug(f"Initializing {exchange_id} with provided credentials config (may be empty for public).")
            # else branch not strictly needed due to _get_credentials behavior

            config = {**credentials, "enableRateLimit": True}
            exchange_class = getattr(ccxtpro, exchange_id)(config)
            logging.debug(f"Attempting to load markets for {exchange_id}...")
            await exchange_class.load_markets()
            logging.debug(f"Markets loaded for {exchange_id}.")

            required_features = ["watchTrades", "watchOrderBook", "fetchOHLCV"] # Could be configurable
            has_all_features = True
            for feature in required_features:
                if not exchange_class.has.get(feature): # Use .get() for safety
                    has_all_features = False
                    reason = f"{exchange_id} does not support required feature: {feature}."
                    logging.error(reason)
                    self.failed_exchanges[exchange_id] = reason
                    if exchange_id in self.exchange_list: # Clean up if it was somehow partially added
                        del self.exchange_list[exchange_id]
                    return None # Stop if a feature is missing
            
            if has_all_features:
                return exchange_class # Successfully loaded and feature complete
            else: # Should be caught by the loop above, but as a safeguard
                return None

        except (ccxt.NetworkError, ccxt.ExchangeError, Exception) as e:
            reason = f"Error during {exchange_id} initialization or market loading: {type(e).__name__} - {e}"
            logging.error(reason, exc_info=True)
            self.failed_exchanges[exchange_id] = str(e) # Store simplified error for dict
            if exchange_id in self.exchange_list: # Clean up
                del self.exchange_list[exchange_id]
            if exchange_class and hasattr(exchange_class, 'close'): # Attempt to close if partially initialized
                try:
                    await exchange_class.close()
                    logging.debug(f"Closed partially initialized exchange {exchange_id} after error.")
                except Exception as close_err:
                    logging.error(f"Error closing partially initialized exchange {exchange_id}: {close_err}", exc_info=True)
            return None

    async def load_exchange(self, exchange_id: str) -> Optional[ccxtpro.Exchange]:
        """
        Loads a single exchange by its ID.
        Returns the exchange instance if successful, None otherwise.
        Updates self.exchange_list and self.failed_exchanges.
        """
        if exchange_id in self.exchange_list:
            logging.debug(f"{exchange_id} is already loaded and available.")
            return self.exchange_list[exchange_id]
        
        # If it previously failed, log it but allow a retry by proceeding.
        # The _create_and_load_exchange will update failed_exchanges if it fails again.
        if exchange_id in self.failed_exchanges:
            logging.warning(f"{exchange_id} previously failed to load (Reason: {self.failed_exchanges[exchange_id]}). Retrying.")
            # No direct return here, allow retry.

        logging.info(f"Attempting to load exchange: {exchange_id}...")
        exchange_instance = await self._create_and_load_exchange(exchange_id)

        if exchange_instance:
            self.exchange_list[exchange_id] = exchange_instance
            logging.info(f"{exchange_id.capitalize()} has been initialized successfully.")
            # If it was previously marked as failed, clear that status
            if exchange_id in self.failed_exchanges:
                del self.failed_exchanges[exchange_id]
            return exchange_instance
        else:
            # _create_and_load_exchange already logs the error and updates self.failed_exchanges
            logging.warning(f"Failed to load exchange: {exchange_id}. See previous errors for details.")
            return None

    async def load_exchanges(self, exchanges: List[str] = None):
        """
        Initializes a list of exchanges. If no list is passed,
        it initializes all exchanges specified in self.target_exchanges.
        Updates self.exchange_list and self.failed_exchanges.
        """
        exchanges_to_load = exchanges if exchanges is not None else self.target_exchanges
        if not exchanges_to_load:
            logging.warning("No exchanges specified to load in load_exchanges.")
            return

        logging.info(f"Starting to load specified exchanges: {exchanges_to_load}")
        
        # Load them sequentially for clearer logs, or concurrently with asyncio.gather
        # For now, sequential:
        for eid in exchanges_to_load:
            await self.load_exchange(eid)

        successful_loads = list(self.exchange_list.keys())
        failed_loads_details = self.failed_exchanges

        logging.info(f"Exchange loading process complete.")
        logging.info(f"Successfully loaded exchanges: {successful_loads if successful_loads else 'None'}")
        if failed_loads_details:
            logging.warning(f"Failed to load exchanges: {failed_loads_details}")
        else:
            logging.info("All specified exchanges attempted for loading reported no persistent failures.")


    async def close_all_exchanges(self):
        """
        Closes all successfully loaded exchanges in self.exchange_list.
        """
        if not self.exchange_list:
            logging.debug("No exchanges in exchange_list to close.")
            return

        logging.info(f"Closing connections for {len(self.exchange_list)} exchanges...")
        tasks = []
        for exchange_id, exchange_instance in self.exchange_list.items():
            if hasattr(exchange_instance, 'close'):
                async def close_task(eid, ex_inst):
                    try:
                        await ex_inst.close()
                        logging.info(f"{eid} closed successfully.")
                    except Exception as e:
                        logging.error(f"Error closing {eid}: {e}", exc_info=True)
                tasks.append(close_task(exchange_id, exchange_instance))
            else:
                logging.warning(f"Exchange {exchange_id} does not have a close method.")
        
        await asyncio.gather(*tasks, return_exceptions=True) # Capture errors from close tasks
        logging.info("Finished closing exchange connections.")

    def _get_credentials(self, exchange_id: str) -> Dict[str, str]:
        """
        Retrieve API credentials for a given exchange from environment variables.
        Returns an empty dict if force_public is True or no valid credentials are found.
        """
        if self.force_public:
            logging.info(f"force_public is True for {exchange_id}, initializing without authentication credentials.")
            return {}

        prefix = exchange_id.upper()
        api_key = os.getenv(f"{prefix}_API_KEY")
        secret = os.getenv(f"{prefix}_SECRET")
        password = os.getenv(f"{prefix}_PASSWORD") # Common for some exchanges

        creds = {}
        if api_key and secret: # Basic check
            # Avoid logging actual credentials
            logging.debug(f"Credentials (API Key) found for {exchange_id}.")
            # Check against common placeholder values - can be expanded
            if api_key.lower() == "your_api_key_here" or secret.lower() == "your_secret_here":
                logging.warning(f"Placeholder API credentials detected for {exchange_id}. Treating as no credentials.")
                return {}
            
            creds['apiKey'] = api_key
            creds['secret'] = secret
            if password:
                logging.debug(f"Password found for {exchange_id}.")
                creds['password'] = password
            return creds
        
        logging.info(f"No valid API key/secret pair found for {exchange_id} in environment variables. Initializing without specific authentication credentials.")
        return {}

    # _has_required_features is effectively integrated into _create_and_load_exchange now.
    # If it's needed elsewhere or for more complex logic, it can be kept/reinstated.