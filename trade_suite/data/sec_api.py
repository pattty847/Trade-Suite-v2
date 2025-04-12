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

class SECDataFetcher:
    """
    A comprehensive library for fetching and processing data from SEC EDGAR APIs.
    
    Features:
    - Fetch data for multiple SEC form types (Form 4, 10-K, 10-Q, etc.)
    - Local caching of results to reduce API calls
    - Conversion to pandas DataFrames for easy analysis
    - Rate limiting to comply with SEC API guidelines
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
            user_agent (str): User-Agent string for SEC API requests.
                             If None, will try to read from environment variable SEC_API_USER_AGENT
                             Format should be: "name (email)" e.g., "Market Analysis Tool (user@example.com)"
            cache_dir (str): Directory for storing cached data
            rate_limit_sleep (float): Seconds to wait between API requests
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
        """Get or create the aiohttp session."""
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
    
    def _test_api_access(self) -> bool:
        """Test if the SEC API is accessible with the provided user agent."""
        if not self.user_agent:
            logging.error("Cannot test API access: No User-Agent provided")
            return False
            
        try:
            # Test using Apple's CIK as an example (0000320193)
            test_url = self.SUBMISSIONS_ENDPOINT.format(cik="0000320193")
            logging.info(f"Testing SEC API connection to: {test_url}")
            
            response = self._make_request(test_url)
            
            if response and response.status_code == 200:
                logging.info("SEC API access test successful")
                return True
            else:
                status = response.status_code if response else "No response"
                reason = response.reason if response else "Connection failed"
                logging.error(f"SEC API access test failed: {status} {reason}")
                if response and response.text:
                    logging.error(f"Error details: {response.text[:500]}")
                return False
                
        except Exception as e:
            logging.error(f"Error testing SEC API access: {str(e)}")
            return False
    
    async def _make_request(self, url: str, max_retries: int = 3, headers: Optional[Dict] = None, is_json: bool = True) -> Optional[Union[Dict, str]]:
        """
        Make a rate-limited request to the SEC API.
        
        Args:
            url (str): URL to request
            max_retries (int): Maximum number of retries for failed requests
            headers (Optional[Dict]): Optional headers dictionary to override self.headers
            is_json (bool): Whether to expect and parse JSON response. If False, returns text.
            
        Returns:
            Optional[Union[Dict, str]]: Parsed JSON dictionary or response text, or None if all retries fail.
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
                        try:
                            return await response.json()
                        except json.JSONDecodeError as json_err:
                             logging.error(f"JSON decode error for {url}: {json_err}")
                             # Optionally log the response text that failed
                             try:
                                 text_content = await response.text()
                                 logging.error(f"Response text: {text_content[:500]}")
                             except Exception:
                                 logging.error("Could not get response text after JSON error.")
                             return None # Or raise an error
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
    
    def get_cik_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Get the CIK (Central Index Key) for a ticker symbol.
        
        Args:
            ticker (str): Stock ticker symbol
            
        Returns:
            Optional[str]: 10-digit CIK with leading zeros, or None if not found
        """
        ticker = ticker.upper()
        
        # First check ticker-to-CIK mapping file
        cik = self._load_cik_from_cache(ticker)
        if cik:
            return cik
    
    def _load_cik_from_cache(self, ticker: str) -> Optional[str]:
        """Load CIK from cache file for a ticker."""
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
        """Save a ticker to CIK mapping in the cache file."""
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
    
    def get_company_info(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Get company information using the submissions API.
        
        Args:
            ticker (str): Stock ticker symbol
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            Optional[Dict]: Company information or None if error
        """
        ticker = ticker.upper()
        
        # Try to load from cache first if use_cache is True
        if use_cache:
            cache_data = self._load_company_info_from_cache(ticker)
            if cache_data:
                return cache_data
        
        # Convert ticker to CIK
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot get company info: No CIK found for {ticker}")
            return None
            
        # Get submissions data which includes company info
        submissions_url = self.SUBMISSIONS_ENDPOINT.format(cik=cik)
        
        try:
            response = self._make_request(submissions_url)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get company info for {ticker} (CIK: {cik}): {response.status_code if response else 'No response'}")
                return None
                
            # Parse company data
            company_data = response.json()
            
            # Extract relevant company info
            company_info = {
                'ticker': ticker,
                'cik': cik,
                'name': company_data.get('name'),
                'sic': company_data.get('sic'),
                'sic_description': company_data.get('sicDescription'),
                'address': company_data.get('addresses', {}).get('mailing'),
                'phone': company_data.get('phone'),
                'exchange': company_data.get('exchanges'),
            }
            
            # Cache the company info data
            self._save_company_info_to_cache(ticker, cik, company_info)
            
            return company_info
            
        except Exception as e:
            logging.error(f"Error fetching company info for {ticker} (CIK: {cik}): {str(e)}")
            return None
    
    def _load_company_info_from_cache(self, ticker: str) -> Optional[Dict]:
        """Load company info from cache file for a ticker."""
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
    
    def get_company_submissions(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Get all submissions for a company using the submissions API.
        
        Args:
            ticker (str): Stock ticker symbol
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            Optional[Dict]: Submissions data or None if error
        """
        ticker = ticker.upper()
        
        # Try to load from cache first if use_cache is True
        if use_cache:
            cache_data = self._load_submissions_from_cache(ticker)
            if cache_data:
                return cache_data
        
        # Convert ticker to CIK
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot get submissions: No CIK found for {ticker}")
            return None
            
        # Get submissions data
        submissions_url = self.SUBMISSIONS_ENDPOINT.format(cik=cik)
        
        try:
            response = self._make_request(submissions_url)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get submissions for {ticker} (CIK: {cik}): {response.status_code if response else 'No response'}")
                return None
                
            # Parse submissions data
            submissions_data = response.json()
            
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
        Fetch filings of a specific form type for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            form_type (str): SEC form type (e.g. "4" for Form 4, "10-K", etc.)
            days_back (int): Limit results to filings within this many days
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            List[Dict]: List of filing data records
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
            cik = self.get_cik_for_ticker(ticker)
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
            # primary_document_list = recent_filings.get('primaryDocument', []) # Not needed for target format

            # Ensure all lists have the same length for safe iteration
            min_len = min(len(form_list), len(filing_date_list), len(accession_number_list), len(report_date_list))

            # Filter for specified form type filings within the date range
            for i in range(min_len): # Iterate up to the minimum length
                form = form_list[i]
                filing_date = filing_date_list[i]
                accession_no = accession_number_list[i]
                report_date = report_date_list[i] if i < len(report_date_list) else None # Handle if reportDate list is shorter

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
        """Load filings from cache file for a ticker and form type."""
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
        Fetch insider trading filings (Form 4) for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Limit results to filings within this many days
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            List[Dict]: List of insider filings
        """
        return await self.get_filings_by_form(ticker, "4", days_back, use_cache)
    
    async def fetch_annual_reports(self, ticker: str, days_back: int = 365, 
                            use_cache: bool = True) -> List[Dict]:
        """
        Fetch annual reports (10-K) for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Limit results to filings within this many days
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            List[Dict]: List of 10-K filings
        """
        return await self.get_filings_by_form(ticker, "10-K", days_back, use_cache)
    
    async def fetch_quarterly_reports(self, ticker: str, days_back: int = 365, 
                               use_cache: bool = True) -> List[Dict]:
        """
        Fetch quarterly reports (10-Q) for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Limit results to filings within this many days
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            List[Dict]: List of 10-Q filings
        """
        return await self.get_filings_by_form(ticker, "10-Q", days_back, use_cache)
    
    async def fetch_current_reports(self, ticker: str, days_back: int = 90, 
                             use_cache: bool = True) -> List[Dict]:
        """
        Fetch current reports (8-K) for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Limit results to filings within this many days
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            List[Dict]: List of 8-K filings
        """
        return await self.get_filings_by_form(ticker, "8-K", days_back, use_cache)
    
    async def fetch_form_direct(self, ticker: str, form_type: str, count: int = 1) -> List[Dict]:
        """
        Directly fetch the most recent forms of a specific type for a company.
        
        Args:
            ticker (str): Stock ticker symbol
            form_type (str): Form type (e.g., "10-K", "10-Q", "4")
            count (int): Number of most recent forms to fetch
            
        Returns:
            List[Dict]: List of form data including accession numbers and filing dates
        """
        cik = self.get_cik_for_ticker(ticker)
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
            response = self._make_request(url, headers=temp_headers)
            
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

    async def fetch_filing_document(self, accession_no: str, primary_doc: str = None) -> Optional[str]:
        """
        Fetches the primary document text for a specific filing by accession number.

        If the `primary_doc` filename is provided, it downloads that specific file directly.
        If `primary_doc` is NOT provided, this method first fetches the filing's
        `index.json` to automatically determine the primary document filename,
        then downloads it. This incurs an extra API call compared to
        `download_form_document`.

        Args:
            accession_no (str): Accession number for the filing (dashes optional).
            primary_doc (str, optional): Primary document filename. If None, it will be
                                         looked up via the filing index. Defaults to None.

        Returns:
            Optional[str]: Document text (usually HTML or XML) or None if error or
                           primary document cannot be found.
        """
        # Format accession number for URL (remove dashes)
        accession_no_clean = accession_no.replace('-', '')
        
        # If primary document not provided, fetch the index first to find it
        if not primary_doc:
            index_url = f"https://www.sec.gov/Archives/edgar/data/{accession_no_clean[0:10]}/{accession_no_clean}/index.json"
            
            try:
                response = self._make_request(index_url)
                if not response or response.status_code != 200:
                    logging.error(f"Failed to get index for accession number {accession_no}")
                    return None
                
                # Extract primary document from index
                index_data = response.json()
                primary_doc = index_data.get('primaryDocument', '')
                
                if not primary_doc:
                    logging.error(f"No primary document found for accession number {accession_no}")
                    return None
                    
            except Exception as e:
                logging.error(f"Error getting index for accession number {accession_no}: {str(e)}")
                return None
        
        # Now fetch the actual document
        document_url = f"https://www.sec.gov/Archives/edgar/data/{accession_no_clean[0:10]}/{accession_no_clean}/{primary_doc}"
        
        try:
            response = self._make_request(document_url)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get document for accession number {accession_no}: {response.status_code if response else 'No response'}")
                return None
                
            return response.text
            
        except Exception as e:
            logging.error(f"Error fetching document for accession number {accession_no}: {str(e)}")
            return None
        
    async def process_insider_filings(self, ticker: str, days_back: int = 90) -> pd.DataFrame:
        """
        Process Form 4 filings into a structured DataFrame of individual transactions.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Number of days back to analyze filings
            
        Returns:
            pd.DataFrame: DataFrame of processed insider transactions
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
        Create a summary of insider trading activity for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Number of days back to analyze
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            Dict: Summary of insider trading activity
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
        Generate a formatted text report of insider activity for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Number of days back to analyze
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            str: Formatted text report
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

    async def download_form_xml(self, accession_no: str) -> Optional[str]:
        """
        Download and return the XML file for a Form 4 filing.
        
        Args:
            accession_no (str): Accession number for the filing
            
        Returns:
            Optional[str]: XML content or None if error
        """
        # Format accession number for URL (remove dashes)
        accession_no_clean = accession_no.replace('-', '')
        # Get CIK from the accession number (first 10 digits, no leading zeros needed for URL path here)
        cik_part = accession_no_clean[0:10]
        if not cik_part.isdigit():
            logging.error(f"Could not extract valid CIK part from accession number: {accession_no}")
            return None

        # First get the index to find the XML file
        index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_part}/{accession_no_clean}/index.json"

        try:
            # Prepare headers for www.sec.gov
            temp_headers = self.headers.copy()
            temp_headers['Host'] = 'www.sec.gov'
            logging.info(f"Fetching index.json from {index_url} with headers: {temp_headers}")

            response = self._make_request(index_url, headers=temp_headers)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get index for accession number {accession_no}. Status: {response.status_code if response else 'No Response'}, URL: {index_url}")
                return None

            # Parse the index to find XML files
            index_data = response.json()

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
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_part}/{accession_no_clean}/{xml_file}"
            logging.info(f"Attempting to download XML file: {xml_url}")

            # Use the same www.sec.gov headers
            response = self._make_request(xml_url, headers=temp_headers)
            if not response or response.status_code != 200:
                logging.error(f"Failed to get XML file '{xml_file}' for accession number {accession_no}. Status: {response.status_code if response else 'No Response'}")
                return None

            return response.text
        
        except json.JSONDecodeError as e:
             logging.error(f"Error decoding index.json for {accession_no}: {e}. URL: {index_url}")
             if response: logging.error(f"Response text: {response.text[:500]}")
             return None
        except Exception as e:
            logging.error(f"Error downloading XML file for accession number {accession_no}: {str(e)}")
            return None
    
    async def download_all_form_documents(self, accession_no: str, output_dir: str = None) -> Dict[str, str]:
        """
        Download all documents for a filing by accession number.
        
        Args:
            accession_no (str): Accession number for the filing
            output_dir (str): Directory to save documents to (optional)
            
        Returns:
            Dict[str, str]: Dictionary of filenames to file contents
        """
        # Format accession number for URL (remove dashes)
        accession_no_clean = accession_no.replace('-', '')
        
        # Create output directory if specified
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # First get the index to find all files
        index_url = f"https://www.sec.gov/Archives/edgar/data/{accession_no_clean[0:10]}/{accession_no_clean}/index.json"
        
        try:
            response = self._make_request(index_url)
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
                
                response = self._make_request(file_url)
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
    
    async def process_form4_filing(self, accession_no: str) -> List[Dict]:
        """
        Process a single Form 4 filing into structured transaction data.
        
        Args:
            accession_no (str): Accession number for the filing
            
        Returns:
            List[Dict]: List of transaction dictionaries
        """
        # Download the XML
        xml_content = await self.download_form_xml(accession_no)
        
        if not xml_content:
            return []
        
        # Parse the XML
        return self.parse_form4_xml(xml_content)
    
    async def get_recent_insider_transactions(self, ticker: str, days_back: int = 90, 
                                     use_cache: bool = True) -> List[Dict]:
        """
        Get all recent insider transactions for a ticker, formatted for UI.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Number of days back to analyze
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            List[Dict]: List of insider transactions formatted for the UI.
        """
        ticker = ticker.upper()
        
        # Get all Form 4 filing metadata first
        # We use the refactored get_filings_by_form to get accession numbers etc.
        filings = await self.fetch_insider_filings(ticker, days_back, use_cache)
        
        if not filings:
            return [] # Return empty list directly
        
        # Process each filing to get transaction details and format for UI
        all_ui_transactions = [] 
        
        for filing_meta in filings: # Use a more descriptive name
            accession_no = filing_meta.get('accession_no')
            if not accession_no:
                logging.warning(f"Skipping filing for {ticker} due to missing accession number.")
                continue
            
            # Process the XML to get detailed transactions for this filing
            # process_form4_filing returns List[Dict] with parsed data
            parsed_transactions = await self.process_form4_filing(accession_no)
            
            if not parsed_transactions:
                logging.debug(f"No transactions parsed for {ticker}, accession: {accession_no}")
                continue

            # Get CIK for URL construction (ideally from parsed data)
            # Assuming all transactions in a filing share the same issuer CIK
            issuer_cik = parsed_transactions[0].get('issuer_cik', 'N/A')
            if issuer_cik == 'N/A' or not issuer_cik:
                # Fallback: try getting CIK from ticker if parse failed to get it
                logging.warning(f"Issuer CIK not found in parsed data for {accession_no}, attempting fallback.")
                issuer_cik = self.get_cik_for_ticker(ticker) 
                if not issuer_cik:
                     logging.error(f"Cannot construct form URL for {accession_no}: CIK unavailable.")
                     # Decide whether to skip or proceed without URL
                     # continue # Option: skip transactions without a URL
                     issuer_cik = "N/A" # Option: proceed without URL
            
            # Clean accession number once for the filing
            accession_no_cleaned = accession_no.replace('-', '')
            form_url = "N/A" # Default if CIK is unavailable
            if issuer_cik != "N/A" and issuer_cik:
                 form_url = f"https://www.sec.gov/Archives/edgar/data/{issuer_cik}/{accession_no_cleaned}/"

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
                    'form_url': form_url # Use the constructed URL
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
        Analyze insider transactions for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            days_back (int): Number of days back to analyze
            use_cache (bool): Whether to use cached data if available
            
        Returns:
            Dict: Dictionary of analysis results
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
        """Fetches company facts (XBRL data) from the SEC API.

        Args:
            ticker (str): Stock ticker symbol.
            use_cache (bool): Whether to use cached data if available.

        Returns:
            Optional[Dict]: Dictionary containing company facts, or None if error.
                           The structure includes keys like 'cik', 'entityName',
                           and 'facts' (which holds us-gaap, dei, etc. taxonomies).
        """
        ticker = ticker.upper()
        
        # Try cache first
        if use_cache:
            cached_data = self._load_company_facts_from_cache(ticker)
            if cached_data:
                return cached_data
                
        # Get CIK
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            logging.error(f"Cannot get company facts: No CIK found for {ticker}")
            return None
            
        # Construct URL
        facts_url = self.COMPANY_FACTS_ENDPOINT.format(cik=cik)
        logging.info(f"Fetching company facts from: {facts_url}")
        
        try:
            response = self._make_request(facts_url)
            company_facts_data = await self._make_request(facts_url, is_json=True)
            
            if company_facts_data is None:
                logging.error(f"Failed to get company facts for {ticker} (CIK: {cik})")
                return None
                
            # Cache the result
            self._save_company_facts_to_cache(ticker, cik, company_facts_data)
            
            return company_facts_data

        except json.JSONDecodeError as e:
            logging.error(f"Error decoding company facts JSON for {ticker}: {str(e)}")
            if response: logging.error(f"Response text that failed decoding: {response.text[:1000]}")
            return None
        except Exception as e:
            logging.error(f"Error fetching company facts for {ticker} (CIK: {cik}): {str(e)}")
            return None

    # Helper function to get the latest value for a specific fact
    def _get_latest_fact_value(self, facts_data: Dict, taxonomy: str, concept_tag: str) -> Optional[Dict]:
        """Internal helper to find the latest reported value for a specific XBRL concept.

        Args:
            facts_data (Dict): The raw dictionary from get_company_facts.
            taxonomy (str): The taxonomy (e.g., 'us-gaap', 'dei').
            concept_tag (str): The specific XBRL concept tag (e.g., 'Assets').

        Returns:
            Optional[Dict]: A dictionary containing the latest fact details 
                            (value, unit, end_date, fy, fp) or None if not found.
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
        """Calculates key financial ratios from extracted summary metrics."""
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
        """Generates a flat summary of key financial metrics using the latest 
        available data, formatted for the UI.

        Args:
            ticker (str): Stock ticker symbol.
            use_cache (bool): Whether to use cached company facts data.

        Returns:
            Optional[Dict]: A flat dictionary summarizing key metrics required by the UI,
                            or None if facts aren't available or key data is missing.
                            Keys include: ticker, entityName, cik, source_form, period_end,
                            revenue, net_income, eps, assets, liabilities, equity, 
                            operating_cash_flow, investing_cash_flow, financing_cash_flow.
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
        """Closes the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logging.info("SECDataFetcher aiohttp session closed.")
        self._session = None # Ensure it's reset