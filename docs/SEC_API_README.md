# SEC Data Fetcher Documentation

## Overview

The `SECDataFetcher` class (`sec_api.py`) provides a Python interface for interacting with the SEC EDGAR APIs. Its primary goal is to fetch, cache, and process financial data and filings for publicly traded companies, making the data more accessible for analysis.

## Key Features Implemented

*   **CIK Lookup:** Converts ticker symbols to SEC Central Index Keys (CIKs) using a local cache (`data/edgar/ticker_cik_map.json`).
*   **Company Information:** Fetches basic company details (name, SIC, address, etc.) via the submissions endpoint.
*   **Filing Lists:** Retrieves lists of recent filings for specific form types (e.g., Form 4, 10-K, 10-Q, 8-K) using the submissions endpoint.
*   **Company Facts (XBRL Data):** Fetches aggregated XBRL data from the `/api/xbrl/companyfacts/` endpoint, providing structured access to reported financial metrics.
*   **Financial Summary:** Processes the raw company facts to extract the latest values for key financial metrics (Revenue, Net Income, Assets, Liabilities, Equity, etc.).
*   **Financial Ratio Calculation:** Automatically calculates key financial ratios and margins (Current Ratio, Debt-to-Equity, Gross Profit Margin, Operating Profit Margin, Net Profit Margin) based on the extracted financial summary metrics, ensuring data is from the same reporting period.
*   **Form 4 Fetching & Parsing:** 
    *   Downloads the specific XML file associated with a Form 4 filing.
    *   Parses the Form 4 XML using `xml.etree.ElementTree` to extract detailed transaction information (non-derivative and derivative) into a structured format.
*   **Document Download:** Provides methods to download specific filing documents (e.g., the primary `.htm` file for a 10-K or the `.xml` for a Form 4) directly from the SEC archives.
*   **Caching:** Implements local file caching for API responses (submissions, facts, filings lists) to reduce redundant API calls and respect SEC rate limits.
*   **Rate Limiting:** Includes basic rate limiting (`time.sleep`) between requests.

## Basic Usage

1.  **Configuration:** Ensure you have a `.env` file in the root directory containing your SEC User-Agent: `SEC_API_USER_AGENT="YourAppName (youremail@example.com)"`. The SEC requires a descriptive User-Agent for API access.
2.  **Initialization:** Create an instance of the `SECDataFetcher` class.
3.  **Calling Methods:** Use the various methods (`get_financial_summary`, `get_recent_insider_transactions`, `fetch_form_direct`, `download_form_document`, etc.) to retrieve the desired data.

See `sec_api_main.py` for example usage patterns, including how to fetch data, save it to files, and test different functionalities.

## Future Work & Potential Improvements

*   **Robust 8-K Parsing:** Implement logic to download 8-K filing documents (likely HTML) and parse their content to extract specific event details (e.g., Item 1.01 Entry into a Material Definitive Agreement, Item 5.02 Departure of Directors or Certain Officers).
*   **10-K/10-Q Text Section Extraction:** Add functionality to download 10-K/10-Q documents (HTML) and parse them (e.g., using BeautifulSoup or lxml) to extract specific qualitative sections like "Management's Discussion and Analysis" (MD&A) or "Risk Factors".
*   **Form 4 Footnote Integration:** Enhance the `parse_form4_xml` method to also parse the `<footnotes>` section and potentially link footnote text back to the relevant transactions (e.g., for explaining prices or ownership details).
*   **More Sophisticated Period Matching:** Improve the period matching logic in `_calculate_ratios` to handle cases where `end_date` might differ slightly but `fy` (fiscal year) and `fp` (fiscal period) match, potentially allowing for more ratio calculations.
*   **Historical Data Fetching:** Currently, `get_financial_summary` focuses on the *latest* available fact. Add methods to retrieve historical time series data for specific XBRL concepts (e.g., quarterly revenue over the last 3 years) using the `companyconcept` API endpoint or by processing the full `companyfacts` data.
*   **Error Handling & Resilience:** Further improve error handling for API request failures, unexpected data formats, or missing data points.
*   **Async Operations:** For fetching data for multiple tickers, consider using asynchronous requests (`aiohttp`) to improve performance. 