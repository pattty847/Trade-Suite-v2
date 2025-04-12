import os
import logging
import json
from datetime import datetime
from trade_suite.data.sec_api import SECDataFetcher
from dotenv import load_dotenv
import pandas as pd # Added for CSV saving

load_dotenv()   

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sec_data_exploration.log"), # Changed log file name
        logging.StreamHandler()
    ]
)

# Ensure the output directory exists
EXPLORATION_DIR = "data/exploration_output"
os.makedirs(EXPLORATION_DIR, exist_ok=True)

def save_json(data, filename):
    """Helper function to save dictionary data to a JSON file."""
    filepath = os.path.join(EXPLORATION_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"Successfully saved data to {filepath}")
    except Exception as e:
        logging.error(f"Error saving JSON to {filepath}: {e}")

def save_text(content, filename):
    """Helper function to save text content to a file."""
    filepath = os.path.join(EXPLORATION_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Successfully saved text content to {filepath}")
    except Exception as e:
        logging.error(f"Error saving text to {filepath}: {e}")

def save_dataframe_csv(df, filename):
    """Helper function to save a pandas DataFrame to a CSV file."""
    filepath = os.path.join(EXPLORATION_DIR, filename)
    try:
        df.to_csv(filepath, index=False)
        logging.info(f"Successfully saved DataFrame to {filepath}")
    except Exception as e:
        logging.error(f"Error saving DataFrame to {filepath}: {e}")

def explore_and_save_data(ticker, days_back=365):
    """Fetches various data points for a ticker and saves them for analysis."""
    ticker = ticker.upper()
    logging.info(f"--- Starting data exploration for {ticker} ---")

    # Create SEC data fetcher
    user_agent = os.getenv('SEC_API_USER_AGENT', 'YourAppName (youremail@example.com)') # Provide a default if not set
    if not user_agent or user_agent == 'YourAppName (youremail@example.com)':
         logging.warning("Using default/placeholder User-Agent. Please set SEC_API_USER_AGENT environment variable.")
    fetcher = SECDataFetcher(user_agent=user_agent)

    if not fetcher.api_valid:
        logging.error("SEC API not accessible. Exiting exploration.")
        return

    # 1. Fetch and save raw company submissions
    logging.info(f"Fetching raw submissions for {ticker}...")
    submissions = fetcher.get_company_submissions(ticker, use_cache=False) # Force fetch for exploration
    if submissions:
        save_json(submissions, f"{ticker}_submissions_raw.json")
    else:
        logging.warning(f"Could not fetch submissions for {ticker}.")

    # Fetch filings lists (Form 4, 10-K, 10-Q)
    form_types_to_fetch = {"4": 90, "10-K": 365*2, "10-Q": 365} # Use specific days_back
    filings_data = {}

    for form_type, lookback in form_types_to_fetch.items():
        logging.info(f"Fetching {form_type} filings list for {ticker} (last {lookback} days)...")
        filings = fetcher.get_filings_by_form(ticker, form_type, days_back=lookback, use_cache=False) # Force fetch
        filings_data[form_type] = filings
        if filings:
            save_json(filings, f"{ticker}_{form_type}_filings_list.json")
            logging.info(f"Found {len(filings)} {form_type} filings.")

            # Fetch and save the primary document of the *most recent* filing
            most_recent_filing = filings[0] # Assumes list is sorted descending by date
            accession_no = most_recent_filing.get('accessionNo')
            primary_doc_name = most_recent_filing.get('primaryDocument')
            if accession_no and primary_doc_name:
                logging.info(f"Fetching primary document for {form_type} {accession_no} ({primary_doc_name})...")
                doc_content = fetcher.fetch_filing_document(accession_no, primary_doc_name)
                if doc_content:
                    # Save with appropriate extension if possible
                    file_ext = os.path.splitext(primary_doc_name)[1] or ".html" # Default to .html
                    save_text(doc_content, f"{ticker}_{form_type}_{accession_no}{file_ext}")
                else:
                    logging.warning(f"Could not fetch document for {accession_no}")
        else:
            logging.warning(f"No {form_type} filings found for {ticker} in the lookback period.")

    # Fetch, parse, and save Form 4 transactions
    logging.info(f"Fetching and parsing Form 4 transactions for {ticker} (last {form_types_to_fetch['4']} days)...")
    transactions_df = fetcher.get_recent_insider_transactions(ticker, days_back=form_types_to_fetch['4'], use_cache=False)
    if not transactions_df.empty:
        save_dataframe_csv(transactions_df, f"{ticker}_form4_transactions.csv")
    else:
        logging.warning(f"No parsable Form 4 transactions found for {ticker}.")

    logging.info(f"--- Data exploration finished for {ticker} ---")
    logging.info(f"Check the '{EXPLORATION_DIR}' directory for saved files.")

def test_edgar_api():
    """Test the EDGAR API functionality using SECDataFetcher."""
    logging.info("--- Starting EDGAR API Test --- ")
    # Initialize the fetcher
    user_agent = os.getenv('SEC_API_USER_AGENT', 'YourAppName (youremail@example.com)') # Provide a default
    if not user_agent or user_agent == 'YourAppName (youremail@example.com)':
         logging.warning("Using default/placeholder User-Agent. Please set SEC_API_USER_AGENT environment variable.")
    fetcher = SECDataFetcher(user_agent=user_agent)

    if not fetcher.api_valid:
        logging.error("SEC API not accessible. Exiting test.")
        return

    # Test getting CIK for a ticker
    ticker = "AAPL"
    logging.info(f"Getting CIK for {ticker}...")
    cik = fetcher.get_cik_for_ticker(ticker)
    if cik:
        logging.info(f"CIK for {ticker}: {cik}")
    else:
        logging.error(f"Failed to get CIK for {ticker}. Aborting further tests for this ticker.")
        return # Stop if CIK lookup fails

    # Test fetching a recent 10-K form using fetch_form_direct
    logging.info(f"\nFetching recent 10-K for {ticker} using fetch_form_direct...")
    forms = fetcher.fetch_form_direct(ticker, "10-K", count=1)
    if forms:
        form = forms[0]
        logging.info(f"Found 10-K filed on {form['filing_date']} (Acc: {form['accession_number']}) Document: {form['primary_document']}")

        # Download the document using download_form_document
        accession_number = form.get('accession_number')
        document_name = form.get('primary_document')

        if accession_number and document_name:
            logging.info(f"\nDownloading document: {document_name} using download_form_document...")
            doc_content = fetcher.download_form_document(
                accession_number,
                document_name
            )

            if doc_content:
                logging.info(f"Document size: {len(doc_content)} bytes")

                # Save the document using helper
                # Determine a reasonable extension
                file_ext = os.path.splitext(document_name)[1] or ".html"
                save_filename = f"{ticker}_10K_{form['filing_date']}{file_ext}"
                save_text(doc_content, save_filename)
            else:
                logging.error("Failed to download document using download_form_document")
        else:
            logging.warning("Missing accession number or document name, cannot download.")
    else:
        logging.warning(f"No 10-K forms found for {ticker} via fetch_form_direct")

    # +++ Fetch recent Form 4 XML examples +++
    logging.info(f"\nFetching recent Form 4 filings for {ticker} to get XML examples...")
    form4_filings = fetcher.fetch_form_direct(ticker, "4", count=2)
    if form4_filings:
        logging.info(f"Found {len(form4_filings)} recent Form 4 filings.")
        for i, filing in enumerate(form4_filings):
            accession_no = filing.get('accession_number')
            if accession_no:
                logging.info(f"Downloading Form 4 XML for filing {i+1}: {accession_no}...")
                xml_content = fetcher.download_form_xml(accession_no)
                if xml_content:
                    xml_filename = f"{ticker}_form4_{accession_no}.xml"
                    save_text(xml_content, xml_filename) # Use existing helper
                    logging.info(f"Saved Form 4 XML example: {xml_filename}")

                    # +++ Test the new XML parser +++
                    logging.info(f"Parsing {xml_filename} using the new XML parser...")
                    parsed_transactions = fetcher.parse_form4_xml(xml_content)
                    if parsed_transactions:
                        logging.info(f"Successfully parsed {len(parsed_transactions)} transactions from {xml_filename}.")
                        # Log first transaction as example
                        logging.info(f"Example parsed transaction: {parsed_transactions[0]}") 
                        # Optionally save parsed data
                        parsed_filename = f"{ticker}_form4_{accession_no}_parsed.json"
                        save_json(parsed_transactions, parsed_filename) # Use existing helper
                    else:
                        logging.error(f"Failed to parse transactions from {xml_filename} using the new parser.")
                    # +++ End Test the new XML parser +++
                else:
                    logging.warning(f"Could not download XML for {accession_no}.")
            else:
                logging.warning(f"Form 4 filing {i+1} missing accession number.")
    else:
        logging.warning(f"No recent Form 4 filings found for {ticker}.")
    # +++ End Fetch recent Form 4 XML examples +++

    # Fetch Company Facts (as before)
    logging.info(f"\nFetching company facts for {ticker}...")
    company_facts = fetcher.get_company_facts(ticker)
    if company_facts:
        logging.info(f"Successfully fetched company facts for {company_facts.get('entityName', ticker)}.")
        save_filename = f"{ticker}_company_facts.json"
        save_json(company_facts, save_filename)

        # +++ Fetch Financial Summary with Ratios +++
        logging.info(f"\nFetching financial summary (including calculated ratios) for {ticker}...")
        financial_summary = fetcher.get_financial_summary(ticker, use_cache=False) # Use cache=False to ensure ratio calc runs
        if financial_summary:
            summary_filename = f"{ticker}_financial_summary.json"
            save_json(financial_summary, summary_filename)
            logging.info(f"Saved financial summary to {summary_filename}")
            
            # Log the calculated ratios
            ratios = financial_summary.get('calculated_ratios', {})
            if ratios:
                logging.info("Calculated Ratios:")
                for name, data in ratios.items():
                    value_str = f"{data.get('value'):.4f}" if data.get('value') is not None else "N/A"
                    logging.info(f"  - {name}: {value_str} (Unit: {data.get('unit')}, Period: {data.get('end_date')}, Error: {data.get('error')})")
            else:
                logging.info("No ratios could be calculated (likely missing data or mismatched periods).")
        else:
            logging.error(f"Failed to generate financial summary for {ticker}.")
        # +++ End Fetch Financial Summary +++

    else:
        logging.error(f"Failed to fetch company facts for {ticker}. Cannot generate summary.")

    logging.info("--- EDGAR API Test Finished ---")

def main():
    """Main function to run the EDGAR API test."""
    test_edgar_api()

if __name__ == "__main__":
    # Ensure you have a .env file with SEC_API_USER_AGENT="YourAppName (youremail@example.com)"
    main()