# SECDataFetcher Methods

## `async analyze_insider_transactions`

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

---

## `async close`

Closes the underlying aiohttp ClientSession if it's open.

---

## `async download_all_form_documents`

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

---

## `async download_form_document`

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

---

## `async download_form_xml`

Downloads the primary XML document (typically for Form 4) for a given filing.

It first fetches the filing's `index.json` to identify the correct XML filename
(looking for patterns like `form4.xml`, `wk-form4_*.xml`, etc.) and then downloads that file.

Args:
    accession_no (str): The SEC filing accession number (dashes optional).
    ticker (str, optional): The stock ticker symbol of the *issuer*. Used to find the correct CIK
                            for the URL path. Defaults to None (will attempt CIK from accession no).

Returns:
    Optional[str]: The content of the XML file as a string, or None if not found or error.

---

## `async fetch_annual_reports`

Convenience method to fetch Form 10-K (annual report) filings.

Calls `get_filings_by_form` with `form_type="10-K"`.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int, optional): Number of past days to include filings from. Defaults to 365.
    use_cache (bool, optional): Whether to use cached data. Defaults to True.
    
Returns:
    List[Dict]: List of 10-K filing data dictionaries.

---

## `async fetch_current_reports`

Convenience method to fetch Form 8-K (current report) filings.

Calls `get_filings_by_form` with `form_type="8-K"`.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int, optional): Number of past days to include filings from. Defaults to 90.
    use_cache (bool, optional): Whether to use cached data. Defaults to True.
    
Returns:
    List[Dict]: List of 8-K filing data dictionaries.

---

## `async fetch_filing_document`

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

---

## `async fetch_form_direct`

DEPRECATED/Potentially Unreliable: Directly fetch metadata for the most recent forms of a specific type.
Relies on synchronous requests within an async method, which is problematic.
Prefer `get_filings_by_form`.

Args:
    ticker (str): Stock ticker symbol.
    form_type (str): Form type (e.g., "10-K", "10-Q", "4").
    count (int): Number of most recent forms to fetch.
    
Returns:
    List[Dict]: List of form data including accession numbers and filing dates.

---

## `async fetch_insider_filings`

Convenience method to fetch Form 4 (insider trading) filings.

Calls `get_filings_by_form` with `form_type="4"`.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int, optional): Number of past days to include filings from. Defaults to 90.
    use_cache (bool, optional): Whether to use cached data. Defaults to True.
    
Returns:
    List[Dict]: List of Form 4 filing data dictionaries.

---

## `async fetch_multiple_tickers`

Fetch filings for multiple tickers.

Args:
    tickers (List[str]): List of stock ticker symbols
    form_type (str): SEC form type to fetch
    days_back (int): Limit results to filings within this many days
    use_cache (bool): Whether to use cached data if available
    
Returns:
    Dict[str, List]: Dictionary with tickers as keys and lists of filings as values

---

## `async fetch_quarterly_reports`

Convenience method to fetch Form 10-Q (quarterly report) filings.

Calls `get_filings_by_form` with `form_type="10-Q"`.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int, optional): Number of past days to include filings from. Defaults to 365.
    use_cache (bool, optional): Whether to use cached data. Defaults to True.
    
Returns:
    List[Dict]: List of 10-Q filing data dictionaries.

---

## `async generate_insider_report`

DEPRECATED/Placeholder: Generates a text report based on filing counts, not actual transactions.
Uses deprecated `summarize_insider_activity`.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int): Number of days back to analyze.
    use_cache (bool): Whether to use cached data if available.
    
Returns:
    str: Formatted text report (based on filing counts only).

---

## `async get_cik_for_ticker`

Retrieves the 10-digit CIK (Central Index Key) for a given stock ticker symbol.

First attempts to load the CIK from a local cache (`ticker_cik_map.json`).
If not found in cache, fetches the official SEC `company_tickers.json` mapping,
updates the cache, and then attempts to retrieve the CIK again.

Args:
    ticker (str): The stock ticker symbol (case-insensitive).
    
Returns:
    Optional[str]: The 10-digit CIK string with leading zeros if found, otherwise None.

---

## `async get_company_facts`

Fetches company facts (XBRL data) from the SEC's `companyfacts` API endpoint.

This endpoint provides standardized financial data extracted from company filings.
The data is structured by taxonomy (e.g., us-gaap, dei) and concept tag.
Uses caching by default.

Args:
    ticker (str): Stock ticker symbol.
    use_cache (bool, optional): Whether to use cached data if available. Defaults to True.
    
Returns:
    Optional[Dict]: The raw company facts JSON data as a dictionary, including keys
                   like 'cik', 'entityName', and 'facts'. Returns None if an error occurs.

---

## `async get_company_info`

Fetches basic company information using the SEC submissions endpoint.

This data includes name, CIK, SIC description, address, etc.
Uses caching by default.

Args:
    ticker (str): The stock ticker symbol.
    use_cache (bool, optional): Whether to use cached data if available and recent.
                               Defaults to True.
    
Returns:
    Optional[Dict]: A dictionary containing company information, or None if an error occurs.

---

## `async get_company_submissions`

Fetches the complete submissions data for a company from the SEC API.

The submissions data contains details about all filings, including recent ones.
Uses caching by default (checks for cache file from the current day).

Args:
    ticker (str): The stock ticker symbol.
    use_cache (bool, optional): Whether to use cached data if available and recent.
                               Defaults to True.
    
Returns:
    Optional[Dict]: The complete submissions JSON data as a dictionary, or None if an error occurs.

---

## `async get_filing_documents_list`

Fetches the list of documents available within a specific filing.

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

---

## `async get_filings_by_form`

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

---

## `async get_financial_summary`

Generates a flattened summary of key financial metrics required by the UI.

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

---

## `async get_recent_insider_transactions`

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

---

## `parse_form4_xml`

Parses Form 4 XML content into structured transaction data using ElementTree.

Args:
    xml_content (str): XML content of Form 4.

Returns:
    List[Dict]: List of transaction dictionaries.

---

## `async process_form4_filing`

Downloads and parses a single Form 4 XML filing into structured transaction data.

Calls `download_form_xml` to get the content and `parse_form4_xml` to process it.

Args:
    accession_no (str): Accession number for the Form 4 filing.
    ticker (str, optional): The stock ticker symbol of the *issuer*, passed to `download_form_xml`
                            to help construct the correct URL. Defaults to None.

Returns:
    List[Dict]: A list of dictionaries, each representing a transaction parsed from the form.
                Returns an empty list if download or parsing fails.

---

## `async process_insider_filings`

DEPRECATED/Placeholder: Processes Form 4 filings metadata into a basic DataFrame.
Does NOT currently fetch or parse the actual transaction details from the forms.
Prefer `get_recent_insider_transactions` for actual transaction data.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int): Number of days back to analyze filings.
    
Returns:
    pd.DataFrame: DataFrame containing basic metadata of Form 4 filings.

---

## `async summarize_insider_activity`

DEPRECATED/Placeholder: Creates a summary based only on the *count* of Form 4 filings.
Does NOT analyze actual transaction data (buy/sell counts or values).
Prefer `analyze_insider_transactions` for meaningful analysis.

Args:
    ticker (str): Stock ticker symbol.
    days_back (int): Number of days back to analyze.
    use_cache (bool): Whether to use cached data if available.
    
Returns:
    Dict: Summary containing total filings count and basic metadata.

---

## `__init__`

Initialize the SECDataFetcher.

Args:
    user_agent (str, optional): User-Agent string for SEC API requests.
                     Format: "Sample Company Name AdminContact@example.com".
                     Defaults to None, attempts to read from 'SEC_API_USER_AGENT' env var.
    cache_dir (str, optional): Directory for storing cached data. Defaults to "data/edgar".
    rate_limit_sleep (float, optional): Seconds to wait between API requests. Defaults to 0.1.

---

## `_calculate_ratios`

Placeholder for calculating financial ratios. Currently not fully implemented or used.

---

## `_ensure_directories`

Ensure all necessary directories exist.

---

## `async _fetch_and_cache_cik_map`

Fetches the official Ticker-CIK map from SEC and caches it.

---

## `_get_latest_fact_value`

Internal helper to find the latest reported value for a specific XBRL concept
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

---

## `async _get_session`

Lazily initializes and returns the aiohttp ClientSession.

---

## `_load_cik_from_cache`

Loads a CIK from the `ticker_cik_map.json` cache file.

---

## `_load_company_facts_from_cache`

Load company facts from the most recent cache file.

---

## `_load_company_info_from_cache`

Loads company info from the most recent cache file for the ticker.

---

## `_load_filings_from_cache`

Loads cached filtered filings for a specific ticker and form type from today.

---

## `_load_submissions_from_cache`

Load submissions data from cache file for a ticker.

---

## `async _make_request`

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

---

## `_save_cik_to_cache`

Saves or updates a ticker-CIK mapping in the `ticker_cik_map.json` cache file.

---

## `_save_company_facts_to_cache`

Save company facts data to a timestamped cache file.

---

## `_save_company_info_to_cache`

Save company info to a cache file.

---

## `_save_filings_to_cache`

Save filings data to cache file.

---

## `_save_submissions_to_cache`

Save submissions data to cache file.

---

## `async _test_api_access`

Test if the SEC API is accessible with the provided user agent.

---

