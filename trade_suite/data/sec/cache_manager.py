import os
import json
import logging
import glob
from datetime import datetime
from typing import Optional, Dict, List, Any

class SecCacheManager:
    """
    Manages caching of SEC data to the local filesystem to reduce redundant API calls.

    This class handles the storage and retrieval of various types of SEC data
    (like company submissions, filing lists, company facts, CIK mappings) in a
    structured directory layout within a specified base cache directory.

    Key responsibilities:
    - Organizing cached data into subdirectories based on data type.
    - Generating timestamped filenames for ticker-specific data to manage versions.
    - Providing methods to save data (as JSON) to appropriate cache files.
    - Providing methods to load the most recent and relevant cached data.
    - Implementing basic freshness checks (e.g., checking if a cache file is from today).
    - Handling file I/O and JSON serialization/deserialization.

    It is instantiated by `SECDataFetcher` and used internally to check for cached
    data before making live API requests.
    """

    # Define cache subdirectories
    SUBDIRS = {
        "mappings": "mappings",
        "submissions": "submissions",
        "forms": "forms",
        "facts": "facts",
        "reports": "reports" # Kept for potential future use, even if deprecated
    }

    def __init__(self, cache_dir: str = "data/edgar"):
        """
        Initializes the SEC Cache Manager.

        Creates the base cache directory and all necessary subdirectories if they
        do not already exist.

        Args:
            cache_dir (str, optional): The root directory path where all SEC cache
                files will be stored. Defaults to \"data/edgar\" relative to the
                project root.
        """
        self.cache_dir = cache_dir
        self._ensure_directories()

    def _ensure_directories(self):
        """
        Internal helper to create the base cache directory and all defined subdirectories.

        This is called during initialization to ensure the cache structure is ready.
        Uses `os.makedirs` with `exist_ok=True` to avoid errors if directories already exist.
        """
        logging.debug(f"Ensuring cache directory exists: {self.cache_dir}")
        os.makedirs(self.cache_dir, exist_ok=True)
        for subdir in self.SUBDIRS.values():
            path = os.path.join(self.cache_dir, subdir)
            logging.debug(f"Ensuring cache subdirectory exists: {path}")
            os.makedirs(path, exist_ok=True)

    def _get_cache_path(self, data_type: str, ticker: Optional[str] = None, **kwargs) -> str:
        """
        Constructs the full path for a cache file based on data type and parameters.

        This centralizes the logic for naming and locating cache files within the
        structured directory layout.

        Args:
            data_type (str): The category of data being cached (e.g., 'submissions',
                'forms', 'facts', 'mappings', 'company_info'). Must be a key in `SUBDIRS`.
            ticker (Optional[str], optional): The stock ticker symbol. Required for most
                `data_type` values (except 'mappings'). Defaults to None.
            **kwargs: Additional keyword arguments used for specific data types:
                - map_type (str): Used when `data_type` is 'mappings' (e.g., 'ticker_cik').
                - form_type (str): Required when `data_type` is 'forms'.

        Returns:
            str: The absolute or relative path to the intended cache file.

        Raises:
            ValueError: If `data_type` is invalid, or if `ticker` or `form_type`
                are required but not provided.
        """
        subdir = self.SUBDIRS.get(data_type)
        if not subdir:
            raise ValueError(f"Invalid data_type for caching: {data_type}")

        # --- CIK Mapping --- 
        if data_type == "mappings" and kwargs.get("map_type") == "ticker_cik":
             return os.path.join(self.cache_dir, subdir, "ticker_cik_map.json")

        # --- Ticker-specific data --- 
        if not ticker:
            raise ValueError(f"Ticker is required for data_type: {data_type}")
        ticker_upper = ticker.upper()

        timestamp = datetime.now().strftime("%Y%m%d") # Daily timestamp by default

        if data_type == "submissions":
            filename = f"{ticker_upper}_submissions_{timestamp}.json"
        elif data_type == "forms":
            form_type = kwargs.get("form_type")
            if not form_type: raise ValueError("form_type is required for 'forms' data_type")
            filename = f"{ticker_upper}_{form_type}_{timestamp}.json"
        elif data_type == "facts":
            # Facts can update more often, add time to timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticker_upper}_facts_{timestamp}.json"
        elif data_type == "company_info": # Using submissions subdir for info for now
            # Treat company info like submissions (daily cache)
             subdir = self.SUBDIRS["submissions"]
             filename = f"{ticker_upper}_info_{timestamp}.json"
        else:
            # Default pattern if needed, though specific types are preferred
            filename = f"{ticker_upper}_{data_type}_{timestamp}.json"

        return os.path.join(self.cache_dir, subdir, filename)

    def _find_latest_cache_file(self, data_type: str, ticker: str, **kwargs) -> Optional[str]:
        """
        Finds the most recently modified cache file matching a pattern for a ticker.

        Uses `glob` to find files matching the naming convention for the specified
        `data_type` and `ticker` within the appropriate subdirectory. It then sorts
        these files by modification time (most recent first).

        Args:
            data_type (str): The category of data (e.g., 'submissions', 'forms', 'facts').
            ticker (str): The stock ticker symbol.
            **kwargs: Additional keyword arguments used for specific data types:
                - form_type (str): Required when `data_type` is 'forms'.

        Returns:
            Optional[str]: The path to the most recent cache file if found, otherwise None.
        """
        subdir = self.SUBDIRS.get(data_type)
        if not subdir: return None
        ticker_upper = ticker.upper()

        if data_type == "submissions":
            pattern = f"{ticker_upper}_submissions_*.json"
        elif data_type == "forms":
            form_type = kwargs.get("form_type")
            if not form_type: return None
            pattern = f"{ticker_upper}_{form_type}_*.json"
        elif data_type == "facts":
            pattern = f"{ticker_upper}_facts_*.json"
        elif data_type == "company_info": # Using submissions subdir for info
            subdir = self.SUBDIRS["submissions"]
            pattern = f"{ticker_upper}_info_*.json"
        else:
            return None # Pattern not defined for this type

        search_path = os.path.join(self.cache_dir, subdir, pattern)
        try:
            cache_files = sorted(glob.glob(search_path), key=os.path.getmtime, reverse=True)
            if cache_files:
                logging.debug(f"Found latest cache file for {ticker} ({data_type}): {cache_files[0]}")
                return cache_files[0]
            else:
                logging.debug(f"No cache files found for pattern: {search_path}")
                return None
        except Exception as e:
            logging.warning(f"Error searching for cache files ({search_path}): {e}")
            return None

    def _is_cache_fresh(self, cache_file: str, data_type: str) -> bool:
        """
        Determines if a given cache file is considered fresh based on its type and timestamp.

        The current logic considers cache files for 'submissions', 'forms', and
        'company_info' fresh if their filename contains today's date (YYYYMMDD format).
        Other types (like 'facts' which include time in the timestamp, or 'mappings')
        are currently considered fresh whenever found by `_find_latest_cache_file`.
        This logic could be expanded for more sophisticated TTL strategies.

        Args:
            cache_file (str): The full path to the cache file.
            data_type (str): The category of data the file represents.

        Returns:
            bool: True if the cache file is considered fresh, False otherwise.
        """
        # Simple check: if cache is from today for submissions/forms/info
        if data_type in ["submissions", "forms", "company_info"]:
            today = datetime.now().strftime("%Y%m%d")
            is_fresh = today in os.path.basename(cache_file)
            logging.debug(f"Checking freshness for {cache_file} ({data_type}): {'Fresh' if is_fresh else 'Stale'}")
            return is_fresh
        return True # Assume other types are always fresh if found by _find_latest

    def _read_cache_file(self, file_path: str) -> Optional[Any]:
        """
        Reads and parses JSON content from a specified cache file.

        Handles file opening, reading, and JSON decoding. Logs warnings and returns
        None if the file doesn't exist, is unreadable, or contains invalid JSON.

        Args:
            file_path (str): The full path to the JSON cache file.

        Returns:
            Optional[Any]: The parsed data from the JSON file (usually dict or list),
                or None if reading or parsing fails.
        """
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logging.debug(f"Successfully read cache file: {file_path}")
                return data
        except json.JSONDecodeError as e:
            logging.warning(f"JSON decode error reading cache file {file_path}: {e}")
            return None
        except Exception as e:
            logging.warning(f"Error reading cache file {file_path}: {e}")
            return None

    def _write_cache_file(self, file_path: str, data: Any) -> bool:
        """
        Writes Python data structures to a specified file path as JSON.

        Ensures the target directory exists, then opens the file and dumps the
        provided data using `json.dump` with indentation for readability.
        Logs errors if writing fails.

        Args:
            file_path (str): The full path to the target cache file.
            data (Any): The Python object (e.g., dict, list) to serialize and save.
                Must be JSON serializable.

        Returns:
            bool: True if the file was written successfully, False otherwise.
        """
        try:
            # Ensure the directory exists before writing
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Successfully wrote cache file: {file_path}")
            return True
        except Exception as e:
            logging.error(f"Error writing cache file {file_path}: {e}")
            return False

    # --- Public Caching Methods --- 

    # CIK Mapping Specific
    async def load_cik(self, ticker: str) -> Optional[str]:
        """
        Loads the CIK for a specific ticker from the cached Ticker-CIK map.

        Reads the central `ticker_cik_map.json` file and looks up the CIK
        for the given ticker (case-insensitive).

        Args:
            ticker (str): The stock ticker symbol.

        Returns:
            Optional[str]: The 10-digit CIK string if found in the cache, otherwise None.
        """
        map_file = self._get_cache_path("mappings", map_type="ticker_cik")
        cik_map = self._read_cache_file(map_file)
        if isinstance(cik_map, dict):
            cik = cik_map.get(ticker.upper())
            if cik:
                 logging.debug(f"CIK found in cache for {ticker}: {cik}")
                 return cik
        logging.debug(f"CIK not found in cache for {ticker}")
        return None

    async def save_cik_map(self, cik_map: Dict[str, str]) -> None:
        """
        Saves the entire Ticker-CIK mapping dictionary to the cache file.

        Overwrites the existing `ticker_cik_map.json` with the provided dictionary.
        This is typically called after fetching the fresh map from the SEC.

        Args:
            cik_map (Dict[str, str]): A dictionary mapping uppercase ticker symbols
                to their 10-digit CIK strings.
        """
        map_file = self._get_cache_path("mappings", map_type="ticker_cik")
        success = self._write_cache_file(map_file, cik_map)
        if not success:
             logging.error("Failed to save Ticker-CIK map to cache.")

    # Generic Load/Save for Ticker-Specific Data
    async def load_data(self, ticker: str, data_type: str, **kwargs) -> Optional[Any]:
        """
        Loads the most recent, fresh cached data for a given ticker and data type.

        This is the primary public method for retrieving cached data. It uses internal
        helpers to find the latest relevant cache file (`_find_latest_cache_file`)
        and checks if it's considered fresh (`_is_cache_fresh`). If both conditions
        are met, it reads and returns the data (`_read_cache_file`).

        Args:
            ticker (str): The stock ticker symbol (case-insensitive).
            data_type (str): The category of data to load (e.g., 'submissions', 'forms',
                'facts', 'company_info').
            **kwargs: Additional parameters needed for specific data types, passed down
                to helper methods (e.g., `form_type` for 'forms').

        Returns:
            Optional[Any]: The cached data (typically dict or list) if found and deemed
                fresh, otherwise None.
        """
        latest_file = self._find_latest_cache_file(data_type, ticker, **kwargs)
        if latest_file and self._is_cache_fresh(latest_file, data_type):
            return self._read_cache_file(latest_file)
        else:
            if latest_file:
                 logging.debug(f"Cache file found ({latest_file}) but considered stale.")
            else:
                 logging.debug(f"No cache file found for {ticker} ({data_type} {' '.join(f'{k}={v}' for k,v in kwargs.items())})")
        return None

    async def save_data(self, ticker: str, data_type: str, data: Any, **kwargs) -> None:
        """
        Saves data to a new, timestamped cache file for a specific ticker and data type.

        This is the primary public method for storing fetched data. It determines the
        correct filename and path using `_get_cache_path` (which includes a timestamp)
        and writes the data using `_write_cache_file`.

        Args:
            ticker (str): The stock ticker symbol (used in the filename).
            data_type (str): The category of data being saved (e.g., 'submissions',
                'forms', 'facts', 'company_info').
            data (Any): The Python object (e.g., dict, list) to be saved as JSON.
            **kwargs: Additional parameters needed for specific data types, passed down
                to helper methods (e.g., `form_type` for 'forms'). (Note: 'cik' is ignored here).
        """
        # CIK might be passed in kwargs but isn't used for path determination here
        kwargs.pop('cik', None)

        cache_file = self._get_cache_path(data_type, ticker, **kwargs)
        success = self._write_cache_file(cache_file, data)
        if not success:
            logging.error(f"Failed to save {data_type} data for {ticker} to cache.")

    # Specific Load/Save methods (kept for compatibility during refactor, but delegate)
    async def _load_company_info_from_cache(self, ticker: str) -> Optional[Dict]:
        """DEPRECATED internal helper. Use `load_data` directly."""
        return await self.load_data(ticker, "company_info")

    async def _save_company_info_to_cache(self, ticker: str, cik: str, data: Dict) -> None:
        """DEPRECATED internal helper. Use `save_data` directly."""
        await self.save_data(ticker, "company_info", data, cik=cik)

    async def _load_submissions_from_cache(self, ticker: str) -> Optional[Dict]:
        """DEPRECATED internal helper. Use `load_data` directly."""
        return await self.load_data(ticker, "submissions")

    async def _save_submissions_to_cache(self, ticker: str, cik: str, data: Dict) -> None:
        """DEPRECATED internal helper. Use `save_data` directly."""
        await self.save_data(ticker, "submissions", data, cik=cik)

    async def _load_filings_from_cache(self, ticker: str, form_type: str) -> List[Dict]:
        """DEPRECATED internal helper. Use `load_data` directly."""
        result = await self.load_data(ticker, "forms", form_type=form_type)
        return result if isinstance(result, list) else [] # Ensure list return type

    async def _save_filings_to_cache(self, ticker: str, form_type: str, data: List[Dict]) -> None:
        """DEPRECATED internal helper. Use `save_data` directly."""
        await self.save_data(ticker, "forms", data, form_type=form_type)

    async def _load_company_facts_from_cache(self, ticker: str) -> Optional[Dict]:
        """DEPRECATED internal helper. Use `load_data` directly."""
        return await self.load_data(ticker, "facts")

    async def _save_company_facts_to_cache(self, ticker: str, cik: str, data: Dict) -> None:
        """DEPRECATED internal helper. Use `save_data` directly."""
        await self.save_data(ticker, "facts", data, cik=cik)