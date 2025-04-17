# SEC API Module Structure

This directory contains the refactored components for interacting with the SEC EDGAR APIs. The original monolithic `SECDataFetcher` class has been broken down into several specialized classes, each handling a distinct part of the process.

## Core Components

1.  **`sec_api.py` (`SECDataFetcher` class)**:
    *   Acts as the primary **facade** and **orchestrator**.
    *   Initializes all other components (`SecHttpClient`, `SecCacheManager`, `FilingDocumentHandler`, etc.).
    *   Provides the main public interface for users of the library (e.g., `get_company_info`, `fetch_insider_filings`, `get_financial_summary`).
    *   Handles core logic like CIK lookup (`get_cik_for_ticker`) and fetching general submission/filing list data (`get_company_submissions`, `get_filings_by_form`).
    *   Delegates specific tasks (HTTP requests, caching, document downloading, Form 4 processing, financial data processing) to the appropriate specialized component.

2.  **`http_client.py` (`SecHttpClient` class)**:
    *   Responsible for all **HTTP interactions** with SEC endpoints.
    *   Manages the `aiohttp.ClientSession`.
    *   Implements rate limiting based on SEC guidelines (10 requests/second).
    *   Handles request retries with exponential backoff.
    *   Manages request headers, including the crucial `User-Agent`.
    *   Provides a core `make_request` method used by other components.

3.  **`cache_manager.py` (`SecCacheManager` class)**:
    *   Handles all **filesystem caching** logic.
    *   Manages the cache directory structure (`data/edgar/` by default, with subdirectories like `mappings`, `submissions`, `forms`, `facts`).
    *   Provides methods for loading and saving different types of data (CIK map, submissions, filings, facts) with appropriate timestamping and freshness checks.
    *   Uses standardized methods (`load_data`, `save_data`) internally for different data types.

4.  **`document_handler.py` (`FilingDocumentHandler` class)**:
    *   Specializes in interacting with the **SEC Archives** (`www.sec.gov/Archives/`).
    *   Fetches the list of documents within a filing (`get_filing_documents_list` using `index.json`).
    *   Downloads specific documents by filename (`download_form_document`).
    *   Includes logic to find the primary document (`_find_primary_document_name`) within a filing by checking `index.json` and falling back to parsing `index.htm`.
    *   Provides methods to fetch the content of the primary document (`fetch_filing_document`) or specifically the XML document (`download_form_xml`).
    *   Can download all documents in a filing concurrently (`download_all_form_documents`).
    *   Relies on `SecHttpClient` for downloads and the CIK lookup function provided by `SECDataFetcher`.

5.  **`form4_processor.py` (`Form4Processor` class)**:
    *   Contains all logic specific to **SEC Form 4 (Insider Transactions)**.
    *   Parses Form 4 XML content into structured data (`parse_form4_xml`).
    *   Orchestrates the download and parsing of a single filing (`process_form4_filing`).
    *   Fetches metadata for recent filings (using the function passed from `SECDataFetcher`), processes multiple filings, and formats results for UI display (`get_recent_insider_transactions`).
    *   Performs analysis on transactions using `pandas` (`analyze_insider_transactions`).
    *   Holds Form 4 specific constants (`TRANSACTION_CODE_MAP`, etc.).
    *   Depends on `FilingDocumentHandler` to get XML content and the filing metadata fetching function from `SECDataFetcher`.

6.  **`financial_processor.py` (`FinancialDataProcessor` class)**:
    *   Handles data extracted from the **Company Facts API** (`/api/xbrl/companyfacts/`).
    *   Contains logic to find the latest reported value for specific XBRL tags (`_get_latest_fact_value`).
    *   Orchestrates fetching the raw facts data (via the function passed from `SECDataFetcher`) and extracting key metrics into a flattened dictionary suitable for the UI (`get_financial_summary`).
    *   Holds the mapping of desired summary metrics to their XBRL tags (`KEY_FINANCIAL_SUMMARY_METRICS`).
    *   Includes a placeholder for potential future financial ratio calculations (`_calculate_ratios`).

## Interaction Flow (Example: Getting Financial Summary)

1.  User calls `SECDataFetcher.get_financial_summary(ticker='AAPL')`.
2.  `SECDataFetcher` delegates this call to `FinancialDataProcessor.get_financial_summary(ticker='AAPL')`.
3.  `FinancialDataProcessor` needs raw facts, so it calls the injected `fetch_facts_func` (which points to `SECDataFetcher.get_company_facts`).
4.  `SECDataFetcher.get_company_facts` checks the cache via `SecCacheManager.load_data(ticker='AAPL', data_type='facts')`.
5.  If cache miss:
    *   `SECDataFetcher.get_company_facts` calls `SECDataFetcher.get_cik_for_ticker('AAPL')`.
        *   `get_cik_for_ticker` checks cache via `SecCacheManager.load_cik('AAPL')`.
        *   If cache miss, `get_cik_for_ticker` calls `_fetch_and_cache_cik_map`.
            *   `_fetch_and_cache_cik_map` uses `SecHttpClient.make_request` to get the map.
            *   `_fetch_and_cache_cik_map` uses `SecCacheManager.save_cik_map` to store it.
        *   `get_cik_for_ticker` returns the CIK.
    *   `SECDataFetcher.get_company_facts` constructs the facts URL.
    *   `SECDataFetcher.get_company_facts` calls `SecHttpClient.make_request` to fetch the facts data.
    *   `SECDataFetcher.get_company_facts` uses `SecCacheManager.save_data` to cache the result.
6.  `SECDataFetcher.get_company_facts` returns the raw facts JSON to `FinancialDataProcessor`.
7.  `FinancialDataProcessor` parses the facts JSON using `_get_latest_fact_value` for each required metric.
8.  `FinancialDataProcessor` formats the results into a summary dictionary.
9.  `FinancialDataProcessor.get_financial_summary` returns the summary dictionary back through `SECDataFetcher` to the original caller.

This modular approach separates concerns, making the code easier to understand, test, and maintain. 