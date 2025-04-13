# SECDataFetcher Class Documentation

## Overview

The `SECDataFetcher` class is an asynchronous Python library designed to interact with the U.S. Securities and Exchange Commission's (SEC) EDGAR APIs. It provides a comprehensive interface for fetching, caching, and processing various types of SEC data, including company information, filings, financial facts (XBRL), and specific documents.

This class aims to simplify interactions with SEC EDGAR by handling rate limiting, caching, CIK lookups, and basic data parsing (e.g., Form 4 XML).

## Features

*   **Asynchronous Operations:** Uses `aiohttp` for efficient, non-blocking network requests.
*   **CIK Lookup:** Retrieves the Central Index Key (CIK) for a given ticker symbol.
*   **Endpoint Integration:** Interacts with key SEC endpoints:
    *   `submissions`: Company filing history and metadata.
    *   `companyfacts`: Standardized XBRL financial data.
    *   `companyconcept`: Specific XBRL concepts over time (not heavily used in current implementation).
    *   EDGAR Archives: Direct access to filing documents (HTML, XML, etc.).
*   **Caching:** Implements local file-based caching for API responses (submissions, CIK map, filings, facts) to reduce redundant requests and improve performance. Cache files are typically stored in `data/edgar/` subdirectories.
*   **Rate Limiting:** Automatically handles SEC API rate limits (10 requests/second) using a configurable delay and basic exponential backoff for 429 errors.
*   **Form Filtering:** Fetches lists of specific filing types (e.g., Form 4, 8-K, 10-K, 10-Q) within a specified date range.
*   **Document Retrieval:** Downloads specific documents from filings, including automatic primary document detection (HTML/XML) from index pages.
*   **Form 4 Processing:**
    *   Downloads Form 4 XML.
    *   Parses XML using `xml.etree.ElementTree` to extract transaction details (non-derivative and derivative).
    *   Provides methods to fetch and analyze recent insider transactions.
*   **Financial Data:**
    *   Fetches standardized `companyfacts` data.
    *   Extracts the latest values for key financial metrics defined in `KEY_FINANCIAL_SUMMARY_METRICS`.
    *   Generates a flattened financial summary suitable for UI display.
*   **Error Handling & Logging:** Uses the `logging` module to report informational messages, warnings, and errors during operation.

## Prerequisites

*   **Environment Variable:** The class requires a User-Agent string for making requests to the SEC API. This should be set as an environment variable:
    *   `SEC_API_USER_AGENT`: Format should be `"YourAppName YourContactEmail@example.com"`. If not set, the class will log a warning, and requests might fail.

## Installation

This class is part of the `Trade-Suite-v2` project and does not require separate installation beyond the project's dependencies (like `requests`, `pandas`, `aiohttp`, `python-dotenv`).

## Initialization

```python
import asyncio
from trade_suite.data.sec_api import SECDataFetcher

# Ensure environment variable SEC_API_USER_AGENT is set
# Example: SEC_API_USER_AGENT="MyTradingTool contact@example.com"

async def main():
    # Initialize the fetcher
    fetcher = SECDataFetcher(
        # user_agent="Optional: Override env var",
        cache_dir="data/edgar", # Default cache location
        rate_limit_sleep=0.1   # Default sleep interval (10 req/sec)
    )

    # Use the fetcher...
    # await fetcher.get_company_info("AAPL")

    # Close the session when done
    await fetcher.close()

if __name__ == "__main__":
    asyncio.run(main())
```

**Important:** Remember to call `await fetcher.close()` when your application finishes to properly close the underlying `aiohttp` session.

## Key Methods & Usage Examples

**(Note: All public data-fetching methods are `async` and need to be `await`ed.)**

### 1. Getting CIK

```python
cik = await fetcher.get_cik_for_ticker("MSFT")
# Returns: '0000789019' (or None if not found)
```

### 2. Fetching Company Information

```python
# Basic company profile (name, CIK, SIC, address)
info = await fetcher.get_company_info("AAPL")

# Full submissions data (includes recent filings metadata)
submissions = await fetcher.get_company_submissions("GOOGL")
```

### 3. Fetching Filings by Form Type

```python
# Get recent Form 4 (insider) filings for the last 90 days
form4_filings = await fetcher.get_filings_by_form("TSLA", form_type="4", days_back=90)
# Or using the convenience method:
form4_filings_alt = await fetcher.fetch_insider_filings("TSLA", days_back=90)

# Get recent 8-K (current report) filings
form8k_filings = await fetcher.fetch_current_reports("NVDA", days_back=30)

# Get 10-K (annual report) filings for the last 2 years
form10k_filings = await fetcher.fetch_annual_reports("AMZN", days_back=730)

# Get 10-Q (quarterly report) filings for the last year
form10q_filings = await fetcher.fetch_quarterly_reports("META", days_back=365)

# Fetch filings for multiple tickers
multi_results = await fetcher.fetch_multiple_tickers(["AAPL", "MSFT"], form_type="4", days_back=60)
```
*Result Format:* Each filing in the returned list is a dictionary containing keys like `accession_no`, `filing_date`, `form`, `report_date`, `url` (to filing index), `primary_document` (filename).

### 4. Fetching Specific Filing Documents

```python
# Example: Fetch the primary document for a specific filing
# accession_no might come from get_filings_by_form result
accession_no = "0000320193-23-000106" # Example Apple 10-K
ticker = "AAPL" # Providing ticker helps ensure correct CIK for URL

# Let the method try to find the primary doc (e.g., .htm, .xml)
document_content_auto = await fetcher.fetch_filing_document(accession_no, ticker=ticker)

# Or, specify the exact document name if known
primary_doc_name = "aapl-20230930.htm" # Example from Apple 10-K
document_content_specific = await fetcher.fetch_filing_document(accession_no, primary_doc=primary_doc_name, ticker=ticker)

# Download just the Form 4 XML (if available)
form4_accession = "0001209191-24-039873" # Example Form 4
form4_ticker = "NVDA"
xml_content = await fetcher.download_form_xml(form4_accession, ticker=form4_ticker)

# Get a list of all documents within a filing
doc_list = await fetcher.get_filing_documents_list(accession_no, ticker=ticker)
```

### 5. Processing Form 4 (Insider Transactions)

```python
# 1. Get recent Form 4 filings metadata (as shown above)
form4_filings = await fetcher.fetch_insider_filings("MSFT", days_back=90)

# 2. Process a specific filing's XML to get transactions
if form4_filings:
    acc_no = form4_filings[0]['accession_no']
    transactions = await fetcher.process_form4_filing(acc_no, ticker="MSFT")
    # transactions is a list of dicts, each representing one transaction line

# 3. Get all recent transactions formatted for UI display
# This fetches metadata, downloads/parses XML for recent filings (limit applies),
# and formats the output.
ui_transactions = await fetcher.get_recent_insider_transactions("MSFT", days_back=90)
# ui_transactions is list of dicts with keys: 'filer', 'date', 'type', 'shares', 'price', 'value', 'form_url'

# 4. Perform basic analysis on transactions
analysis = await fetcher.analyze_insider_transactions("MSFT", days_back=90)
# analysis is a dict with keys: 'total_transactions', 'buy_count', 'sell_count', 'net_value', 'owners', etc.
```

### 6. Fetching Financial Data (XBRL Facts)

```python
# Get the raw company facts JSON data
facts_data = await fetcher.get_company_facts("GOOG")

# Get a flattened summary of key metrics for the UI
financial_summary = await fetcher.get_financial_summary("GOOG")
# financial_summary is a flat dict with keys like 'ticker', 'entityName', 'cik',
# 'source_form', 'period_end', 'revenue', 'net_income', 'assets', etc.
# Values are extracted from the latest relevant filing in company facts.
```

## Caching

*   API responses are cached locally in the directory specified by `cache_dir` (default: `data/edgar`).
*   Subdirectories are used for different data types (`submissions`, `insider`, `forms`, `facts`, `reports`).
*   Cache filenames typically include the ticker, data type, and timestamp (e.g., `AAPL_submissions_20240715.json`, `MSFT_4_20240715.json`).
*   Methods generally check for a cache file from the current day before making a network request if `use_cache=True` (the default).
*   The Ticker-CIK map (`ticker_cik_map.json`) is cached and updated less frequently.

## Rate Limiting

*   The SEC EDGAR API enforces a rate limit (currently 10 requests per second).
*   `SECDataFetcher` enforces this by waiting at least `rate_limit_sleep` seconds (default 0.1) between requests.
*   If a `429 Too Many Requests` error is received, the class automatically waits using exponential backoff (1s, 3s, 5s...) before retrying up to `max_retries` times (default 3).

## Error Handling

*   The class uses Python's `logging` module. Ensure logging is configured in your application to see output.
*   Methods generally return `None` or empty lists/dictionaries upon failure (e.g., network error, data not found, parsing error). Errors are logged.

## Closing the Session

It is crucial to close the `aiohttp` session when done to release resources.

```python
await fetcher.close()
```

## Future Development / Modularity

This class has grown quite large and encompasses many distinct functionalities (CIK lookup, filing fetching, document downloading, XML parsing, facts processing). Future refactoring could break this down into smaller, more focused classes or modules (e.g., a `FilingFetcher`, a `DocumentDownloader`, a `Form4Parser`, a `CompanyFactsProcessor`) potentially managed by a higher-level facade or used independently. This would improve maintainability and testability. 