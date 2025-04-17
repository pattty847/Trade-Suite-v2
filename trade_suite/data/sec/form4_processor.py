import logging
import xml.etree.ElementTree as ET
import pandas as pd
from typing import List, Dict, Optional, TYPE_CHECKING, Callable, Awaitable

# Import FilingDocumentHandler for dependency injection
from .document_handler import FilingDocumentHandler

# Use TYPE_CHECKING block to avoid circular imports at runtime
# SECDataFetcher is needed for fetching filing metadata (get_filings_by_form)
if TYPE_CHECKING:
    from .sec_api import SECDataFetcher # type: ignore

class Form4Processor:
    """
    Handles the specialized processing, parsing, and analysis of SEC Form 4 filings (Insider Transactions).

    This class encapsulates all logic related to Form 4 data. Its core responsibilities include:
    - Parsing the XML structure of Form 4 filings to extract transaction details
      for both non-derivative and derivative securities.
    - Mapping transaction codes (e.g., 'P', 'S') to human-readable descriptions (e.g., 'Purchase', 'Sale').
    - Classifying transactions as acquisitions or dispositions based on codes.
    - Orchestrating the retrieval of recent Form 4 filing metadata (via an injected function).
    - Downloading the corresponding Form 4 XML documents (using the injected `FilingDocumentHandler`).
    - Processing multiple recent filings to compile a list of transactions formatted for display or analysis.
    - Performing basic quantitative analysis on the compiled transactions (e.g., buy/sell counts, net value).

    It depends on an injected `FilingDocumentHandler` for XML downloads and a function
    (usually from `SECDataFetcher`) to retrieve the list of recent Form 4 filing accession numbers.
    """

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

    def __init__(self, 
                 document_handler: FilingDocumentHandler, 
                 fetch_filings_func: Callable[..., Awaitable[List[Dict]]]):
        """
        Initializes the Form 4 Processor.

        Args:
            document_handler (FilingDocumentHandler): An instance of the
                `FilingDocumentHandler` used specifically for downloading the
                XML content of Form 4 filings.
            fetch_filings_func (Callable[..., Awaitable[List[Dict]]]): An awaitable
                function that retrieves the metadata for recent Form 4 filings
                (e.g., accession number, filing date) for a given ticker.
                This is typically bound to `SECDataFetcher.fetch_insider_filings`.
        """
        self.document_handler = document_handler
        self.fetch_filings_metadata = fetch_filings_func # e.g., SECDataFetcher.fetch_insider_filings

    def parse_form4_xml(self, xml_content: str) -> List[Dict]:
        """
        Parses the XML content of a single SEC Form 4 filing into structured transaction data.

        Uses `xml.etree.ElementTree` to navigate the standard Form 4 XML structure.
        Extracts details for both `nonDerivativeTransaction` and `derivativeTransaction` elements.
        Handles potential missing fields gracefully and attempts basic type conversion (e.g., float for shares/price).
        Adds derived fields like 'transaction_type', 'is_acquisition', 'is_disposition', and calculated 'value'.

        Args:
            xml_content (str): A string containing the complete XML content of a Form 4 filing.

        Returns:
            List[Dict]: A list of dictionaries, where each dictionary represents a single
                transaction (either non-derivative or derivative) parsed from the form.
                Returns an empty list if the XML is malformed or cannot be parsed.
                Keys in the dictionary include 'ticker', 'owner_name', 'transaction_date',
                'transaction_code', 'transaction_type', 'shares', 'price_per_share',
                'value', 'is_derivative', 'is_acquisition', 'is_disposition', etc.
        """
        transactions = []
        try:
            root = ET.fromstring(xml_content)

            # Extract common info
            issuer_cik = root.findtext('.//issuer/issuerCik', default='N/A')
            issuer_name = root.findtext('.//issuer/issuerName', default='N/A')
            issuer_symbol = root.findtext('.//issuer/issuerTradingSymbol', default='N/A')

            owner_cik = root.findtext('.//reportingOwner/reportingOwnerId/rptOwnerCik', default='N/A')
            owner_name = root.findtext('.//reportingOwner/reportingOwnerId/rptOwnerName', default='N/A')

            # Extract owner relationship
            relationship_node = root.find('.//reportingOwner/reportingOwnerRelationship')
            owner_positions = []
            officer_title = None
            if relationship_node is not None:
                if relationship_node.findtext('isDirector', default='0').strip() in ['1', 'true']:
                    owner_positions.append('Director')
                if relationship_node.findtext('isOfficer', default='0').strip() in ['1', 'true']:
                    owner_positions.append('Officer')
                    officer_title = relationship_node.findtext('officerTitle', default='').strip()
                if relationship_node.findtext('isTenPercentOwner', default='0').strip() in ['1', 'true']:
                    owner_positions.append('10% Owner')
                if relationship_node.findtext('isOther', default='0').strip() in ['1', 'true']:
                    owner_positions.append('Other')
            
            # Format the position string
            owner_position_str = ', '.join(owner_positions)
            if officer_title and 'Officer' in owner_positions:
                 # Replace 'Officer' with 'Officer (Title)' if title exists
                 owner_position_str = owner_position_str.replace('Officer', f'Officer ({officer_title})', 1)
            elif not owner_position_str:
                 owner_position_str = 'N/A' # Default if no flags are set

            # Process Non-Derivative Transactions
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
                        'is_derivative': False,
                        'owner_position': owner_position_str
                    }
                    transactions.append(transaction)
                except Exception as e:
                    logging.warning(f"Error parsing non-derivative tx: {e} - XML: {ET.tostring(tx, encoding='unicode')[:200]}")

            # Process Derivative Transactions
            for tx in root.findall('.//derivativeTransaction'):
                try:
                    security_title = tx.findtext('./securityTitle/value', default='N/A')
                    tx_date = tx.findtext('./transactionDate/value', default='N/A')
                    tx_code = tx.findtext('./transactionCoding/transactionCode', default='N/A')
                    conv_exercise_price_str = tx.findtext('./conversionOrExercisePrice/value', default='0')
                    shares_str = tx.findtext('./transactionAmounts/transactionShares/value', default='0')
                    acq_disp_code = tx.findtext('./transactionAmounts/transactionAcquiredDisposedCode/value', default='N/A')
                    exercise_date = tx.findtext('./exerciseDate/value', default='N/A')
                    expiration_date = tx.findtext('./expirationDate/value', default='N/A')
                    underlying_title = tx.findtext('./underlyingSecurity/underlyingSecurityTitle/value', default='N/A')
                    underlying_shares_str = tx.findtext('./underlyingSecurity/underlyingSecurityShares/value', default='0')
                    shares_owned_after_str = tx.findtext('./postTransactionAmounts/sharesOwnedFollowingTransaction/value', default='N/A')
                    direct_indirect = tx.findtext('./ownershipNature/directOrIndirectOwnership/value', default='N/A')

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
                        'shares': shares,
                        'conversion_exercise_price': conv_exercise_price,
                        'exercise_date': exercise_date,
                        'expiration_date': expiration_date,
                        'underlying_title': underlying_title,
                        'underlying_shares': underlying_shares,
                        'shares_owned_after': shares_owned_after,
                        'direct_indirect': direct_indirect,
                        'is_derivative': True,
                        'owner_position': owner_position_str
                    }
                    transactions.append(transaction)
                except Exception as e:
                    logging.warning(f"Error parsing derivative tx: {e} - XML: {ET.tostring(tx, encoding='unicode')[:200]}")

            return transactions

        except ET.ParseError as e:
            logging.error(f"XML Parse Error in Form 4: {e} - Content length: {len(xml_content)}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error parsing Form 4 XML: {e}", exc_info=True)
            return []

    async def process_form4_filing(self, accession_no: str, ticker: str = None) -> List[Dict]:
        """
        Downloads and parses a single Form 4 XML filing identified by its accession number.

        This method orchestrates the two main steps for processing one filing:
        1. Calls `document_handler.download_form_xml` to get the XML content.
        2. Calls `parse_form4_xml` to parse the downloaded content.

        Args:
            accession_no (str): The accession number of the Form 4 filing to process.
            ticker (str, optional): The stock ticker symbol of the *issuer*. This is passed
                to the `download_form_xml` method as a hint for constructing the correct
                download URL. Defaults to None.

        Returns:
            List[Dict]: A list of transaction dictionaries parsed from the filing.
                Returns an empty list if the XML download or parsing fails.
        """
        # Use document_handler to download the XML
        xml_content = await self.document_handler.download_form_xml(accession_no, ticker=ticker)

        if not xml_content:
            logging.warning(f"Could not download Form 4 XML for {accession_no} (ticker: {ticker})")
            return []

        # Parse the XML
        return self.parse_form4_xml(xml_content)

    async def get_recent_insider_transactions(self, ticker: str, days_back: int = 90,
                                         use_cache: bool = True, filing_limit: int = 10) -> List[Dict]:
        """
        Fetches metadata, downloads, parses, and formats recent Form 4 transactions.

        This is a high-level method designed to retrieve a list of recent insider
        transactions suitable for direct use (e.g., displaying in a UI table).

        Workflow:
        1. Calls the injected `fetch_filings_metadata` function to get a list of recent
           Form 4 filings (accession numbers, dates, etc.) for the `ticker`.
        2. Iterates through the fetched metadata (up to `filing_limit`).
        3. For each filing, calls `process_form4_filing` to download and parse its XML.
        4. Formats the relevant fields from the parsed transactions into a simplified
           dictionary structure commonly needed for display.
        5. Appends these formatted dictionaries to a final list.

        Args:
            ticker (str): The stock ticker symbol of the issuer.
            days_back (int, optional): How many days back to look for Form 4 filings.
                Passed to the `fetch_filings_metadata` function. Defaults to 90.
            use_cache (bool, optional): Whether the `fetch_filings_metadata` function
                should attempt to use cached filing metadata. Defaults to True.
            filing_limit (int, optional): The maximum number of the most recent filings
                to download and parse. This helps limit processing time and API usage.
                Defaults to 10.

        Returns:
            List[Dict]: A list of dictionaries, each representing a formatted insider
                transaction ready for display. Keys typically include 'filer' (owner name),
                'date', 'type' (e.g., Purchase, Sale), 'shares', 'price', 'value',
                'form_url', 'primary_document'. Returns an empty list if no filings
                are found or no transactions can be parsed.
        """
        ticker = ticker.upper()

        # Get Form 4 filing metadata using the injected function
        filings_meta = await self.fetch_filings_metadata(ticker, days_back=days_back, use_cache=use_cache)

        if not filings_meta:
            logging.info(f"No recent Form 4 filing metadata found for {ticker}")
            return []

        all_ui_transactions = []
        logging.info(f"Processing up to {filing_limit} most recent Form 4 filings for {ticker}...")

        processed_count = 0
        for filing_meta in filings_meta:
            if processed_count >= filing_limit:
                 logging.info(f"Reached processing limit of {filing_limit} filings for {ticker}.")
                 break

            accession_no = filing_meta.get('accession_no')
            filing_url = filing_meta.get('url', 'N/A') # Get URL from metadata if available
            primary_doc_name = filing_meta.get('primary_document') # Get primary doc name

            if not accession_no:
                logging.warning(f"Skipping filing for {ticker} due to missing accession number in metadata: {filing_meta}")
                continue

            # Process the XML to get detailed transactions
            parsed_transactions = await self.process_form4_filing(accession_no, ticker=ticker)

            if not parsed_transactions:
                logging.debug(f"No transactions parsed for {ticker}, accession: {accession_no}")
                continue # Move to the next filing

            processed_count += 1

            # Format each parsed transaction for the UI
            for tx in parsed_transactions:
                ui_transaction = {
                    'filer': tx.get('owner_name', 'N/A'),
                    'position': tx.get('owner_position', 'N/A'),
                    'date': tx.get('transaction_date', 'N/A'),
                    'type': tx.get('transaction_type', 'Unknown'),
                    'shares': tx.get('shares'),
                    'price': tx.get('price_per_share') if not tx.get('is_derivative') else tx.get('conversion_exercise_price'),
                    'value': tx.get('value') if not tx.get('is_derivative') else None, # Value calculation for derivatives is complex
                    'form_url': filing_url, # Use URL from metadata
                    'primary_document': primary_doc_name # Use filename from metadata
                }

                # Recalculate value for non-derivatives if needed
                if not tx.get('is_derivative') and ui_transaction['value'] is None:
                     shares = ui_transaction.get('shares')
                     price = ui_transaction.get('price')
                     if shares is not None and price is not None:
                          try: ui_transaction['value'] = float(shares) * float(price)
                          except (ValueError, TypeError): ui_transaction['value'] = 0.0
                     else: ui_transaction['value'] = 0.0

                all_ui_transactions.append(ui_transaction)

        logging.info(f"Completed processing {processed_count} filings for {ticker}. Found {len(all_ui_transactions)} transactions.")
        return all_ui_transactions

    async def analyze_insider_transactions(self, ticker: str, days_back: int = 90, use_cache: bool = True) -> Dict:
        """
        Performs a basic quantitative analysis of recent insider transactions for a ticker.

        Downloads and parses recent Form 4 filings (similar to
        `get_recent_insider_transactions` but retrieves the full parsed data),
        converts the data into a pandas DataFrame, and calculates summary statistics.

        Workflow:
        1. Fetches recent Form 4 filing metadata for the `ticker`.
        2. Processes each filing using `process_form4_filing` to get detailed transactions.
        3. Concatenates all parsed transactions into a single list.
        4. Converts the list into a pandas DataFrame.
        5. Calculates metrics like:
           - Total number of transactions.
           - Number of buy vs. sell transactions (based on transaction codes).
           - Total value of buy vs. sell transactions.
           - Net transaction value (Total Buy Value - Total Sell Value).
           - Number of unique owners involved.
           - List of unique owners involved.
           - Optionally includes the raw DataFrame.

        Args:
            ticker (str): The stock ticker symbol of the issuer.
            days_back (int, optional): How many days back to look for Form 4 filings.
                Defaults to 90.
            use_cache (bool, optional): Whether to use cached filing metadata when fetching
                the list of filings to process. Defaults to True.

        Returns:
            Dict: A dictionary containing the analysis results. Keys include
                'ticker', 'analysis_period_days', 'total_transactions', 'buy_count',
                'sell_count', 'total_buy_value', 'total_sell_value', 'net_value',
                'involved_owners_count', 'involved_owners_list'. Includes an 'error'
                key if fetching or analysis fails. May include 'dataframe' if successful.
        """
        ticker = ticker.upper()

        # Get *parsed* transactions first (not UI formatted)
        # Need a method that fetches filings and processes them without UI formatting
        # Let's adapt process_form4_filing to run over multiple filings

        logging.info(f"Analyzing insider transactions for {ticker} ({days_back} days back)...")
        filings_meta = await self.fetch_filings_metadata(ticker, days_back=days_back, use_cache=use_cache)
        if not filings_meta:
             return {'ticker': ticker, 'error': "No filing metadata found."} 

        all_parsed_transactions = []
        # No limit for analysis, process all filings in the period
        for filing_meta in filings_meta:
             accession_no = filing_meta.get('accession_no')
             if not accession_no:
                 continue
             parsed = await self.process_form4_filing(accession_no, ticker=ticker)
             all_parsed_transactions.extend(parsed)

        if not all_parsed_transactions:
            return {
                'ticker': ticker,
                'error': "No transactions found in filings.",
                'total_transactions': 0
             }

        df = pd.DataFrame(all_parsed_transactions)

        try:
            # Ensure required columns exist and handle potential NaNs
            df['is_acquisition'] = df['is_acquisition'].fillna(False)
            df['is_disposition'] = df['is_disposition'].fillna(False)
            df['value'] = pd.to_numeric(df['value'], errors='coerce').fillna(0)
            df['shares'] = pd.to_numeric(df['shares'], errors='coerce').fillna(0)
            df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')

            # Filter out rows where conversion failed
            df = df.dropna(subset=['transaction_date'])

            # Separate buys/sells based on the boolean flags
            # Consider only non-derivative transactions for simple value analysis
            non_deriv_df = df[~df['is_derivative'].fillna(False)]
            buys = non_deriv_df[non_deriv_df['is_acquisition'] == True]
            sells = non_deriv_df[non_deriv_df['is_disposition'] == True]

            # Summary statistics
            result = {
                'ticker': ticker,
                'analysis_period_days': days_back,
                'total_filings_processed': len(filings_meta),
                'total_transactions_parsed': len(df),
                'buy_transaction_count': len(buys),
                'sell_transaction_count': len(sells),
                'total_buy_value': buys['value'].sum(),
                'total_sell_value': sells['value'].sum(),
                'net_value': buys['value'].sum() - sells['value'].sum(),
                'unique_filers': df['owner_name'].nunique(),
                'involved_filers': df['owner_name'].unique().tolist(),
                'analysis_start_date': df['transaction_date'].min().strftime('%Y-%m-%d') if not df.empty else None,
                'analysis_end_date': df['transaction_date'].max().strftime('%Y-%m-%d') if not df.empty else None,
                # Optional: More detailed stats
                # 'transactions_by_type': df['transaction_type'].value_counts().to_dict(),
                # 'top_buyers_by_value': buys.groupby('owner_name')['value'].sum().nlargest(5).to_dict(),
                # 'top_sellers_by_value': sells.groupby('owner_name')['value'].sum().nlargest(5).to_dict(),
            }

            logging.info(f"Analysis complete for {ticker}. Net value: {result['net_value']:.2f}")
            return result

        except Exception as e:
            logging.error(f"Error analyzing insider transactions for {ticker}: {e}", exc_info=True)
            return {
                'ticker': ticker,
                'error': f"Analysis error: {str(e)}",
                'total_transactions_parsed': len(df)
            } 