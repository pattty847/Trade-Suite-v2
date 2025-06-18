import asyncio
import os
import logging
import pandas as pd
from typing import Tuple


class CacheStore:
    """Simple helper for loading and saving OHLCV CSV caches."""

    def __init__(self, cache_dir: str = "data/cache") -> None:
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    async def load_cache(self, path: str, key: str) -> Tuple[pd.DataFrame, int | None, int | None, bool]:
        existing_df = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
        first_cached_timestamp = None
        last_cached_timestamp = None
        data_loaded_from_cache = False

        if os.path.exists(path):
            logging.debug(f"Cache found: {path}")
            try:
                cached_df = await asyncio.to_thread(pd.read_csv, path, dtype={"dates": "Int64"})
                if not cached_df.empty and "dates" in cached_df.columns and not cached_df["dates"].isnull().all():
                    cached_df = cached_df.sort_values(by="dates").reset_index(drop=True)
                    existing_df = cached_df
                    data_loaded_from_cache = True
                    first_cached_timestamp = existing_df["dates"].iloc[0]
                    last_cached_timestamp = existing_df["dates"].iloc[-1]
                    logging.debug(
                        f"Cache for {key}: First ts: {first_cached_timestamp}, Last ts: {last_cached_timestamp}, Rows: {len(existing_df)}"
                    )
                else:
                    logging.debug(
                        f"Cache file {path} is empty, malformed, or 'dates' column is missing/empty. Will fetch fresh data."
                    )
            except pd.errors.EmptyDataError:
                logging.debug(f"Cache file {path} is empty. Will fetch fresh data.")
            except Exception as e:
                logging.error(f"Error loading cache {path}: {e}. Will attempt to fetch fresh data.")
        return existing_df, first_cached_timestamp, last_cached_timestamp, data_loaded_from_cache

    async def save_cache(self, df: pd.DataFrame, path: str, key: str, exchange_id: str, symbol: str, timeframe: str) -> None:
        if not df.empty:
            directory = os.path.dirname(path)
            os.makedirs(directory, exist_ok=True)

            df_to_save = df.copy()
            df_to_save["exchange"] = exchange_id
            df_to_save["symbol"] = symbol
            df_to_save["timeframe"] = timeframe

            desired_columns = [
                "dates",
                "opens",
                "highs",
                "lows",
                "closes",
                "volumes",
                "exchange",
                "symbol",
                "timeframe",
            ]
            columns_to_save = [col for col in desired_columns if col in df_to_save.columns]

            await asyncio.to_thread(df_to_save[columns_to_save].to_csv, path, index=False)
            logging.debug(f"Saved data for {key} to {path} with metadata columns. Rows: {len(df_to_save)}")
        else:
            logging.info(f"No data to save for {key} (DataFrame is empty). CSV not created/updated at {path}.")
