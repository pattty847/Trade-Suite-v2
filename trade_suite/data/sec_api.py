import requests
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, Tuple
import logging
import time
import glob
import xml.etree.ElementTree as ET
import asyncio
import aiohttp
import re

from dotenv import load_dotenv

load_dotenv()
class SECDataFetcher:
    """
    A comprehensive asynchronous library for fetching and processing data from SEC EDGAR APIs.
    
    Handles interactions with various SEC endpoints, including submissions, company facts,
    and fetching specific filing documents. Implements caching, rate limiting,
    and parsing capabilities (e.g., for Form 4 XML).
    
    Attributes:
        user_agent (str): The User-Agent string used for SEC requests.
        cache_dir (str): The directory path for storing cached API responses.
        headers (Dict[str, str]): Default headers for API requests.
        request_interval (float): Minimum time interval (seconds) between requests.
        last_request_time (float): Timestamp of the last request made.
        _session (Optional[aiohttp.ClientSession]): The asynchronous HTTP session.
    """
    
    # Base endpoints for SEC EDGAR APIs
    SUBMISSIONS_ENDPOINT = "https://data.sec.gov/submissions/CIK{cik}.json"
    COMPANY_FACTS_ENDPOINT = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    COMPANY_CONCEPT_ENDPOINT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
    
    # Map of form types to their descriptions
    FORM_TYPES = {
        "4": "Statement of changes in beneficial ownership (insider transactions)",
        "3": "Initial statement of beneficial ownership",
        "5": "Annual statement of beneficial ownership",
        "8-K": "Current report",
        "10-K": "Annual report",
        "10-Q": "Quarterly report",
        "13F": "Institutional investment manager holdings report",
        "SC 13G": "Beneficial ownership report",
        "SC 13D": "Beneficial ownership report (active)",
        "DEF 14A": "Definitive proxy statement",
    }
    
    # Transaction codes for Form 4 filings
    TRANSACTION_CODE_MAP = {
        'P': 'Purchase',
        'S': 'Sale',
        'A': 'Award',
        'D': 'Disposition (Gift/Other)',
        'F': 'Tax Withholding',
        'I': 'Discretionary Transaction',
        'M': 'Option Exercise',
        'C': 'Conversion',
        'W': 'Warrant Exercise',
        'G': 'Gift',
        'J': 'Other Acquisition/Disposition',
        'U': 'Tender of Shares',
        'X': 'Option Expiration',
        'Z': 'Trust Transaction',
    }
    
    # Define codes considered as 'Acquisition'/'Disposition'
    ACQUISITION_CODES = ['P', 'A', 'M', 'C', 'W', 'G', 'J', 'I']
    DISPOSITION_CODES = ['S', 'D', 'F', 'X', 'U', 'Z']

    # Define key metrics mapping for the financial summary required by the UI
    # Keys are snake_case matching the target flat dictionary output.
    # Values are the corresponding us-gaap or dei XBRL tags.
    # Includes only metrics directly needed for the final flat summary.
    KEY_FINANCIAL_SUMMARY_METRICS = {
        # Income Statement
        "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax", # US-GAAP
        "net_income": "NetIncomeLoss",                                 # US-GAAP
        "eps": "EarningsPerShareBasic",                                # US-GAAP (Using Basic EPS for UI)
        # Balance Sheet
        "assets": "Assets",                                           # US-GAAP
        "liabilities": "Liabilities",                                     # US-GAAP
        "equity": "StockholdersEquity",                                # US-GAAP
        # Cash Flow
        "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities", # US-GAAP
        "investing_cash_flow": "NetCashProvidedByUsedInInvestingActivities",# US-GAAP
        "financing_cash_flow": "NetCashProvidedByUsedInFinancingActivities",# US-GAAP
        # Other potentially useful (DEI)
        # "shares_outstanding": "EntityCommonStockSharesOutstanding" # DEI - Add if needed by UI
    }
    
    # Separate mapping for DEI tags if needed, can be merged or kept separate
    # KEY_DEI_METRICS = {
    #     "shares_outstanding": "EntityCommonStockSharesOutstanding"
    # }
    
    def __init__(self, user_agent: str = None, cache_dir: str = "data/edgar", 
                 rate_limit_sleep: float = 0.1):
        """
        Initialize the SECDataFetcher.
        
        Args:
            user_agent (str, optional): User-Agent string for SEC API requests.
                             Format: "Sample Company Name AdminContact@example.com".
                             Defaults to None, attempts to read from 'SEC_API_USER_AGENT' env var.
            cache_dir (str, optional): Directory for storing cached data. Defaults to "data/edgar".
            rate_limit_sleep (float, optional): Seconds to wait between API requests. Defaults to 0.1.
        """
        # Set up user agent
        self.user_agent = user_agent or os.environ.get('SEC_API_USER_AGENT')
        
        if self.user_agent:
            logging.info(f"SEC API User-Agent: {self.user_agent}")
        else:
            logging.warning("No SEC API User-Agent provided. Please set SEC_API_USER_AGENT environment variable.")
            logging.warning("Format should be: 'name (email)' e.g., 'Market Analysis Tool (user@example.com)'")
        
        # Set headers for API requests
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov"
        }
        
        # Set up rate limiting
        self.request_interval = rate_limit_sleep
        self.last_request_time = 0
        
        # Set up cache directory
        self.cache_dir = cache_dir
        self._ensure_directories()
        
        # Initialize aiohttp session - TO BE CREATED ASYNCHRONOUSLY if needed outside __init__
        # For simplicity, we create it here but it's not ideal for long-running apps
        # where the event loop might not be running yet.
        # Consider lazy initialization or passing a session.
        self._session: Optional[aiohttp.ClientSession] = None # Initialize later or pass in

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily initializes and returns the aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _ensure_directories(self):
        """Ensure all necessary directories exist."""
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, "submissions"), exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, "insider"), exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, "forms"), exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, "reports"), exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, "facts"), exist_ok=True)
    
    async def _test_api_access(self) -> bool:
        """Test if the SEC API is accessible with the provided user agent."""
        if not self.user_agent:
            logging.error("Cannot test API access: No User-Agent provided")
            return False
            
        try:
            # Test using Apple's CIK as an example (0000320193)
            test_url = self.SUBMISSIONS_ENDPOINT.format(cik="0000320193")
            logging.info(f"Testing SEC API connection to: {test_url}")
            
            response = await self._make_request(test_url)
            
            if response:
                logging.info("SEC API access test successful")
                return True
            else:
                logging.error(f"SEC API access test failed: No response")
                return False
                
        except Exception as e:
            logging.error(f"Error testing SEC API access: {str(e)}")
            return False
    
    async def _make_request(self, url: str, max_retries: int = 3, headers: Optional[Dict] = None, is_json: bool = True) -> Optional[Union[Dict, str]]:
        """
        Internal helper to make a rate-limited, retrying asynchronous HTTP GET request.
        
        Handles rate limiting (429 errors) with exponential backoff and basic error handling.
        Parses JSON response by default.
        
        Args:
            url (str): The URL to request.
            max_retries (int, optional): Maximum retry attempts. Defaults to 3.
            headers (Optional[Dict], optional): Headers to use for the request, overriding default headers.
                                              Defaults to None (uses self.headers).
            is_json (bool, optional): If True, attempts to parse the response as JSON.
                                     If False, returns the raw response text.
                                     Defaults to True.
            
        Returns:
            Optional[Union[Dict, str]]: The parsed JSON dictionary or raw text content,
                                       or None if the request fails after all retries.
        """
        # Implement simple rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.request_interval:
            sleep_time = self.request_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        session = await self._get_session()
        
        # Determine which headers to use
        request_headers = headers if headers is not None else self.headers
        if not request_headers.get('User-Agent'):
             logging.warning(f"User-Agent not found in request headers for {url}. Using default self.headers if available.")
             # Fallback explicitly if custom headers were provided but lacked User-Agent
             if headers is not None and not headers.get('User-Agent') and self.headers.get('User-Agent'):
                   request_headers = self.headers
             elif not self.headers.get('User-Agent'):
                  logging.error(f"CRITICAL: No User-Agent available in default or custom headers for {url}. Request likely to fail.")
                  # Assign empty dict if absolutely no User-Agent is set anywhere, though request will likely fail
                  request_headers = request_headers or {}

        for attempt in range(max_retries):
            try:
                self.last_request_time = time.time()
                # Use the determined headers
                async with session.get(url, headers=request_headers, timeout=10) as response:
                    # Handle rate limiting (429) with exponential backoff
                    if response.status == 429:
                        wait_time = (2 ** attempt) + 1  # 1, 3, 5 seconds
                        logging.warning(f"Rate limited by SEC API. Waiting {wait_time}s before retry {attempt+1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue # Retry the loop

                    # Check for other client/server errors
                    response.raise_for_status() # Raise exception for 4xx/5xx status codes

                    # Process successful response
                    if is_json:
                        # First get the text content
                        text_content = await response.text()
                        
                        # Try to parse as JSON regardless of content type
                        # SEC API often returns JSON with text/html content type
                        try:
                            # Check if it starts with { or [ (likely JSON)
                            if text_content.strip().startswith(('{', '[')):
                                return json.loads(text_content)
                            else:
                                logging.warning(f"Content doesn't appear to be JSON: {text_content[:100]}...")
                                return text_content
                        except json.JSONDecodeError as json_err:
                            logging.error(f"JSON decode error for {url}: {json_err}")
                            logging.warning(f"Returning raw text instead (first 100 chars): {text_content[:100]}...")
                            return text_content
                    else:
                        return await response.text() # Return raw text

            except asyncio.TimeoutError:
                 logging.warning(f"Timeout on attempt {attempt+1}/{max_retries} for {url}")
            except aiohttp.ClientResponseError as e:
                 logging.error(f"HTTP error {e.status} on attempt {attempt+1}/{max_retries} for {url}: {e.message}")
            except aiohttp.ClientError as e: # Catch other aiohttp client errors
                 logging.warning(f"Request error on attempt {attempt+1}/{max_retries}: {str(e)}")
            
            # Wait before retry
            await asyncio.sleep(1 * (attempt + 1))
        
        return None
    
    async def get_cik_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Retrieves the 10-digit CIK (Central Index Key) for a given stock ticker symbol.
        
        First attempts to load the CIK from a local cache (`ticker_cik_map.json`).
        If not found in cache, fetches the official SEC `company_tickers.json` mapping,
        updates the cache, and then attempts to retrieve the CIK again.
        
        Args:
            ticker (str): The stock ticker symbol (case-insensitive).
            
        Returns:
            Optional[str]: The 10-digit CIK string with leading zeros if found, otherwise None.
        """
        ticker = ticker.upper()
        
        # 1. Check local cache file
        cik = self._load_cik_from_cache(ticker)
        if cik:
            return cik
        
        # 2. If not in cache, fetch the official map, cache it, and retry
        logging.info(f"CIK for {ticker} not found in cache. Fetching official map...")
        success = await self._fetch_and_cache_cik_map()
        if success:
            cik = self._load_cik_from_cache(ticker) # Retry loading from cache
            if cik:
                return cik
        
        logging.error(f"Could not find or fetch CIK for {ticker}.")
        return None
    
    def _load_cik_from_cache(self, ticker: str) -> Optional[str]:
        """Loads a CIK from the `ticker_cik_map.json` cache file."""
        cache_file = os.path.join(self.cache_dir, "ticker_cik_map.json")
        
        if not os.path.exists(cache_file):
            return None
            
        try:
            with open(cache_file, 'r') as f:
                ticker_map = json.load(f)
                return ticker_map.get(ticker.upper())
        except Exception as e:
            logging.warning(f"Error loading CIK from cache for {ticker}: {str(e)}")
            return None
    
    def _save_cik_to_cache(self, ticker: str, cik: str) -> None:
        """Saves or updates a ticker-CIK mapping in the `ticker_cik_map.json` cache file."""
        cache_file = os.path.join(self.cache_dir, "ticker_cik_map.json")
        
        # Read existing mappings
        ticker_map = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    ticker_map = json.load(f)
            except Exception as e:
                logging.warning(f"Error reading ticker-CIK cache file: {str(e)}")
        
        # Update with new mapping
        ticker_map[ticker.upper()] = cik
        
        # Save updated mappings
        try:
            with open(cache_file, 'w') as f:
                json.dump(ticker_map, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving ticker-CIK mapping to cache: {str(e)}")
    
    async def _fetch_and_cache_cik_map(self) -> bool:
        """Fetches the official Ticker-CIK map from SEC and caches it."""
        url = "https://www.sec.gov/files/company_tickers.json"
        logging.info(f"Fetching Ticker-CIK map from {url}")
        try:
            # SEC serves this as application/json, use standard headers
            # Need to adjust host in headers if necessary
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov' # Host for this specific URL

            sec_map_data = await self._make_request(url, headers=temp_headers, is_json=True)
            if not sec_map_data:
                logging.error(f"Failed to fetch or parse Ticker-CIK map from {url}")
                return False

            # Process the map: { "0": { "cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc." }, ... }
            ticker_to_cik = {}
            for _index, company_info in sec_map_data.items():
                ticker = company_info.get('ticker')
                cik_int = company_info.get('cik_str')
                if ticker and cik_int:
                    # Format CIK to 10 digits with leading zeros
                    cik_str = str(cik_int).zfill(10)
                    ticker_to_cik[ticker.upper()] = cik_str

            # Save the processed map
            cache_file = os.path.join(self.cache_dir, "ticker_cik_map.json")
            try:
                with open(cache_file, 'w') as f:
                    json.dump(ticker_to_cik, f, indent=2)
                logging.info(f"Successfully fetched and cached Ticker-CIK map to {cache_file}")
                return True
            except IOError as e:
                logging.error(f"Error saving fetched Ticker-CIK map to cache: {str(e)}")
                return False

        except Exception as e:
            logging.error(f"Error during Ticker-CIK map fetch/processing: {e}", exc_info=True)
            return False
    
    async def get_company_info(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetches basic company information using the SEC submissions endpoint.
        
        This data includes name, CIK, SIC description, address, etc.
        Uses caching by default.
        
        Args:
            ticker (str): The stock ticker symbol.
            use_cache (bool, optional): Whether to use cached data if available and recent.
                                       Defaults to True.
            
        Returns:
            Optional[Dict]: A dictionary containing company information, or None if an error occurs.
        """
        ticker = ticker.upper()
        
        # Try to load from cache first if use_cache is True
        if use_cache:
            cache_data = self._load_company_info_from_cache(ticker)
            if cache_data:
                return cache_data
        
        # Convert ticker to CIK
        cik = await self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot get company info: No CIK found for {ticker}")
            return None
            
        # Get submissions data which includes company info
        submissions_url = self.SUBMISSIONS_ENDPOINT.format(cik=cik)
        
        try:
            response = await self._make_request(submissions_url, is_json=True)
            if response is None:
                logging.error(f"Failed to get company submission data for info lookup for {ticker} (CIK: {cik})")
                return None
            
            # Extract relevant company info
            company_info = {
                'ticker': ticker,
                'cik': cik,
                'name': response.get('name'),
                'sic': response.get('sic'),
                'sic_description': response.get('sicDescription'),
                'address': response.get('addresses', {}).get('mailing'),
                'phone': response.get('phone'),
                'exchange': response.get('exchanges'),
            }
            
            # Cache the company info data
            self._save_company_info_to_cache(ticker, cik, company_info)
            
            return company_info
            
        except Exception as e:
            logging.error(f"Error fetching company info for {ticker} (CIK: {cik}): {str(e)}")
            return None
    
    def _load_company_info_from_cache(self, ticker: str) -> Optional[Dict]:
        """Loads company info from the most recent cache file for the ticker."""
        # Find the most recent cache file for this ticker
        cache_pattern = os.path.join(self.cache_dir, "submissions", f"{ticker.upper()}_info_*.json")
        cache_files = sorted(glob.glob(cache_pattern), key=os.path.getmtime, reverse=True)
        
        if not cache_files:
            return None
            
        # Use the most recent cache file
        try:
            with open(cache_files[0], 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Error loading company info from cache for {ticker}: {str(e)}")
            return None
    
    def _save_company_info_to_cache(self, ticker: str, cik: str, data: Dict) -> None:
        """Save company info to a cache file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(self.cache_dir, "submissions", f"{ticker.upper()}_info_{timestamp}.json")
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Saved company info to cache: {cache_file}")
        except Exception as e:
            logging.error(f"Error saving company info to cache: {str(e)}")
    
    async def get_company_submissions(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetches the complete submissions data for a company from the SEC API.
        
        The submissions data contains details about all filings, including recent ones.
        Uses caching by default (checks for cache file from the current day).
        
        Args:
            ticker (str): The stock ticker symbol.
            use_cache (bool, optional): Whether to use cached data if available and recent.
                                       Defaults to True.
            
        Returns:
            Optional[Dict]: The complete submissions JSON data as a dictionary, or None if an error occurs.
        """
        ticker = ticker.upper()
        
        # Try to load from cache first if use_cache is True
        if use_cache:
            cache_data = self._load_submissions_from_cache(ticker)
            if cache_data:
                return cache_data
        
        # Convert ticker to CIK
        cik = await self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot get submissions: No CIK found for {ticker}")
            return None
            
        # Get submissions data
        submissions_url = self.SUBMISSIONS_ENDPOINT.format(cik=cik)
        
        try:
            response = await self._make_request(submissions_url, is_json=True)
            if response is None:
                logging.error(f"Failed to get submissions for {ticker} (CIK: {cik})")
                return None
            
            # Parse submissions data
            submissions_data = response
            
            # Cache the submissions data
            self._save_submissions_to_cache(ticker, cik, submissions_data)
            
            return submissions_data
            
        except Exception as e:
            logging.error(f"Error fetching submissions for {ticker} (CIK: {cik}): {str(e)}")
            return None
    
    def _load_submissions_from_cache(self, ticker: str) -> Optional[Dict]:
        """Load submissions data from cache file for a ticker."""
        # Find the most recent cache file for this ticker
        cache_pattern = os.path.join(self.cache_dir, "submissions", f"{ticker.upper()}_submissions_*.json")
        cache_files = sorted(glob.glob(cache_pattern), key=os.path.getmtime, reverse=True)
        
        if not cache_files:
            return None
            
        # Check if cache is from today (for freshness)
        today = datetime.now().strftime("%Y%m%d")
        if today not in cache_files[0]:
            return None  # Cache is not from today
            
        # Use the most recent cache file
        try:
            with open(cache_files[0], 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Error loading submissions from cache for {ticker}: {str(e)}")
            return None
    
    def _save_submissions_to_cache(self, ticker: str, cik: str, data: Dict) -> None:
        """Save submissions data to cache file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        # Ensure parent directory exists before saving
        cache_subdir = os.path.join(self.cache_dir, "submissions")
        os.makedirs(cache_subdir, exist_ok=True)
        cache_file = os.path.join(cache_subdir, f"{ticker.upper()}_submissions_{timestamp}.json")
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Saved submissions data to cache: {cache_file}")
        except Exception as e:
            logging.error(f"Error saving submissions data to cache: {str(e)}")

    async def get_filings_by_form(self, ticker: str, form_type: str, days_back: int = 90, 
                            use_cache: bool = True) -> List[Dict]:
        """
        Fetches a list of filings of a specific form type for a ticker within a given timeframe.
        
        Retrieves the company's submissions data first (using cache if enabled)
        and then filters the recent filings based on the specified `form_type` and `days_back`.
        Formats the results into a list of dictionaries suitable for display.
        Caches the filtered results for the specific form type and day.
        
        Args:
            ticker (str): Stock ticker symbol.
            form_type (str): SEC form type (e.g., "4", "8-K", "10-K").
            days_back (int, optional): Number of past days to include filings from. Defaults to 90.
            use_cache (bool, optional): Whether to use cached submissions and filtered filings data.
                                       Defaults to True.
            
        Returns:
            List[Dict]: A list of dictionaries, each representing a filing. Includes keys like
                        'accession_no', 'filing_date', 'form', 'report_date', 'url',
                        'primary_document'. Returns an empty list if no filings are found or an error occurs.
        """
        ticker = ticker.upper()
        
        # Try to load from cache first if use_cache is True
        if use_cache:
            cache_data = self._load_filings_from_cache(ticker, form_type)
            if cache_data:
                # Filter for the days_back parameter
                cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
                # Filter based on the new 'filing_date' key
                return [filing for filing in cache_data if filing.get('filing_date', '') >= cutoff_date]
        
        # Get submissions data, which includes CIK
        submissions = await self.get_company_submissions(ticker, use_cache=use_cache) # Use the cache setting consistently
        if not submissions:
            return []

        # Extract CIK needed for URL construction
        cik = submissions.get('cik')
        if not cik:
            logging.error(f"CIK not found in submissions data for {ticker}. Cannot construct URLs.")
            # Optionally, try getting CIK again, but submissions should ideally contain it
            cik = await self.get_cik_for_ticker(ticker)
            if not cik:
                 logging.error(f"Failed to get CIK for {ticker} separately. Returning empty list.")
                 return []
            
        # Process and filter for the specified form type
        filings = []
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        try:
            # The submissions endpoint has a 'filings' key containing filing data
            recent_filings = submissions.get('filings', {}).get('recent', {})
            
            if not recent_filings:
                logging.warning(f"No recent filings found for {ticker}")
                return []
                
            # Extract data lists safely
            form_list = recent_filings.get('form', [])
            filing_date_list = recent_filings.get('filingDate', [])
            accession_number_list = recent_filings.get('accessionNumber', [])
            report_date_list = recent_filings.get('reportDate', []) # Extract reportDate
            primary_document_list = recent_filings.get('primaryDocument', []) # Extract primaryDocument

            # Ensure all lists have the same length for safe iteration
            # Note: primaryDocument list might be shorter, handle index errors or check length
            min_len = min(len(form_list), len(filing_date_list), len(accession_number_list), len(report_date_list))

            # Filter for specified form type filings within the date range
            for i in range(min_len): # Iterate up to the minimum length
                form = form_list[i]
                filing_date = filing_date_list[i]
                accession_no = accession_number_list[i]
                report_date = report_date_list[i] # No need to check index, already limited by min_len
                # Get primary document, default to None if list is shorter or index out of bounds
                primary_doc = primary_document_list[i] if i < len(primary_document_list) else None

                if form == form_type and filing_date >= cutoff_date:
                    # Clean accession number (remove dashes)
                    accession_no_cleaned = accession_no.replace('-', '')
                    # Construct URL to the filing index page
                    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_cleaned}/"

                    filing_dict = {
                        'accession_no': accession_no,
                        'filing_date': filing_date,
                        'form': form,
                        'report_date': report_date, # Include report_date
                        'url': filing_url,          # Include constructed URL
                        'primary_document': primary_doc, # Include primary document filename
                        # Keep ticker for potential caching key consistency if needed, though not required by UI
                        # 'ticker': ticker
                    }
                    
                    # Optional: Add owner/issuer if Form 4, although UI doesn't explicitly request it
                    # if form_type == "4":
                    #     filing_dict['reportingOwner'] = recent_filings.get('reportingOwner', [''])[i] if i < len(recent_filings.get('reportingOwner', [])) else ''
                    #     filing_dict['issuerName'] = recent_filings.get('issuerName', [''])[i] if i < len(recent_filings.get('issuerName', [])) else ''
                    
                    filings.append(filing_dict)
            
            # Cache the filings (now in the new format)
            if filings:
                self._save_filings_to_cache(ticker, form_type, filings)
            
            return filings
                
        except Exception as e:
            logging.error(f"Error processing {form_type} filings for {ticker}: {str(e)}")
            return []

    def _load_filings_from_cache(self, ticker: str, form_type: str) -> List[Dict]:
        """Loads cached filtered filings for a specific ticker and form type from today."""
        # Find the most recent cache file for this ticker and form type
        cache_pattern = os.path.join(self.cache_dir, "forms", f"{ticker.upper()}_{form_type}_*.json")
        cache_files = sorted(glob.glob(cache_pattern), key=os.path.getmtime, reverse=True)
        
        if not cache_files:
            return []
            
        # Check if cache is from today (for freshness)
        today = datetime.now().strftime("%Y%m%d")
        if today not in cache_files[0]:
            return []  # Cache is not from today
            
        # Use the most recent cache file
        try:
            with open(cache_files[0], 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Error loading {form_type} filings from cache for {ticker}: {str(e)}")
            return []
    
    def _save_filings_to_cache(self, ticker: str, form_type: str, data: List[Dict]) -> None:
        """Save filings data to cache file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        # Ensure parent directory exists before saving
        cache_subdir = os.path.join(self.cache_dir, "forms")
        os.makedirs(cache_subdir, exist_ok=True)
        cache_file = os.path.join(
            cache_subdir, 
            f"{ticker.upper()}_{form_type}_{timestamp}.json"
        )
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Saved {form_type} filings to cache: {cache_file}")
        except Exception as e:
            logging.error(f"Error saving {form_type} filings to cache: {str(e)}")
    
    async def fetch_insider_filings(self, ticker: str, days_back: int = 90, 
                             use_cache: bool = True) -> List[Dict]:
        """
        Convenience method to fetch Form 4 (insider trading) filings.
        
        Calls `get_filings_by_form` with `form_type="4"`.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int, optional): Number of past days to include filings from. Defaults to 90.
            use_cache (bool, optional): Whether to use cached data. Defaults to True.
            
        Returns:
            List[Dict]: List of Form 4 filing data dictionaries.
        """
        return await self.get_filings_by_form(ticker, "4", days_back, use_cache)
    
    async def fetch_annual_reports(self, ticker: str, days_back: int = 365, 
                            use_cache: bool = True) -> List[Dict]:
        """
        Convenience method to fetch Form 10-K (annual report) filings.
        
        Calls `get_filings_by_form` with `form_type="10-K"`.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int, optional): Number of past days to include filings from. Defaults to 365.
            use_cache (bool, optional): Whether to use cached data. Defaults to True.
            
        Returns:
            List[Dict]: List of 10-K filing data dictionaries.
        """
        return await self.get_filings_by_form(ticker, "10-K", days_back, use_cache)
    
    async def fetch_quarterly_reports(self, ticker: str, days_back: int = 365, 
                               use_cache: bool = True) -> List[Dict]:
        """
        Convenience method to fetch Form 10-Q (quarterly report) filings.
        
        Calls `get_filings_by_form` with `form_type="10-Q"`.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int, optional): Number of past days to include filings from. Defaults to 365.
            use_cache (bool, optional): Whether to use cached data. Defaults to True.
            
        Returns:
            List[Dict]: List of 10-Q filing data dictionaries.
        """
        return await self.get_filings_by_form(ticker, "10-Q", days_back, use_cache)
    
    async def fetch_current_reports(self, ticker: str, days_back: int = 90, 
                             use_cache: bool = True) -> List[Dict]:
        """
        Convenience method to fetch Form 8-K (current report) filings.
        
        Calls `get_filings_by_form` with `form_type="8-K"`.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int, optional): Number of past days to include filings from. Defaults to 90.
            use_cache (bool, optional): Whether to use cached data. Defaults to True.
            
        Returns:
            List[Dict]: List of 8-K filing data dictionaries.
        """
        return await self.get_filings_by_form(ticker, "8-K", days_back, use_cache)
    
    async def fetch_form_direct(self, ticker: str, form_type: str, count: int = 1) -> List[Dict]:
        """
        DEPRECATED/Potentially Unreliable: Directly fetch metadata for the most recent forms of a specific type.
        Relies on synchronous requests within an async method, which is problematic.
        Prefer `get_filings_by_form`.
        
        Args:
            ticker (str): Stock ticker symbol.
            form_type (str): Form type (e.g., "10-K", "10-Q", "4").
            count (int): Number of most recent forms to fetch.
            
        Returns:
            List[Dict]: List of form data including accession numbers and filing dates.
        """
        cik = await self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot fetch forms: No CIK found for {ticker}")
            return []
        
        # Endpoint for company submissions
        submissions_url = self.SUBMISSIONS_ENDPOINT.format(cik=cik) # Use class constant
        
        try:
            response = self._make_request(submissions_url)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get submissions for {ticker} (CIK: {cik}): {response.status_code if response else 'No response'}")
                return []
            
            submissions_data = response.json()
            
            # Extract recent filings
            recent_filings = submissions_data.get('filings', {}).get('recent', {})
            if not recent_filings:
                logging.warning(f"No recent filings found for {ticker}")
                return []
            
            # Extract relevant fields safely
            forms = recent_filings.get('form', [])
            dates = recent_filings.get('filingDate', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            documents = recent_filings.get('primaryDocument', [])
            
            # Filter for the requested form type
            results = []
            num_filings = len(forms)
            for i in range(num_filings):
                if forms[i] == form_type:
                    # Ensure other lists have corresponding entries
                    if i < len(dates) and i < len(accession_numbers):
                        results.append({
                            'ticker': ticker,
                            'form': forms[i],
                            'filing_date': dates[i],
                            'accession_number': accession_numbers[i],
                            'primary_document': documents[i] if i < len(documents) else None,
                        })
                        if len(results) >= count:
                            break # Stop once we have the desired count
            
            return results
        
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding submissions JSON for {ticker}: {str(e)}")
            if response: logging.error(f"Response text that failed decoding: {response.text[:500]}")
            return []
        except Exception as e:
            logging.error(f"Error fetching {form_type} for {ticker} (CIK: {cik}): {str(e)}")
            return []

    async def download_form_document(self, accession_number: str, document_name: str) -> Optional[str]:
        """
        Downloads a specific document file directly from the SEC archive.

        Requires both the accession number and the exact filename of the document.
        Use this when you already know the target document file (e.g., from
        `fetch_form_direct` or by inspecting the filing index).

        Args:
            accession_number (str): SEC accession number (e.g., '0000320193-23-000106').
                                    Dashes are optional.
            document_name (str): The specific filename to download from the filing
                                 (e.g., 'aapl-20230930.htm', 'form4.xml').

        Returns:
            Optional[str]: Document content (usually HTML or XML) or None if not found/error.
        """
        if not accession_number or not document_name:
             logging.error("Accession number and document name are required.")
             return None
             
        # Format accession number (remove dashes)
        clean_accession = accession_number.replace('-', '')
        
        # Basic validation
        if len(clean_accession) < 11: # Need at least 10 for CIK + 1
             logging.error(f"Invalid accession number format: {accession_number}")
             return None

        # Get CIK from the accession number (first 10 digits)
        cik = clean_accession[:10].lstrip('0') # CIK in URL path often has leading zeros stripped
        # Ensure CIK is numeric-like before using in URL
        if not cik.isdigit():
             logging.error(f"Could not extract valid CIK from accession number: {accession_number}")
             return None
             
        # Construct the URL
        # Example: https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{clean_accession}/{document_name}"
        logging.info(f"Attempting to download document from: {url}") # Add log for URL
        
        try:
            # Explicitly set headers for www.sec.gov archives
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov' # Explicitly set Host for this request
            logging.info(f"Using headers for document download: {temp_headers}") # Log headers
            
            # Use the modified headers for this specific request
            response = await self._make_request(url, is_json=False, headers=temp_headers)
            
            if not response:
                logging.error(f"Failed to download document {document_name} (No response from server)")
                return None
                
            if response.status_code != 200:
                logging.error(f"Failed to download document {document_name} ({accession_number}). Status: {response.status_code}, Reason: {response.reason}")
                logging.error(f"URL attempted: {url}")
                # Log response text for debugging
                # logging.error(f"Response text: {response.text[:500]}") 
                return None
            
            # Check content type? Might not be reliable
            # content_type = response.headers.get('Content-Type', '')
            
            return response.text
            
        except Exception as e:
            logging.error(f"Error downloading document {document_name} ({accession_number}): {str(e)}")
            logging.error(f"URL attempted: {url}")
            return None

    async def fetch_filing_document(self, accession_no: str, primary_doc: str = None, ticker: str = None) -> Optional[str]:
        """
        Fetches the textual content of a specific document within an SEC filing.

        Determines the correct CIK and document URL. If `primary_doc` is not provided,
        it attempts to find the most likely primary document (HTML or XML) by first checking
        `index.json` and falling back to parsing `index.htm`.

        Args:
            accession_no (str): The SEC filing accession number (e.g., '0001193125-23-017489').
                                Dashes are optional.
            primary_doc (str, optional): The specific filename of the document within the filing
                                         (e.g., 'd451917d8k.htm'). If None, the method attempts
                                         to automatically determine the primary document.
                                         Defaults to None.
            ticker (str, optional): The stock ticker symbol. Used as a hint to find the CIK more reliably.
                                    Defaults to None.

        Returns:
            Optional[str]: The textual content (HTML, XML, or plain text) of the specified or
                           determined primary document, or None if an error occurs or the document
                           cannot be found/retrieved.
        """
        # Format accession number for URL (remove dashes)
        accession_no_clean = accession_no.replace('-', '')
        
        # Get CIK (either from ticker or extracted from accession number)
        cik = None
        
        # 1. Try to get CIK from ticker (most reliable)
        if ticker:
            try:
                cik = await self.get_cik_for_ticker(ticker)
                if cik:
                    # Strip leading zeros for URL
                    cik = cik.lstrip('0')
                    logging.debug(f"Using CIK {cik} from ticker {ticker}")
            except Exception as e:
                logging.error(f"Error looking up CIK for ticker {ticker}: {e}")
        
        # 2. Try to extract from accession number format
        if not cik:
            parts = accession_no.split('-')
            if len(parts) == 3:
                potential_cik_part = parts[0]
                # Remove leading zeros to get actual CIK number
                cik = potential_cik_part.lstrip('0')
                logging.debug(f"Extracted potential CIK {cik} from accession {accession_no}")
                
        # If we still don't have a CIK, we can't continue
        if not cik:
            logging.error(f"Could not determine CIK for accession {accession_no}")
            return None
            
        logging.info(f"Using CIK {cik} for accessing accession {accession_no}")
        
        # If primary_doc isn't provided, try to find it
        if not primary_doc:
            # First try the index.json approach (SEC should return JSON with content type text/html)
            index_json_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_clean}/index.json"
            logging.info(f"Looking for primary document via index.json: {index_json_url}")
            
            try:
                # Prepare headers for www.sec.gov
                temp_headers = self.headers.copy()
                temp_headers['Host'] = 'www.sec.gov'
                
                # Get the index data
                index_data = await self._make_request(index_json_url, headers=temp_headers)
                
                # Check if we got valid JSON with a directory structure
                if isinstance(index_data, dict) and 'directory' in index_data:
                    # Look for XML or HTML files in the directory
                    potential_docs = []
                    
                    for item in index_data.get('directory', {}).get('item', []):
                        name = item.get('name', '')
                        # Look for likely primary document formats
                        if name.endswith(('.xml', '.htm', '.html')) and not name.endswith('-index.html'):
                            if name.startswith(('form4', 'xslF345X', 'wk-form')):
                                # Form 4 patterns - prioritize
                                potential_docs.insert(0, name)
                            elif any(x in name.lower() for x in ['-10k', '-10q', '-8k']):
                                # Annual/quarterly report patterns
                                potential_docs.insert(0, name)
                            else:
                                # Other possibly relevant files
                                potential_docs.append(name)
                    
                    if potential_docs:
                        primary_doc = potential_docs[0]
                        logging.info(f"Found primary document from index.json: {primary_doc}")
                    else:
                        logging.warning(f"No likely primary documents found in index.json")
                else:
                    # We didn't get valid JSON directory data
                    logging.warning(f"index.json didn't return expected directory structure")
            
            except Exception as e:
                logging.error(f"Error parsing index.json for {accession_no}: {str(e)}")
            
            # If we still don't have a primary_doc, fall back to HTML index page
            if not primary_doc:
                index_html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_clean}/index.htm"
                logging.info(f"Falling back to HTML index page: {index_html_url}")
                
                try:
                    # Use same headers as above
                    index_html = await self._make_request(index_html_url, headers=temp_headers, is_json=False)
                    if not index_html:
                        logging.error(f"Failed to get HTML index page for accession number {accession_no}")
                        return None
                    
                    # Use regex pattern matching to find document links
                    # Common patterns for main documents
                    patterns = [
                        # 10-K/10-Q patterns
                        r'(\w+-\d+\.htm)',
                        r'(10-[kq]\.htm)',
                        # Form 4 patterns
                        r'(form4\.xml)',
                        r'(xslF345X\d+\.xml)',
                        r'(wk-form4_\d+\.xml)',
                        # Generic patterns
                        r'(primary_doc\.\w+)',
                        r'_(\w+\.htm)'
                    ]
                    
                    # Try each pattern
                    possible_docs = []
                    for pattern in patterns:
                        matches = re.findall(pattern, index_html.lower())
                        if matches:
                            for match in matches:
                                if match not in possible_docs:
                                    possible_docs.append(match)
                    
                    # If we found possible documents, use the first one
                    if possible_docs:
                        primary_doc = possible_docs[0]
                        logging.info(f"Found potential primary document from HTML: {primary_doc}")
                    else:
                        # If no pattern match, look for any links with .htm or .xml extension
                        htm_links = re.findall(r'href=[\'"]?([^\'" >]+\.htm)', index_html) 
                        xml_links = re.findall(r'href=[\'"]?([^\'" >]+\.xml)', index_html)
                        
                        all_links = htm_links + xml_links
                        if all_links:
                            # Filter out links that don't seem like document names
                            filtered_links = [link for link in all_links if '?' not in link and '//' not in link]
                            if filtered_links:
                                primary_doc = filtered_links[0]
                                logging.info(f"Found primary document from HTML links: {primary_doc}")
                
                except Exception as e:
                    logging.error(f"Error processing HTML index for {accession_no}: {str(e)}")
                
            # If we still don't have a primary document, we can't continue
            if not primary_doc:
                logging.error(f"Could not determine primary document for {accession_no}")
                return None
        
        # Now that we have both CIK and primary_doc, fetch the actual document
        document_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_clean}/{primary_doc}"
        logging.info(f"Fetching document: {document_url}")
        
        try:
            # Prepare headers for www.sec.gov
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov'

            # Get the document content (text, not JSON)
            document_content = await self._make_request(document_url, is_json=False, headers=temp_headers)
            if not document_content:
                logging.error(f"Failed to get document for accession number {accession_no} (no response)")
                return None
                
            return document_content
            
        except Exception as e:
            logging.error(f"Error fetching document for accession number {accession_no}: {str(e)}")
            return None
    
    async def process_insider_filings(self, ticker: str, days_back: int = 90) -> pd.DataFrame:
        """
        DEPRECATED/Placeholder: Processes Form 4 filings metadata into a basic DataFrame.
        Does NOT currently fetch or parse the actual transaction details from the forms.
        Prefer `get_recent_insider_transactions` for actual transaction data.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int): Number of days back to analyze filings.
            
        Returns:
            pd.DataFrame: DataFrame containing basic metadata of Form 4 filings.
        """
        # Get Form 4 filings
        filings = await self.fetch_insider_filings(ticker, days_back)
        
        if not filings:
            logging.info(f"No Form 4 filings found for {ticker}")
            return pd.DataFrame()
        
        # For each filing, fetch the actual document and extract transaction details
        # In a full implementation, this would parse the XML/HTML content
        # This is a simplified placeholder that returns limited information
        
        transactions = []
        
        for filing in filings:
            # In a real implementation, we would fetch and parse the Form 4 document
            # Here we're just adding basic metadata
            
            transaction = {
                'ticker': ticker,
                'filed_at': filing.get('filedAt'),
                'accession_no': filing.get('accessionNo'),
                'reporting_owner': filing.get('reportingOwner', ''),
                'issuer_name': filing.get('issuerName', ''),
                # Additional fields would be populated by parsing the document
            }
            
            transactions.append(transaction)
        
        # Convert to DataFrame
        if transactions:
            return pd.DataFrame(transactions)
        else:
            return pd.DataFrame()
    
    async def fetch_multiple_tickers(self, tickers: List[str], form_type: str = "4", 
                             days_back: int = 90, use_cache: bool = True) -> Dict[str, List]:
        """
        Fetch filings for multiple tickers.
        
        Args:
            tickers (List[str]): List of stock ticker symbols
            form_type (str): SEC form type to fetch
            days_back (int): Limit results to filings within this many days
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            Dict[str, List]: Dictionary with tickers as keys and lists of filings as values
        """
        results = {}
        
        for ticker in tickers:
            ticker = ticker.upper()
            
            try:
                if form_type == "4":
                    filings = await self.fetch_insider_filings(ticker, days_back, use_cache)
                elif form_type == "10-K":
                    filings = await self.fetch_annual_reports(ticker, days_back, use_cache)
                elif form_type == "10-Q":
                    filings = await self.fetch_quarterly_reports(ticker, days_back, use_cache)
                elif form_type == "8-K":
                    filings = await self.fetch_current_reports(ticker, days_back, use_cache)
                else:
                    filings = await self.get_filings_by_form(ticker, form_type, days_back, use_cache)
                
                results[ticker] = filings
                
                if filings:
                    logging.info(f"Found {len(filings)} {form_type} filings for {ticker}")
                else:
                    logging.info(f"No {form_type} filings found for {ticker}")
            
            except Exception as e:
                logging.error(f"Error fetching {form_type} data for {ticker}: {str(e)}")
                results[ticker] = []
        
        return results
    
    async def summarize_insider_activity(self, ticker: str, days_back: int = 90, 
                                use_cache: bool = True) -> Dict:
        """
        DEPRECATED/Placeholder: Creates a summary based only on the *count* of Form 4 filings.
        Does NOT analyze actual transaction data (buy/sell counts or values).
        Prefer `analyze_insider_transactions` for meaningful analysis.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int): Number of days back to analyze.
            use_cache (bool): Whether to use cached data if available.
            
        Returns:
            Dict: Summary containing total filings count and basic metadata.
        """
        ticker = ticker.upper()
        
        # Get all Form 4 filings
        filings = await self.fetch_insider_filings(ticker, days_back, use_cache)
        
        if not filings:
            return {
                'ticker': ticker,
                'total_filings': 0,
                'buy_count': 0,
                'sell_count': 0,
                'total_buy_value': 0.0,
                'total_sell_value': 0.0,
                'net_value': 0.0,
                'filing_dates': [],
                'recent_filings': []
            }
        
        # In a full implementation, this would parse the Form 4 XML/HTML
        # to extract detailed transaction information
        # For now, we just count the filings
        
        summary = {
            'ticker': ticker,
            'total_filings': len(filings),
            'buy_count': 0,  # Would be populated by XML parsing
            'sell_count': 0,  # Would be populated by XML parsing
            'total_buy_value': 0.0,  # Would be populated by XML parsing
            'total_sell_value': 0.0,  # Would be populated by XML parsing
            'net_value': 0.0,  # Would be populated by XML parsing
            'filing_dates': [filing.get('filedAt') for filing in filings],
            'recent_filings': filings[:10]  # Top 10 most recent filings
        }
        
        return summary
    
    async def generate_insider_report(self, ticker: str, days_back: int = 90, 
                             use_cache: bool = True) -> str:
        """
        DEPRECATED/Placeholder: Generates a text report based on filing counts, not actual transactions.
        Uses deprecated `summarize_insider_activity`.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int): Number of days back to analyze.
            use_cache (bool): Whether to use cached data if available.
            
        Returns:
            str: Formatted text report (based on filing counts only).
        """
        ticker = ticker.upper()
        
        # Get company info
        company_info = await self.get_company_info(ticker, use_cache)
        
        # Get insider activity summary
        summary = await self.summarize_insider_activity(ticker, days_back, use_cache)
        
        # Format the report
        lines = []
        lines.append(f"INSIDER ACTIVITY REPORT: {ticker}")
        lines.append("=" * 50)
        
        if company_info:
            lines.append(f"Company: {company_info.get('name', 'N/A')}")
            lines.append(f"CIK: {company_info.get('cik', 'N/A')}")
            lines.append(f"Industry: {company_info.get('sic_description', 'N/A')}")
        
        lines.append(f"\nTime Period: Last {days_back} days")
        lines.append(f"Total Form 4 Filings: {summary.get('total_filings', 0)}")
        
        # In a full implementation, you would include more detailed analysis here
        
        if summary.get('recent_filings'):
            lines.append("\nRecent Filings:")
            lines.append("-" * 50)
            
            for i, filing in enumerate(summary.get('recent_filings', []), 1):
                lines.append(f"{i}. Filed on {filing.get('filedAt', 'N/A')}")
                lines.append(f"   Accession Number: {filing.get('accessionNo', 'N/A')}")
                lines.append(f"   Reporting Owner: {filing.get('reportingOwner', 'N/A')}")
                lines.append("")
        
        # Save the report to a file
        report_path = os.path.join(
            self.cache_dir, "reports", 
            f"{ticker}_insider_report_{datetime.now().strftime('%Y%m%d')}.txt"
        )
        
        try:
            with open(report_path, 'w') as f:
                f.write("\n".join(lines))
            logging.info(f"Saved insider report to {report_path}")
        except Exception as e:
            logging.error(f"Error saving insider report: {str(e)}")
        
        return "\n".join(lines)

    async def download_form_xml(self, accession_no: str, ticker: str = None) -> Optional[str]:
        """
        Downloads the primary XML document (typically for Form 4) for a given filing.

        It first fetches the filing's `index.json` to identify the correct XML filename
        (looking for patterns like `form4.xml`, `wk-form4_*.xml`, etc.) and then downloads that file.
        
        Args:
            accession_no (str): The SEC filing accession number (dashes optional).
            ticker (str, optional): The stock ticker symbol of the *issuer*. Used to find the correct CIK
                                    for the URL path. Defaults to None (will attempt CIK from accession no).

        Returns:
            Optional[str]: The content of the XML file as a string, or None if not found or error.
        """
        # Format accession number for URL (remove dashes)
        accession_no_clean = accession_no.replace('-', '')
        cik_for_url = None

        # 1. Try to get CIK from ticker (most reliable)
        if ticker:
            try:
                cik_lookup = await self.get_cik_for_ticker(ticker)
                if cik_lookup:
                    cik_for_url = cik_lookup.lstrip('0') # Use CIK stripped of leading zeros for path
                    logging.debug(f"Using CIK {cik_for_url} from ticker {ticker} for XML download URL.")
            except Exception as e:
                logging.warning(f"Error looking up CIK for ticker {ticker} during XML download: {e}")

        # 2. Fallback: Try to extract CIK-like part from accession number
        if not cik_for_url:
            cik_part_from_acc = accession_no_clean[0:10]
            if cik_part_from_acc.isdigit():
                cik_for_url = cik_part_from_acc # Keep leading zeros if extracted this way? SEC inconsistent.
                # Let's try stripping zeros here too for consistency
                cik_for_url = cik_for_url.lstrip('0')
                logging.warning(f"Could not get CIK from ticker {ticker}. Falling back to using extracted part {cik_for_url} from accession {accession_no} for URL.")
            else:
                logging.error(f"Could not determine valid CIK for URL from ticker {ticker} or accession {accession_no}. Cannot download XML.")
                return None

        # First get the index to find the XML file
        # Use the determined CIK for the URL path
        index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_for_url}/{accession_no_clean}/index.json"

        try:
            # Prepare headers for www.sec.gov
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov'
            logging.info(f"Fetching index.json from {index_url} with headers: {temp_headers}")

            # ADD AWAIT HERE
            response = await self._make_request(index_url, headers=temp_headers, is_json=True) # Expecting JSON
            # Check response status (make_request doesn't raise for non-200 by default if retries fail)
            # if response is None or not isinstance(response, dict): # _make_request returns dict on success for json
            #     logging.error(f"Failed to get or parse index for accession number {accession_no}. URL: {index_url}")
            #     return None
            
            # Parse the index to find XML files
            # index_data = response # Already parsed by _make_request

            # Check if response is a dictionary (parsed JSON)
            if not isinstance(response, dict):
                logging.error(f"Index response for {accession_no} was not valid JSON. Type: {type(response)}. URL: {index_url}")
                return None
            index_data = response

            # Look for XML file - SEC often uses filenames like 'wk-form4_*.xml' or 'form4.xml' or 'XML' doc type
            xml_file = None
            for file_entry in index_data.get('directory', {}).get('item', []):
                file_name = file_entry.get('name', '')
                file_type = file_entry.get('type', '') # Check type description as well
                # Prioritize specific known patterns, then generic .xml
                if file_name.endswith('.xml') and ('form4' in file_name.lower() or 'f345' in file_name.lower()):
                    xml_file = file_name
                    break
                if file_type and 'XML' in file_type.upper() and file_name.endswith('.xml'):
                    xml_file = file_name # Found by type
                    break # Probably the right one
            
            # Fallback if specific names weren't found
            if not xml_file:
                for file_entry in index_data.get('directory', {}).get('item', []):
                    file_name = file_entry.get('name', '')
                    if file_name.endswith('.xml'):
                        xml_file = file_name
                        logging.info(f"Found generic XML file '{xml_file}' - assuming it is the correct one.")
                        break

            if not xml_file:
                logging.error(f"No suitable XML file found in index for accession number {accession_no}. Files: {[item.get('name') for item in index_data.get('directory', {}).get('item', [])]}")
                return None

            # Now download the XML file
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_for_url}/{accession_no_clean}/{xml_file}"
            logging.info(f"Attempting to download XML file: {xml_url}")

            # ADD AWAIT HERE TOO, and specify is_json=False
            response_text = await self._make_request(xml_url, headers=temp_headers, is_json=False)
            # Check if response_text is actually text content
            if response_text is None or not isinstance(response_text, str):
                logging.error(f"Failed to get XML file '{xml_file}' content for accession number {accession_no}. Received: {type(response_text)}")
                return None

            return response_text
        
        except json.JSONDecodeError as e:
             logging.error(f"Error decoding index.json for {accession_no}: {e}. URL: {index_url}")
             if response: logging.error(f"Response text: {response.text[:500]}")
             return None
        except Exception as e:
            logging.error(f"Error downloading XML file for accession number {accession_no}: {str(e)}")
            return None
    
    async def download_all_form_documents(self, accession_no: str, output_dir: str = None) -> Dict[str, str]:
        """
        Downloads all documents listed in a filing's `index.json`.
        
        Optionally saves the documents to a specified output directory.
        Note: This currently relies on synchronous requests within an async method via `_make_request`,
        which might be inefficient for numerous small files. Consider refactoring for full async downloads if performance is critical.
        
        Args:
            accession_no (str): The SEC filing accession number (dashes optional).
            output_dir (str, optional): If provided, saves each downloaded document to this directory.
                                        Directory will be created if it doesn't exist.
                                        Defaults to None (documents are not saved locally).
            
        Returns:
            Dict[str, str]: A dictionary where keys are filenames and values are the
                            corresponding file contents (as strings).
                            Returns an empty dictionary if the index cannot be fetched or other errors occur.
        """
        # Format accession number for URL (remove dashes)
        accession_no_clean = accession_no.replace('-', '')
        
        # Create output directory if specified
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # First get the index to find all files
        index_url = f"https://www.sec.gov/Archives/edgar/data/{accession_no_clean[0:10]}/{accession_no_clean}/index.json"
        
        try:
            # Prepare headers for www.sec.gov
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov'
            
            response = await self._make_request(index_url, headers=temp_headers)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get index for accession number {accession_no}")
                return {}
            
            # Parse the index to find all files
            index_data = response.json()
            
            # Get all files
            documents = {}
            
            for file_entry in index_data.get('directory', {}).get('item', []):
                file_name = file_entry.get('name', '')
                if not file_name or file_name == 'index.json':
                    continue
                    
                # Download the file
                file_url = f"https://www.sec.gov/Archives/edgar/data/{accession_no_clean[0:10]}/{accession_no_clean}/{file_name}"
                
                response = await self._make_request(file_url, headers=temp_headers, is_json=False)
                if not response or response.status_code != 200:
                    logging.warning(f"Failed to get file {file_name} for accession number {accession_no}")
                    continue
                
                file_content = response.text
                
                # Save to file if output_dir specified
                if output_dir:
                    file_path = os.path.join(output_dir, file_name)
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(file_content)
                    except Exception as e:
                        logging.error(f"Error saving file {file_name}: {str(e)}")
                
                documents[file_name] = file_content
            
            return documents
            
        except Exception as e:
            logging.error(f"Error downloading documents for accession number {accession_no}: {str(e)}")
            return {}
    
    def parse_form4_xml(self, xml_content: str) -> List[Dict]:
        """
        Parses Form 4 XML content into structured transaction data using ElementTree.

        Args:
            xml_content (str): XML content of Form 4.

        Returns:
            List[Dict]: List of transaction dictionaries.
        """
        transactions = []
        try:
            # Add namespace handling if necessary - sometimes SEC XML uses them
            # Example: namespaces = {'ns': 'http://www.sec.gov/edgar/ownership'}
            # Then use find('ns:tag', namespaces)
            # For now, assuming no namespace or default namespace
            root = ET.fromstring(xml_content)

            # --- Extract common info --- 
            issuer_cik = root.findtext('.//issuer/issuerCik', default='N/A')
            issuer_name = root.findtext('.//issuer/issuerName', default='N/A')
            issuer_symbol = root.findtext('.//issuer/issuerTradingSymbol', default='N/A')

            owner_cik = root.findtext('.//reportingOwner/reportingOwnerId/rptOwnerCik', default='N/A')
            owner_name = root.findtext('.//reportingOwner/reportingOwnerId/rptOwnerName', default='N/A')
            # Get relationship info (optional, add if needed)
            # is_director = root.findtext('.//reportingOwner/reportingOwnerRelationship/isDirector', default='0') == '1'
            # is_officer = root.findtext('.//reportingOwner/reportingOwnerRelationship/isOfficer', default='0') == '1'
            # officer_title = root.findtext('.//reportingOwner/reportingOwnerRelationship/officerTitle', default='')

            # --- Process Non-Derivative Transactions --- 
            for tx in root.findall('.//nonDerivativeTransaction'):
                try:
                    security_title = tx.findtext('./securityTitle/value', default='N/A')
                    tx_date = tx.findtext('./transactionDate/value', default='N/A')
                    tx_code = tx.findtext('./transactionCoding/transactionCode', default='N/A')
                    
                    shares_str = tx.findtext('./transactionAmounts/transactionShares/value', default='0')
                    price_str = tx.findtext('./transactionAmounts/transactionPricePerShare/value', default='0')
                    acq_disp_code = tx.findtext('./transactionAmounts/transactionAcquiredDisposedCode/value', default='N/A')

                    shares_owned_after_str = tx.findtext('./postTransactionAmounts/sharesOwnedFollowingTransaction/value', default='N/A')
                    direct_indirect = tx.findtext('./ownershipNature/directOrIndirectOwnership/value', default='N/A')

                    # Convert to appropriate types
                    shares = float(shares_str) if shares_str and shares_str.replace('.', '', 1).isdigit() else 0.0
                    price = float(price_str) if price_str and price_str.replace('.', '', 1).isdigit() else 0.0
                    shares_owned_after = float(shares_owned_after_str) if shares_owned_after_str and shares_owned_after_str.replace('.', '', 1).isdigit() else None
                    
                    transaction_type = self.TRANSACTION_CODE_MAP.get(tx_code, 'Unknown')
                    is_acquisition = tx_code in self.ACQUISITION_CODES
                    is_disposition = tx_code in self.DISPOSITION_CODES

                    transaction = {
                        'ticker': issuer_symbol,
                        'issuer_cik': issuer_cik,
                        'issuer_name': issuer_name,
                        'owner_cik': owner_cik,
                        'owner_name': owner_name,
                        'transaction_date': tx_date,
                        'security_title': security_title,
                        'transaction_code': tx_code,
                        'transaction_type': transaction_type,
                        'acq_disp_code': acq_disp_code,
                        'is_acquisition': is_acquisition,
                        'is_disposition': is_disposition,
                        'shares': shares,
                        'price_per_share': price,
                        'value': shares * price if shares is not None and price is not None else 0.0,
                        'shares_owned_after': shares_owned_after,
                        'direct_indirect': direct_indirect,
                        'is_derivative': False
                    }
                    transactions.append(transaction)
                except Exception as e:
                    logging.warning(f"Error parsing non-derivative transaction: {e} - XML snippet: {ET.tostring(tx, encoding='unicode', short_empty_elements=False)[:200]}")
            
            # --- Process Derivative Transactions --- 
            for tx in root.findall('.//derivativeTransaction'):
                try:
                    security_title = tx.findtext('./securityTitle/value', default='N/A')
                    tx_date = tx.findtext('./transactionDate/value', default='N/A')
                    tx_code = tx.findtext('./transactionCoding/transactionCode', default='N/A')
                    # Note: Derivative transactions often have exercise/conversion price instead of direct price
                    conv_exercise_price_str = tx.findtext('./conversionOrExercisePrice/value', default='0')
                    shares_str = tx.findtext('./transactionAmounts/transactionShares/value', default='0') # Shares transacted
                    acq_disp_code = tx.findtext('./transactionAmounts/transactionAcquiredDisposedCode/value', default='N/A')

                    exercise_date = tx.findtext('./exerciseDate/value', default='N/A')
                    expiration_date = tx.findtext('./expirationDate/value', default='N/A')

                    underlying_title = tx.findtext('./underlyingSecurity/underlyingSecurityTitle/value', default='N/A')
                    underlying_shares_str = tx.findtext('./underlyingSecurity/underlyingSecurityShares/value', default='0')

                    shares_owned_after_str = tx.findtext('./postTransactionAmounts/sharesOwnedFollowingTransaction/value', default='N/A')
                    direct_indirect = tx.findtext('./ownershipNature/directOrIndirectOwnership/value', default='N/A')

                    # Convert to appropriate types
                    shares = float(shares_str) if shares_str and shares_str.replace('.', '', 1).isdigit() else 0.0
                    conv_exercise_price = float(conv_exercise_price_str) if conv_exercise_price_str and conv_exercise_price_str.replace('.', '', 1).isdigit() else 0.0
                    underlying_shares = float(underlying_shares_str) if underlying_shares_str and underlying_shares_str.replace('.', '', 1).isdigit() else 0.0
                    shares_owned_after = float(shares_owned_after_str) if shares_owned_after_str and shares_owned_after_str.replace('.', '', 1).isdigit() else None

                    transaction_type = self.TRANSACTION_CODE_MAP.get(tx_code, 'Unknown')
                    is_acquisition = tx_code in self.ACQUISITION_CODES
                    is_disposition = tx_code in self.DISPOSITION_CODES

                    transaction = {
                        'ticker': issuer_symbol,
                        'issuer_cik': issuer_cik,
                        'issuer_name': issuer_name,
                        'owner_cik': owner_cik,
                        'owner_name': owner_name,
                        'transaction_date': tx_date,
                        'security_title': security_title,
                        'transaction_code': tx_code,
                        'transaction_type': transaction_type,
                        'acq_disp_code': acq_disp_code,
                        'is_acquisition': is_acquisition,
                        'is_disposition': is_disposition,
                        'shares': shares, # Number of derivative securities transacted
                        'conversion_exercise_price': conv_exercise_price,
                        'exercise_date': exercise_date,
                        'expiration_date': expiration_date,
                        'underlying_title': underlying_title,
                        'underlying_shares': underlying_shares, # Number of underlying shares
                        'shares_owned_after': shares_owned_after, # Derivative securities owned after
                        'direct_indirect': direct_indirect,
                        'is_derivative': True
                        # Value calculation for derivatives is more complex (depends on type), omitting for now
                    }
                    transactions.append(transaction)
                except Exception as e:
                    logging.warning(f"Error parsing derivative transaction: {e} - XML snippet: {ET.tostring(tx, encoding='unicode', short_empty_elements=False)[:200]}")

            return transactions

        except ET.ParseError as e:
            logging.error(f"XML Parse Error in Form 4: {e} - Content length: {len(xml_content)}")
            # Optionally log first few chars: logging.error(f"XML Content Start: {xml_content[:500]}")
            return []
        except Exception as e:
            # Catch-all for other unexpected errors during parsing
            logging.error(f"Unexpected error parsing Form 4 XML: {e}")
            return []
    
    async def process_form4_filing(self, accession_no: str, ticker: str = None) -> List[Dict]:
        """
        Downloads and parses a single Form 4 XML filing into structured transaction data.

        Calls `download_form_xml` to get the content and `parse_form4_xml` to process it.

        Args:
            accession_no (str): Accession number for the Form 4 filing.
            ticker (str, optional): The stock ticker symbol of the *issuer*, passed to `download_form_xml`
                                    to help construct the correct URL. Defaults to None.

        Returns:
            List[Dict]: A list of dictionaries, each representing a transaction parsed from the form.
                        Returns an empty list if download or parsing fails.
        """
        # Download the XML, passing the ticker
        xml_content = await self.download_form_xml(accession_no, ticker=ticker)
        
        if not xml_content:
            return []
        
        # Parse the XML
        return self.parse_form4_xml(xml_content)
    
    async def get_recent_insider_transactions(self, ticker: str, days_back: int = 90, 
                                     use_cache: bool = True) -> List[Dict]:
        """
        Fetches, parses, and formats recent Form 4 (insider) transactions for UI display.
        
        1. Fetches Form 4 filing metadata using `fetch_insider_filings`.
        2. For each recent filing (currently limited to the first 5 for performance):
           - Calls `process_form4_filing` to download and parse the XML.
           - Formats the parsed transactions into a structure suitable for the UI table.
           - Attempts to determine the filing's CIK for constructing the `form_url`.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int, optional): Number of past days to include filings from. Defaults to 90.
            use_cache (bool, optional): Whether to use cached filing metadata. Defaults to True.
            
        Returns:
            List[Dict]: A list of dictionaries, each representing an insider transaction
                        formatted for the `SECFilingViewer` table (keys: 'filer', 'date', 'type',
                        'shares', 'price', 'value', 'form_url', 'primary_document').
                        Returns an empty list if no transactions are found or errors occur.
        """
        ticker = ticker.upper()
        
        # Get all Form 4 filing metadata first
        # We use the refactored get_filings_by_form to get accession numbers etc.
        filings = await self.fetch_insider_filings(ticker, days_back, use_cache)
        
        if not filings:
            return [] # Return empty list directly
        
        # Process each filing to get transaction details and format for UI
        all_ui_transactions = [] 
        
        # Limit to first N filings for faster testing/debugging (e.g., 5 or 10)
        # TODO: Consider making this limit configurable or removing it later
        filing_limit = 10 
        logging.debug(f"Processing up to {filing_limit} most recent Form 4 filings for {ticker}...")
        for filing_meta in filings[:filing_limit]: 
            accession_no = filing_meta.get('accession_no')
            if not accession_no:
                logging.warning(f"Skipping filing for {ticker} due to missing accession number.")
                continue
            
            # Process the XML to get detailed transactions for this filing
            # process_form4_filing returns List[Dict] with parsed data
            # Pass the ticker down to help find the XML
            parsed_transactions = await self.process_form4_filing(accession_no, ticker=ticker)
            
            if not parsed_transactions:
                logging.debug(f"No transactions parsed for {ticker}, accession: {accession_no}")
                continue

            # Get CIK for URL construction (ideally from parsed data)
            # Assuming all transactions in a filing share the same issuer CIK
            # Try getting CIK from parsed data first
            issuer_cik = parsed_transactions[0].get('issuer_cik') 
            
            # If not in parsed data, use the CIK we likely already looked up
            if not issuer_cik or issuer_cik == 'N/A':
                # Use the ticker passed into this function to get the CIK again if needed
                logging.warning(f"Issuer CIK not found in parsed data for {accession_no}. Using ticker {ticker} to construct form URL.")
                looked_up_cik = await self.get_cik_for_ticker(ticker)
                if looked_up_cik:
                    issuer_cik = looked_up_cik # Use the full CIK with leading zeros here if needed?
                else:
                     logging.error(f"Cannot construct form URL for {accession_no}: CIK for {ticker} unavailable.")
                     issuer_cik = "N/A" # Proceed without URL
            
            # Clean accession number once for the filing
            accession_no_cleaned = accession_no.replace('-', '')
            form_url = "N/A" # Default if CIK is unavailable
            # Construct URL using CIK (strip leading zeros for path)
            if issuer_cik != "N/A" and issuer_cik:
                 cik_for_path = issuer_cik.lstrip('0')
                 form_url = f"https://www.sec.gov/Archives/edgar/data/{cik_for_path}/{accession_no_cleaned}/"

            # Format each parsed transaction for the UI
            for tx in parsed_transactions:
                # Map keys and format data
                ui_transaction = {
                    'filer': tx.get('owner_name', 'N/A'),
                    'date': tx.get('transaction_date', 'N/A'),
                    'type': tx.get('transaction_type', 'Unknown'), # Use parsed type
                    'shares': tx.get('shares'), # Already float or 0.0
                    'price': tx.get('price_per_share', tx.get('conversion_exercise_price')), # Use price_per_share for non-deriv, fallback for deriv
                    'value': tx.get('value', 0.0), # Use pre-calculated value if available
                    'form_url': form_url, # Use the constructed URL
                    'primary_document': tx.get('primary_document') # Include primary document filename
                }

                # Handle potential None for shares/price before calculating value if needed
                if ui_transaction['value'] is None or ui_transaction['value'] == 0.0:
                     shares = ui_transaction.get('shares')
                     price = ui_transaction.get('price')
                     if shares is not None and price is not None:
                          try:
                               ui_transaction['value'] = float(shares) * float(price)
                          except (ValueError, TypeError):
                               ui_transaction['value'] = 0.0 # Fallback if conversion fails
                     else:
                          ui_transaction['value'] = 0.0
                
                all_ui_transactions.append(ui_transaction)
        
        # Return the list of UI-formatted dictionaries
        return all_ui_transactions
    
    async def analyze_insider_transactions(self, ticker: str, days_back: int = 90, 
                                  use_cache: bool = True) -> Dict:
        """
        Performs basic analysis on recent insider transactions for a ticker.
        
        Fetches transaction data using `get_recent_insider_transactions`, converts it to a DataFrame,
        and calculates summary statistics like buy/sell counts, total/net values, involved owners, etc.
        
        Args:
            ticker (str): Stock ticker symbol.
            days_back (int, optional): Number of past days to include transactions from. Defaults to 90.
            use_cache (bool, optional): Whether to use cached data when fetching transactions.
                                       Defaults to True.
            
        Returns:
            Dict: A dictionary containing analysis results (e.g., 'total_transactions',
                  'buy_count', 'sell_count', 'total_buy_value', 'net_value', 'owners').
                  Includes an 'error' key if fetching or analysis fails.
        """
        ticker = ticker.upper()
        
        # Get all transactions
        transactions = await self.get_recent_insider_transactions(ticker, days_back, use_cache) # Now async
        
        if not transactions:
            return {
                'ticker': ticker,
                'error': "No transactions found or failed to fetch.",
             }

        df = pd.DataFrame(transactions) # Convert to DataFrame
        
        try:
            # Basic analysis
            buys = df[df['type'].str.contains('Purchase|Award|Exercise|Acquire', case=False, na=False)]
            sells = df[df['type'].str.contains('Sale|Dispose|Tax Withholding', case=False, na=False)]
            
            # Ensure 'value' column exists and is numeric
            if 'value' not in df.columns or df['value'].isnull().all():
                df['value'] = df.get('shares', 0) * df.get('price_per_share', 0)
            
            # Convert to numeric if not already
            df['value'] = pd.to_numeric(df['value'], errors='coerce').fillna(0)
            
            # Summary statistics
            result = {
                'ticker': ticker,
                'total_transactions': len(df),
                'buy_count': len(buys),
                'sell_count': len(sells),
                'total_buy_value': buys['value'].sum() if not buys.empty else 0,
                'total_sell_value': sells['value'].sum() if not sells.empty else 0,
                'net_value': buys['value'].sum() - sells['value'].sum() if not df.empty else 0,
                'owners': df['filer'].unique().tolist(),
                'start_date': df['date'].min() if 'date' in df.columns else None,
                'end_date': df['date'].max() if 'date' in df.columns else None,
                'transactions_by_type': df.groupby('transaction_type').size().to_dict() if 'transaction_type' in df.columns else {},
                'top_owners_by_value': df.groupby('owner_name')['value'].sum().sort_values(ascending=False).head(5).to_dict() if not df.empty else {}
            }
            
            return result
            
        except Exception as e:
            logging.error(f"Error analyzing insider transactions for {ticker}: {str(e)}")
            return {
                'ticker': ticker,
                'error': f"Analysis error: {str(e)}",
                'total_transactions': len(df)
            }

    _load_company_facts_from_cache = _save_company_facts_to_cache = get_company_facts = _get_latest_fact_value = _calculate_ratios = None

    async def get_company_facts(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """Fetches company facts (XBRL data) from the SEC's `companyfacts` API endpoint.

        This endpoint provides standardized financial data extracted from company filings.
        The data is structured by taxonomy (e.g., us-gaap, dei) and concept tag.
        Uses caching by default.
        
        Args:
            ticker (str): Stock ticker symbol.
            use_cache (bool, optional): Whether to use cached data if available. Defaults to True.
            
        Returns:
            Optional[Dict]: The raw company facts JSON data as a dictionary, including keys
                           like 'cik', 'entityName', and 'facts'. Returns None if an error occurs.
        """
        ticker = ticker.upper()

        # Try cache first
        if use_cache:
            cached_data = self._load_company_facts_from_cache(ticker)
            if cached_data:
                return cached_data

        # Get CIK
        cik = await self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot get company facts: No CIK found for {ticker}")
            return None

        # Construct URL
        facts_url = self.COMPANY_FACTS_ENDPOINT.format(cik=cik)
        logging.info(f"Fetching company facts from: {facts_url}")

        try:
            # Use standard headers for data.sec.gov
            company_facts_data = await self._make_request(facts_url, is_json=True, headers=self.headers)

            if company_facts_data is None:
                logging.error(f"Failed to get company facts for {ticker} (CIK: {cik})")
                return None

            # Cache the result
            self._save_company_facts_to_cache(ticker, cik, company_facts_data)

            return company_facts_data

        except json.JSONDecodeError as e:
            logging.error(f"Error decoding company facts JSON for {ticker}: {str(e)}")
            # Optionally log response text if decode fails
            # try:
            #     text_content = await response.text() # Need response object if logging text
            #     logging.error(f"Response text that failed decoding: {text_content[:1000]}")
            # except Exception:
            #     logging.error("Could not get response text after JSON error.")
            return None
        except Exception as e:
            logging.error(f"Error fetching company facts for {ticker} (CIK: {cik}): {str(e)}")
            return None

    # Helper function to get the latest value for a specific fact
    def _get_latest_fact_value(self, facts_data: Dict, taxonomy: str, concept_tag: str) -> Optional[Dict]:
        """Internal helper to find the latest reported value for a specific XBRL concept
        within the raw company facts data.

        Searches within the specified taxonomy and concept tag for the data point
        with the most recent 'end' date. Prioritizes 'USD' or 'shares' units.
        
        Args:
            facts_data (Dict): The raw dictionary returned by `get_company_facts`.
            taxonomy (str): The XBRL taxonomy to search within (e.g., 'us-gaap', 'dei').
            concept_tag (str): The specific XBRL concept tag (e.g., 'Assets', 'RevenueFromContractWithCustomerExcludingAssessedTax').
            
        Returns:
            Optional[Dict]: A dictionary containing details of the latest fact if found
                            (keys: 'value', 'unit', 'end_date', 'fy', 'fp', 'form', 'filed'),
                            otherwise None.
        """
        try:
            concept_data = facts_data.get('facts', {}).get(taxonomy, {}).get(concept_tag)
            if not concept_data:
                # logging.debug(f"Concept tag '{concept_tag}' not found in {taxonomy} taxonomy.")
                return None

            # Find available units (e.g., 'USD', 'shares')
            units = concept_data.get('units')
            if not units:
                # logging.debug(f"No units found for concept tag '{concept_tag}'.")
                return None

            # Prioritize USD for financials, shares for share counts
            target_unit = None
            if 'USD' in units:
                target_unit = 'USD'
            elif 'shares' in units:
                target_unit = 'shares'
            else:
                # Fallback to the first available unit if neither USD nor shares
                target_unit = list(units.keys())[0]
            
            unit_data = units.get(target_unit)
            if not unit_data or not isinstance(unit_data, list) or len(unit_data) == 0:
                # logging.debug(f"No data points found for unit '{target_unit}' in concept '{concept_tag}'.")
                return None

            # Find the entry with the latest 'end' date
            # We should also consider 'filed' date as a tie-breaker if needed, but 'end' is usually sufficient
            latest_entry = max(unit_data, key=lambda x: x.get('end', '0000-00-00'))
            
            # Basic validation of the found entry
            if not latest_entry or 'val' not in latest_entry:
                 logging.warning(f"Latest entry found for '{concept_tag}' seems invalid: {latest_entry}")
                 return None

            return {
                "value": latest_entry.get('val'),
                "unit": target_unit,
                "end_date": latest_entry.get('end'),
                "fy": latest_entry.get('fy'),
                "fp": latest_entry.get('fp'),
                "form": latest_entry.get('form'),
                "filed": latest_entry.get('filed')
            }

        except Exception as e:
            logging.error(f"Error processing concept '{concept_tag}' in taxonomy '{taxonomy}': {e}")
            return None

    # --- Financial Ratio Calculations ---
    def _calculate_ratios(self, summary_metrics: Dict) -> Dict:
        """Placeholder for calculating financial ratios. Currently not fully implemented or used."""
        calculated = {}

        # Helper to safely get metric values if periods match
        def get_matching_values(metric_names: List[str]) -> Optional[Tuple[Dict, ...]]:
            metrics_data = [summary_metrics.get(name) for name in metric_names]
            if not all(metrics_data):
                # logging.debug(f"Missing one or more metrics for ratio: {metric_names}")
                return None
            
            # Check for matching periods (simplistic check using end_date first)
            first_end_date = metrics_data[0].get('end_date')
            if not first_end_date:
                return None # Cannot match period
            if not all(m.get('end_date') == first_end_date for m in metrics_data):
                 # Add more sophisticated period matching later if needed (e.g., FY/FP)
                 # logging.debug(f"Metric periods don't match for ratio: {metric_names} - Dates: {[m.get('end_date') for m in metrics_data]}")
                 return None 
            
            # Check units (e.g., ensure all are USD for value-based ratios)
            if not all(m.get('unit') == 'USD' for m in metrics_data if m.get('unit') != 'shares'): # Allow 'shares' unit alongside USD if needed
                # logging.debug(f"Metric units are incompatible for ratio: {metric_names} - Units: {[m.get('unit') for m in metrics_data]}")
                return None

            return tuple(metrics_data)

        # 1. Current Ratio = Current Assets / Current Liabilities
        current_vals = get_matching_values(["AssetsCurrent", "LiabilitiesCurrent"])
        if current_vals:
            assets_curr = current_vals[0]['value']
            liab_curr = current_vals[1]['value']
            if liab_curr is not None and liab_curr != 0:
                calculated['CurrentRatio'] = {
                    "value": assets_curr / liab_curr if liab_curr else None,
                    "unit": "ratio",
                    "end_date": current_vals[0]['end_date'] # Use period from components
                }
            else:
                 calculated['CurrentRatio'] = {"value": None, "unit": "ratio", "end_date": current_vals[0]['end_date'], "error": "Zero current liabilities"}

        # 2. Debt-to-Equity = Total Liabilities / Stockholders' Equity
        debt_equity_vals = get_matching_values(["Liabilities", "StockholdersEquity"])
        if debt_equity_vals:
            liab_total = debt_equity_vals[0]['value']
            equity_total = debt_equity_vals[1]['value']
            if equity_total is not None and equity_total != 0:
                 calculated['DebtToEquityRatio'] = {
                    "value": liab_total / equity_total if equity_total else None,
                    "unit": "ratio",
                    "end_date": debt_equity_vals[0]['end_date']
                }
            else:
                 calculated['DebtToEquityRatio'] = {"value": None, "unit": "ratio", "end_date": debt_equity_vals[0]['end_date'], "error": "Zero equity"}

        # 3. Gross Profit Margin = Gross Profit / Revenue
        # Requires GrossProfit to be present (either directly or calculated earlier)
        gross_margin_vals = get_matching_values(["GrossProfit", "Revenue"])
        if gross_margin_vals:
            gross_profit = gross_margin_vals[0]['value']
            revenue = gross_margin_vals[1]['value']
            if revenue is not None and revenue != 0:
                calculated['GrossProfitMargin'] = {
                    "value": gross_profit / revenue if revenue else None,
                    "unit": "percent", # Or ratio if preferred
                    "end_date": gross_margin_vals[0]['end_date']
                }
            else:
                 calculated['GrossProfitMargin'] = {"value": None, "unit": "percent", "end_date": gross_margin_vals[0]['end_date'], "error": "Zero revenue"}
        
        # 4. Operating Profit Margin = Operating Income (Loss) / Revenue
        op_margin_vals = get_matching_values(["OperatingIncomeLoss", "Revenue"])
        if op_margin_vals:
            op_income = op_margin_vals[0]['value']
            revenue = op_margin_vals[1]['value']
            if revenue is not None and revenue != 0:
                calculated['OperatingProfitMargin'] = {
                    "value": op_income / revenue if revenue else None,
                    "unit": "percent",
                    "end_date": op_margin_vals[0]['end_date']
                }
            else:
                 calculated['OperatingProfitMargin'] = {"value": None, "unit": "percent", "end_date": op_margin_vals[0]['end_date'], "error": "Zero revenue"}

        # 5. Net Profit Margin = Net Income (Loss) / Revenue
        net_margin_vals = get_matching_values(["NetIncomeLoss", "Revenue"])
        if net_margin_vals:
            net_income = net_margin_vals[0]['value']
            revenue = net_margin_vals[1]['value']
            if revenue is not None and revenue != 0:
                calculated['NetProfitMargin'] = {
                    "value": net_income / revenue if revenue else None,
                    "unit": "percent",
                    "end_date": net_margin_vals[0]['end_date']
                }
            else:
                 calculated['NetProfitMargin'] = {"value": None, "unit": "percent", "end_date": net_margin_vals[0]['end_date'], "error": "Zero revenue"}

        return calculated

    # Main function to get financial summary, refactored for UI
    async def get_financial_summary(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """Generates a flattened summary of key financial metrics required by the UI.

        1. Fetches company facts using `get_company_facts`.
        2. Iterates through `KEY_FINANCIAL_SUMMARY_METRICS` defined in the class.
        3. For each required metric, calls `_get_latest_fact_value` to find the most recent data point.
        4. Constructs a flat dictionary containing the ticker, entity name, CIK, the source form
           and period end date of the latest key data points, and the values of the requested metrics.
        
        Args:
            ticker (str): Stock ticker symbol.
            use_cache (bool, optional): Whether to use cached company facts data. Defaults to True.
            
        Returns:
            Optional[Dict]: A flat dictionary summarizing key financial metrics (keys defined in
                            `KEY_FINANCIAL_SUMMARY_METRICS` plus metadata like 'ticker', 'entityName', 'cik',
                            'source_form', 'period_end'), or None if facts cannot be retrieved or
                            no relevant metric data is found.
        """
        company_facts = await self.get_company_facts(ticker, use_cache=use_cache)
        if not company_facts:
            logging.warning(f"Could not retrieve company facts for {ticker}. Cannot generate financial summary.")
            return None

        summary_data = {
            "ticker": ticker.upper(),
            "entityName": company_facts.get('entityName', "N/A"),
            "cik": company_facts.get('cik', "N/A"),
            "source_form": None, # To be determined
            "period_end": None,  # To be determined
        }

        # Initialize all required metric keys to None
        for key in self.KEY_FINANCIAL_SUMMARY_METRICS.keys():
            summary_data[key] = None

        latest_period_info = {"end_date": "0000-00-00", "form": None}
        has_data = False

        # Iterate through the required metrics defined in the mapping
        for metric_key, concept_details in self.KEY_FINANCIAL_SUMMARY_METRICS.items():
            # Determine taxonomy (assume us-gaap unless specified otherwise, e.g., via tuple)
            taxonomy = "us-gaap" # Default
            concept_tag = concept_details
            # Example if mixing taxonomies: 
            # if isinstance(concept_details, tuple):
            #    concept_tag, taxonomy = concept_details
            
            latest_fact = self._get_latest_fact_value(company_facts, taxonomy, concept_tag)
            
            if latest_fact:
                has_data = True # Mark that we found at least some data
                summary_data[metric_key] = latest_fact.get('value') # Extract only the value
                
                # Try to determine the most recent period end date and form 
                # based on key financial metrics (e.g., Revenue or NetIncome)
                current_end_date = latest_fact.get("end_date", "0000-00-00")
                if metric_key in ["revenue", "net_income"] and current_end_date > latest_period_info["end_date"]:
                    latest_period_info["end_date"] = current_end_date
                    latest_period_info["form"] = latest_fact.get('form')
            else:
                 logging.debug(f"Metric '{metric_key}' (Tag: {concept_tag}, Tax: {taxonomy}) not found or has no data for {ticker}.")
                 summary_data[metric_key] = None # Ensure it's None if not found
        
        # Assign the determined source form and period end
        summary_data["period_end"] = latest_period_info["end_date"] if latest_period_info["end_date"] != "0000-00-00" else None
        summary_data["source_form"] = latest_period_info["form"]

        # Return None if no relevant facts were found at all
        if not has_data:
             logging.warning(f"No financial metrics found for {ticker} based on defined tags.")
             return None 

        logging.info(f"Generated financial summary for {ticker} ending {summary_data['period_end']} from form {summary_data['source_form']}.")
        return summary_data

    async def close(self):
        """Closes the underlying aiohttp ClientSession if it's open."""
        if self._session and not self._session.closed:
            await self._session.close()
            logging.info("SECDataFetcher aiohttp session closed.")
        self._session = None # Ensure it's reset

    def _load_company_facts_from_cache(self, ticker: str) -> Optional[Dict]:
        """Load company facts from the most recent cache file."""
        cache_pattern = os.path.join(self.cache_dir, "facts", f"{ticker.upper()}_facts_*.json")
        cache_files = sorted(glob.glob(cache_pattern), key=os.path.getmtime, reverse=True)
        if not cache_files:
            return None
        # Optionally check for freshness (e.g., if cache_files[0] is from today)
        try:
            with open(cache_files[0], 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Error loading company facts from cache {cache_files[0]}: {e}")
            return None

    def _save_company_facts_to_cache(self, ticker: str, cik: str, data: Dict) -> None:
        """Save company facts data to a timestamped cache file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_subdir = os.path.join(self.cache_dir, "facts")
        os.makedirs(cache_subdir, exist_ok=True)
        cache_file = os.path.join(cache_subdir, f"{ticker.upper()}_facts_{timestamp}.json")
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Saved company facts to cache: {cache_file}")
        except Exception as e:
            logging.error(f"Error saving company facts to cache: {e}")

    async def get_filing_documents_list(self, accession_no: str, ticker: str = None) -> Optional[List[Dict]]:
        """Fetches the list of documents available within a specific filing.

        Attempts to fetch and parse the filing's index.json to get a list of
        contained files (name, type, size).

        Args:
            accession_no (str): The SEC filing accession number (dashes optional).
            ticker (str, optional): The stock ticker symbol, used as a hint for CIK lookup.
                                    Defaults to None.

        Returns:
            Optional[List[Dict]]: A list of dictionaries, where each dictionary
                                 represents a document in the filing (keys: 'name', 'type', 'size').
                                 Returns None if the index cannot be fetched or parsed.
        """
        accession_no_clean = accession_no.replace('-', '')
        cik = None

        # Get CIK first
        if ticker:
            try:
                cik = await self.get_cik_for_ticker(ticker)
                if cik:
                    cik = cik.lstrip('0')
            except Exception as e:
                logging.error(f"Error looking up CIK for ticker {ticker} while fetching doc list: {e}")

        if not cik:
            parts = accession_no.split('-')
            if len(parts) == 3:
                cik = parts[0].lstrip('0')

        if not cik:
            logging.error(f"Could not determine CIK for {accession_no} to fetch document list.")
            return None

        index_json_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_clean}/index.json"
        logging.info(f"Fetching document list via index.json: {index_json_url}")

        try:
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov'

            index_data = await self._make_request(index_json_url, headers=temp_headers, is_json=True)

            if not isinstance(index_data, dict) or 'directory' not in index_data:
                logging.warning(f"index.json for {accession_no} did not return expected structure. Type: {type(index_data)}")
                # TODO: Fallback to parsing index.htm if index.json fails?
                return None

            documents = []
            for item in index_data.get('directory', {}).get('item', []):
                doc_info = {
                    'name': item.get('name'),
                    'type': item.get('type'), # e.g., 'XML', 'GRAPHIC', 'EX-10.1', 'COVER'
                    'size': item.get('size')
                    # Add 'last_modified' if needed: item.get('last_modified')
                }
                if doc_info['name']:
                    documents.append(doc_info)

            logging.info(f"Found {len(documents)} documents in index for {accession_no}")
            return documents

        except Exception as e:
            logging.error(f"Error fetching/parsing index.json for document list ({accession_no}): {e}", exc_info=True)
            return None