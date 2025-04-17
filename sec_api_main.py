import os
import logging
import json
import asyncio # Added asyncio
from datetime import datetime
import sys
from trade_suite.data.sec_api import SECDataFetcher
from dotenv import load_dotenv
import pandas as pd # Added for CSV saving

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()   

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', # Added logger name
    handlers=[
        logging.FileHandler("sec_api_test.log"), # Renamed log file
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__) # Added logger instance

# Ensure the output directory exists - Changed to sec_data_dump
OUTPUT_DIR = "sec_data_dump"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def save_json(data, filename):
    """Helper function to save dictionary data to a JSON file."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # Handle cases where data might not be serializable directly (e.g., set)
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Successfully saved JSON data to {filepath}")
    except Exception as e:
        logger.error(f"Error saving JSON to {filepath}: {e}")

def save_text(content, filename):
    """Helper function to save text content to a file."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Successfully saved text content to {filepath}")
    except Exception as e:
        logger.error(f"Error saving text to {filepath}: {e}")

def save_dataframe_csv(df, filename):
    """Helper function to save a pandas DataFrame to a CSV file."""
    if df is None or df.empty:
        logger.warning(f"DataFrame is empty or None, skipping save for {filename}")
        return
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        df.to_csv(filepath, index=False)
        logger.info(f"Successfully saved DataFrame to {filepath}")
    except Exception as e:
        logger.error(f"Error saving DataFrame to {filepath}: {e}")

def explore_and_save_data(ticker, days_back=365):
    """Fetches various data points for a ticker and saves them for analysis."""
    ticker = ticker.upper()
    logger.info(f"--- Starting data exploration for {ticker} ---")

    # Create SEC data fetcher
    user_agent = os.getenv('SEC_API_USER_AGENT', 'YourAppName (youremail@example.com)') # Provide a default if not set
    if not user_agent or user_agent == 'YourAppName (youremail@example.com)':
         logger.warning("Using default/placeholder User-Agent. Please set SEC_API_USER_AGENT environment variable.")
    fetcher = SECDataFetcher(user_agent=user_agent)

    if not fetcher.api_valid:
        logger.error("SEC API not accessible. Exiting exploration.")
        return

    # 1. Fetch and save raw company submissions
    logger.info(f"Fetching raw submissions for {ticker}...")
    submissions = fetcher.get_company_submissions(ticker, use_cache=False) # Force fetch for exploration
    if submissions:
        save_json(submissions, f"{ticker}_submissions_raw.json")
    else:
        logger.warning(f"Could not fetch submissions for {ticker}.")

    # Fetch filings lists (Form 4, 10-K, 10-Q)
    form_types_to_fetch = {"4": 90, "10-K": 365*2, "10-Q": 365} # Use specific days_back
    filings_data = {}

    for form_type, lookback in form_types_to_fetch.items():
        logger.info(f"Fetching {form_type} filings list for {ticker} (last {lookback} days)...")
        filings = fetcher.get_filings_by_form(ticker, form_type, days_back=lookback, use_cache=False) # Force fetch
        filings_data[form_type] = filings
        if filings:
            save_json(filings, f"{ticker}_{form_type}_filings_list.json")
            logger.info(f"Found {len(filings)} {form_type} filings.")

            # Fetch and save the primary document of the *most recent* filing
            most_recent_filing = filings[0] # Assumes list is sorted descending by date
            accession_no = most_recent_filing.get('accessionNo')
            primary_doc_name = most_recent_filing.get('primaryDocument')
            if accession_no and primary_doc_name:
                logger.info(f"Fetching primary document for {form_type} {accession_no} ({primary_doc_name})...")
                doc_content = fetcher.fetch_filing_document(accession_no, primary_doc_name)
                if doc_content:
                    # Save with appropriate extension if possible
                    file_ext = os.path.splitext(primary_doc_name)[1] or ".html" # Default to .html
                    save_text(doc_content, f"{ticker}_{form_type}_{accession_no}{file_ext}")
                else:
                    logger.warning(f"Could not fetch document for {accession_no}")
        else:
            logger.warning(f"No {form_type} filings found for {ticker} in the lookback period.")

    # Fetch, parse, and save Form 4 transactions
    logger.info(f"Fetching and parsing Form 4 transactions for {ticker} (last {form_types_to_fetch['4']} days)...")
    transactions_df = fetcher.get_recent_insider_transactions(ticker, days_back=form_types_to_fetch['4'], use_cache=False)
    if not transactions_df.empty:
        save_dataframe_csv(transactions_df, f"{ticker}_form4_transactions.csv")
    else:
        logger.warning(f"No parsable Form 4 transactions found for {ticker}.")

    logger.info(f"--- Data exploration finished for {ticker} ---")
    logger.info(f"Check the '{OUTPUT_DIR}' directory for saved files.")

async def test_edgar_api_refactored(ticker="AAPL"):
    """Test the refactored EDGAR API functionality using SECDataFetcher."""
    logger.info(f"--- Starting Refactored EDGAR API Test for {ticker} --- ")
    # Initialize the fetcher
    user_agent = os.getenv('SEC_API_USER_AGENT')
    if not user_agent:
         logger.warning("SEC_API_USER_AGENT environment variable not set. Using default rate limiting, but requests might be slower or blocked.")
         # Use a generic user agent if none is provided, but log warning
         user_agent = "TradeSuiteTester/1.0 (test@example.com)"

    fetcher = SECDataFetcher(user_agent=user_agent)

    # --- Test getting CIK ---
    logger.info(f"[TEST] Getting CIK for {ticker}...")
    cik = await fetcher.get_cik_for_ticker(ticker)
    if cik:
        logger.info(f"SUCCESS: CIK for {ticker}: {cik}")
    else:
        logger.error(f"FAILURE: Failed to get CIK for {ticker}. Aborting further tests.")
        await fetcher.close() # Close client session
        return

    # --- Test getting Company Info ---
    logger.info(f"[TEST] Getting Company Info for {ticker}...")
    # Usually cached, force fetch for testing? Let's use cache for now.
    company_info = await fetcher.get_company_info(ticker, use_cache=True)
    if company_info:
        logger.info(f"SUCCESS: Got company info for {company_info.get('name', ticker)}.")
        save_json(company_info, f"{ticker}_company_info.json")
    else:
        logger.warning(f"WARNING: Failed to get company info for {ticker}.") # Don't abort test

    # --- Test Fetching Specific Filings Lists ---
    filing_tests = {
        "10-K": 730, # 2 years
        "10-Q": 365, # 1 year
        "8-K": 180,  # 6 months
        "4": 90      # 3 months (standard for insider tx)
    }

    for form_type, days_back in filing_tests.items():
        logger.info(f"[TEST] Fetching {form_type} filings list for {ticker} (last {days_back} days)...")
        # Force fetch to test API, not just cache reads
        filings = await fetcher.get_filings_by_form(ticker, form_type, days_back=days_back, use_cache=False)
        if filings:
            logger.info(f"SUCCESS: Found {len(filings)} {form_type} filings.")
            save_json(filings, f"{ticker}_{form_type}_{days_back}d_filings_list.json")
            # Log first few filing details for quick check
            for i, f in enumerate(filings[:3]):
                 logger.info(f"  - Filing {i+1}: Date={f.get('filing_date')}, AccNo={f.get('accession_no')}")
        elif isinstance(filings, list) and not filings:
             logger.info(f"SUCCESS (API): Found 0 {form_type} filings in the lookback period.")
             # Save empty list to indicate test ran
             save_json([], f"{ticker}_{form_type}_{days_back}d_filings_list.json")
        else:
            logger.error(f"FAILURE: Failed to get {form_type} filings list (returned type: {type(filings)}).")

    # --- Test Fetching Recent Insider Transactions ---
    insider_days_back = 90
    logger.info(f"[TEST] Fetching and parsing Form 4 transactions for {ticker} (last {insider_days_back} days)...")
    # Force fetch = False here, as it inherently fetches filings and parses docs if needed
    transactions_list = await fetcher.get_recent_insider_transactions(
        ticker, days_back=insider_days_back, use_cache=True, filing_limit=10 # Limit processing for test speed
    )
    if isinstance(transactions_list, list):
         logger.info(f"SUCCESS: Parsed {len(transactions_list)} Form 4 transactions.")
         # Convert list of dicts to DataFrame for saving
         if transactions_list:
              transactions_df = pd.DataFrame(transactions_list)
              save_dataframe_csv(transactions_df, f"{ticker}_form4_transactions_{insider_days_back}d.csv")
              logger.info(f"  - Example Transaction: {transactions_list[0]}")
         else:
              logger.info("  - No transactions found in the specified period/limit.")
              # Save empty CSV to indicate test ran
              save_dataframe_csv(pd.DataFrame(), f"{ticker}_form4_transactions_{insider_days_back}d.csv")
    else:
        logger.error(f"FAILURE: get_recent_insider_transactions returned type {type(transactions_list)}, expected list.")


    # --- Test Fetching Financial Summary ---
    logger.info(f"[TEST] Fetching financial summary for {ticker}...")
    # Force fetch to test processing, not just cache read
    financial_summary = await fetcher.get_financial_summary(ticker, use_cache=False)
    if financial_summary:
        logger.info(f"SUCCESS: Generated financial summary for {ticker}.")
        save_json(financial_summary, f"{ticker}_financial_summary.json")
        # Log a few summary items
        logger.info(f"  - Revenue: {financial_summary.get('Revenue')}")
        logger.info(f"  - Net Income: {financial_summary.get('NetIncomeLoss')}")
        logger.info(f"  - EPS Basic: {financial_summary.get('EarningsPerShareBasic')}")
    else:
        logger.error(f"FAILURE: Failed to generate financial summary for {ticker}.")


    # --- Cleanup ---
    await fetcher.close() # Close the HTTP client session
    logger.info(f"--- Refactored EDGAR API Test Finished for {ticker} ---")
    logger.info(f"Check the '{OUTPUT_DIR}' directory for saved files.")

async def main():
    """Main async function to run tests."""
    # Test with a primary ticker
    await test_edgar_api_refactored(ticker="AAPL")

    # Optionally test another ticker
    # await test_edgar_api_refactored(ticker="MSFT")

if __name__ == "__main__":
    # Ensure you have a .env file with SEC_API_USER_AGENT="Your Name (your.email@example.com)"
    logger.info("Starting SEC API Test Script...")
    asyncio.run(main())
    logger.info("SEC API Test Script finished.")