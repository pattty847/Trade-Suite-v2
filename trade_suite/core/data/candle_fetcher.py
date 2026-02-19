import asyncio
import logging
from typing import Dict, List, Tuple, Optional
import pandas as pd
import ccxt

from .cache_store import CacheStore
from .influx import InfluxDB


class CandleFetcher:
    """Handle OHLCV fetching and caching logic."""

    def __init__(self, cache_store: CacheStore, influx: InfluxDB) -> None:
        self.cache_store = cache_store
        self.influx = influx
        self.exchange_list: Dict[str, ccxt.Exchange] = {}
        self.exchange_semaphores: Dict[str, asyncio.Semaphore] = {}

    def set_exchange_list(self, exchange_list: Dict[str, ccxt.Exchange]) -> None:
        self.exchange_list = exchange_list

    async def fetch_candles(
        self,
        exchanges: List[str],
        symbols: List[str],
        since: str,
        timeframes: List[str],
        write_to_db: bool = False,
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        all_candles: Dict[str, Dict[str, pd.DataFrame]] = {}
        tasks = []
        for exchange in exchanges:
            if exchange in self.exchange_list:
                exchange_class = self.exchange_list[exchange]
                if exchange_class.id not in self.exchange_semaphores:
                    self.exchange_semaphores[exchange_class.id] = asyncio.Semaphore(5)
                    logging.debug(f"Initialized semaphore for {exchange_class.id} with concurrency 5.")

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

        if write_to_db:
            try:
                await self.influx.write_candles(all_candles)
            except Exception as e:
                logging.error(f"Error writing to DB: {e}")

        return all_candles

    async def _prepend_historic_candles(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: str,
        requested_since_timestamp: int,
        current_cache_start_timestamp: int,
        existing_df: pd.DataFrame,
        timeframe_duration_ms: int,
        cache_key: str,
    ) -> Tuple[pd.DataFrame, int | None]:
        prepend_fetch_until = current_cache_start_timestamp
        current_prepend_since = requested_since_timestamp
        prepended_ohlcv_list = []

        while current_prepend_since < prepend_fetch_until:
            logging.debug(
                f"Prepending {cache_key}: fetching from {current_prepend_since} up to {prepend_fetch_until}"
            )
            limit_for_prepend = exchange.options.get("fetchOHLCVLimit", 1000)

            ohlcv_prepend_batch = await self.retry_fetch_ohlcv(
                exchange, symbol, timeframe, current_prepend_since, limit_for_prepend
            )

            if ohlcv_prepend_batch:
                ohlcv_prepend_batch = [c for c in ohlcv_prepend_batch if c[0] < prepend_fetch_until]
                if not ohlcv_prepend_batch:
                    break
                prepended_ohlcv_list.extend(ohlcv_prepend_batch)
                last_ts_in_batch = ohlcv_prepend_batch[-1][0]
                current_prepend_since = last_ts_in_batch + timeframe_duration_ms
                if current_prepend_since >= prepend_fetch_until:
                    break
            else:
                break

        updated_df = existing_df
        new_first_cached_timestamp = current_cache_start_timestamp
        if prepended_ohlcv_list:
            prepend_df = pd.DataFrame(prepended_ohlcv_list, columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
            prepend_df["dates"] = prepend_df["dates"].astype("int64")
            updated_df = (
                pd.concat([prepend_df, existing_df])
                .drop_duplicates(subset=["dates"], keep="first")
                .sort_values(by="dates")
                .reset_index(drop=True)
            )
            logging.debug(
                f"Prepended {len(prepend_df)} new rows to {cache_key}. Total rows now: {len(updated_df)}."
            )
            if not updated_df.empty:
                new_first_cached_timestamp = updated_df["dates"].iloc[0]

        return updated_df, new_first_cached_timestamp

    async def _fetch_candle_data_after_timestamp(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: str,
        fetch_from_timestamp: int,
        fetch_until_timestamp: int,
        timeframe_duration_ms: int,
        is_initial_cache_fill: bool,
    ) -> List[List]:
        all_newly_fetched_ohlcv = []
        current_loop_fetch_timestamp = fetch_from_timestamp
        attempting_first_batch_for_initial_fill = is_initial_cache_fill

        while current_loop_fetch_timestamp < fetch_until_timestamp:
            logging.debug(
                f"Fetching {symbol} {timeframe} from {pd.to_datetime(current_loop_fetch_timestamp, unit='ms', errors='coerce')} for {exchange.id}"
            )
            ohlcv_batch = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, current_loop_fetch_timestamp)

            if ohlcv_batch:
                all_newly_fetched_ohlcv.extend(ohlcv_batch)
                current_loop_fetch_timestamp = ohlcv_batch[-1][0] + timeframe_duration_ms
                attempting_first_batch_for_initial_fill = False
            else:
                if attempting_first_batch_for_initial_fill:
                    logging.info(
                        f"Initial fetch for {exchange.id} {symbol} {timeframe} from {pd.to_datetime(fetch_from_timestamp, unit='ms', errors='coerce')} yielded no data. Attempting to find actual first candle."
                    )
                    first_ever_ohlcv_batch = await self.retry_fetch_ohlcv(exchange, symbol, timeframe, since=1, limit=1)
                    attempting_first_batch_for_initial_fill = False
                    if first_ever_ohlcv_batch:
                        actual_listing_timestamp = first_ever_ohlcv_batch[0][0]
                        logging.info(
                            f"Found first actual candle for {exchange.id} {symbol} {timeframe} at {pd.to_datetime(actual_listing_timestamp, unit='ms', errors='coerce')}"
                        )
                        if actual_listing_timestamp >= current_loop_fetch_timestamp:
                            current_loop_fetch_timestamp = actual_listing_timestamp
                            continue
                        else:
                            logging.info(
                                f"First candle for {exchange.id} {symbol} {timeframe} is at {pd.to_datetime(actual_listing_timestamp, unit='ms', errors='coerce')}, which is before our initial targeted fetch from {pd.to_datetime(fetch_from_timestamp, unit='ms', errors='coerce')}. No data found for the requested period. Stopping fetch for this symbol."
                            )
                            break
                    else:
                        logging.info(
                            f"Could not find any candles for {exchange.id} {symbol} {timeframe} even when checking from earliest time. Stopping fetch."
                        )
                        break
                else:
                    logging.debug(
                        f"No further data found for {exchange.id} {symbol} {timeframe} from {pd.to_datetime(current_loop_fetch_timestamp, unit='ms', errors='coerce')}. Ending fetch."
                    )
                    break

        return all_newly_fetched_ohlcv

    async def fetch_and_process_candles(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: str,
        since_timestamp: int,
        exchange_name: str,
        all_candles: Dict[str, Dict[str, pd.DataFrame]],
    ) -> None:
        logging.info(
            f"Fetching {symbol} {timeframe} from {pd.to_datetime(since_timestamp, unit='ms', errors='coerce')} for {exchange.id}"
        )
        key = self._generate_cache_key(exchange.id, symbol, timeframe)
        path = f"{self.cache_store.cache_dir}/{key}.csv"
        timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe)
        timeframe_duration_in_ms = timeframe_duration_in_seconds * 1000
        now = exchange.milliseconds()

        existing_df, first_cached_timestamp, last_cached_timestamp, data_loaded_from_cache = await self.cache_store.load_cache(path, key)

        if data_loaded_from_cache and first_cached_timestamp is not None and since_timestamp < first_cached_timestamp:
            logging.debug(
                f"Need to prepend data for {key}. Cache starts at {pd.to_datetime(first_cached_timestamp, unit='ms')}, requested since {pd.to_datetime(since_timestamp, unit='ms')}"
            )
            existing_df, first_cached_timestamp = await self._prepend_historic_candles(
                exchange,
                symbol,
                timeframe,
                since_timestamp,
                first_cached_timestamp,
                existing_df,
                timeframe_duration_in_ms,
                key,
            )

        if data_loaded_from_cache and last_cached_timestamp is not None:
            fetch_from_ts_for_new_data = last_cached_timestamp + timeframe_duration_in_ms
        else:
            fetch_from_ts_for_new_data = since_timestamp

        is_initial_cache_fill_for_fetch = not data_loaded_from_cache

        all_newly_fetched_ohlcv = await self._fetch_candle_data_after_timestamp(
            exchange,
            symbol,
            timeframe,
            fetch_from_ts_for_new_data,
            now,
            timeframe_duration_in_ms,
            is_initial_cache_fill_for_fetch,
        )

        if all_newly_fetched_ohlcv:
            new_data_df = pd.DataFrame(
                all_newly_fetched_ohlcv,
                columns=["dates", "opens", "highs", "lows", "closes", "volumes"],
            )
            new_data_df["dates"] = new_data_df["dates"].astype("int64")
            if not new_data_df.empty:
                new_data_df["exchange"] = exchange.id
                new_data_df["symbol"] = symbol
                new_data_df["timeframe"] = timeframe
            if existing_df.empty:
                combined_df = new_data_df
            else:
                combined_df = pd.concat([existing_df, new_data_df])
            existing_df = (
                combined_df.drop_duplicates(subset=["dates"], keep="last")
                .sort_values(by="dates")
                .reset_index(drop=True)
            )
            logging.info(
                f"Fetched/updated {len(new_data_df)} new rows for {key}. Total rows now: {len(existing_df)}."
            )

        if not existing_df.empty:
            await self.cache_store.save_cache(existing_df, path, key, exchange.id, symbol, timeframe)
            all_candles[exchange_name][key] = existing_df.copy()
        else:
            logging.info(
                f"No data fetched or found in cache for {exchange.id} {symbol} {timeframe}. CSV not created/updated at {path}."
            )
            if exchange_name not in all_candles:
                all_candles[exchange_name] = {}
            all_candles[exchange_name][key] = pd.DataFrame()

    async def retry_fetch_ohlcv(
        self, exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, limit: Optional[int] = None
    ) -> List[List]:
        max_retries = 3
        num_retries = 0
        if exchange.id not in self.exchange_semaphores:
            logging.warning(
                f"Semaphore for {exchange.id} not pre-initialized by fetch_candles. Creating with default concurrency 5."
            )
            self.exchange_semaphores[exchange.id] = asyncio.Semaphore(5)

        semaphore = self.exchange_semaphores[exchange.id]

        while num_retries < max_retries:
            async with semaphore:
                try:
                    logging.debug(
                        f"Attempting to fetch OHLCV for {symbol} {timeframe} on {exchange.id} since {pd.to_datetime(since, unit='ms', errors='coerce')} with limit {limit if limit is not None else 'default'}"
                    )
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, int(since), limit=limit)
                    logging.debug(
                        f"Fetched {len(ohlcv)} candles for {symbol} {timeframe} since {pd.to_datetime(since, unit='ms', errors='coerce')}" + (f" with limit {limit}" if limit is not None else "") + f" on {exchange.id}."
                    )
                    return ohlcv
                except ccxt.RateLimitExceeded as e:
                    num_retries += 1
                    logging.warning(
                        f"Rate limit exceeded for {symbol} on {exchange.id}. Attempt {num_retries}/{max_retries}. Retrying after delay... Error: {e}"
                    )
                    if num_retries >= max_retries:
                        logging.error(
                            f"Failed to fetch {timeframe} {symbol} OHLCV on {exchange.id} due to rate limiting after {max_retries} attempts from {since}."
                        )
                        return []
                    await asyncio.sleep(exchange.rateLimit / 1000 * (2 ** num_retries))
                except ccxt.NetworkError as e:
                    num_retries += 1
                    logging.warning(
                        f"Network error for {symbol} on {exchange.id}. Attempt {num_retries}/{max_retries}. Error: {e}"
                    )
                    if num_retries >= max_retries:
                        logging.error(
                            f"Failed to fetch {timeframe} {symbol} OHLCV on {exchange.id} due to network issues after {max_retries} attempts from {since}."
                        )
                        return []
                    await asyncio.sleep(1 * (2 ** num_retries))
                except Exception as e:
                    num_retries += 1
                    logging.error(
                        f"Error fetching {symbol} on {exchange.id}. Attempt {num_retries}/{max_retries}. Error: {type(e).__name__} - {e}"
                    )
                    if num_retries >= max_retries:
                        logging.error(
                            f"Failed to fetch {timeframe} {symbol} OHLCV on {exchange.id} after {max_retries} attempts from {since} due to {type(e).__name__}."
                        )
                        return []
        return []

    def _generate_cache_key(self, exchange_id: str, symbol: str, timeframe: str) -> str:
        safe_symbol = symbol.replace("/", "-")
        key = f"{exchange_id}_{safe_symbol}_{timeframe}"
        logging.debug(f"Generated cache key: {key}")
        return key

