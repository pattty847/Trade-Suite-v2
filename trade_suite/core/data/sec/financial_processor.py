import logging
from typing import Dict, Optional, List, Callable, Awaitable

class FinancialDataProcessor:
    """Handles the processing and summarization of financial data extracted from SEC Company Facts (XBRL API).

    This class focuses on consuming the structured data available through the SEC's
    `/api/xbrl/companyfacts/` endpoint. Its primary roles are:
    - Defining a mapping (`KEY_FINANCIAL_SUMMARY_METRICS`) between desired summary
      metric names (e.g., 'revenue', 'net_income') and their corresponding XBRL tags
      within specific taxonomies (usually 'us-gaap' or 'dei').
    - Providing a method (`_get_latest_fact_value`) to navigate the raw company facts JSON
      and extract the most recent reported value for a given XBRL concept, considering units
      (prioritizing USD or shares) and reporting period end dates.
    - Orchestrating the retrieval of raw company facts (via an injected function) and using
      the defined mapping and extraction logic to produce a flattened dictionary
      (`get_financial_summary`) containing key financial metrics suitable for display or further analysis.
    - Includes a placeholder for potential future financial ratio calculations.

    It relies on an injected function (typically from `SECDataFetcher`) to obtain the raw
    company facts JSON data for a given ticker.
    """

    # Define key metrics mapping for the financial summary required by the UI
    # Keys are snake_case matching the target flat dictionary output.
    # Values are the corresponding us-gaap or dei XBRL tags.
    KEY_FINANCIAL_SUMMARY_METRICS = {
        # Income Statement
        "revenue": ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        "net_income": ("us-gaap", "NetIncomeLoss"),
        "eps": ("us-gaap", "EarningsPerShareBasic"), # Using Basic EPS for UI
        # Balance Sheet
        "assets": ("us-gaap", "Assets"),
        "liabilities": ("us-gaap", "Liabilities"),
        "equity": ("us-gaap", "StockholdersEquity"),
        # Cash Flow
        "operating_cash_flow": ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        "investing_cash_flow": ("us-gaap", "NetCashProvidedByUsedInInvestingActivities"),
        "financing_cash_flow": ("us-gaap", "NetCashProvidedByUsedInFinancingActivities"),
        # Other potentially useful
        # "shares_outstanding": ("dei", "EntityCommonStockSharesOutstanding") # Example DEI tag
    }

    def __init__(self, fetch_facts_func: Callable[[str, bool], Awaitable[Optional[Dict]]]):
        """
        Initializes the Financial Data Processor.

        Args:
            fetch_facts_func (Callable[[str, bool], Awaitable[Optional[Dict]]]): An awaitable
                function that takes a ticker (str) and a use_cache flag (bool) and returns
                the raw company facts JSON data as a dictionary (Optional[Dict]).
                This is typically bound to `SECDataFetcher.get_company_facts`.
        """
        self.fetch_company_facts = fetch_facts_func

    def _get_latest_fact_value(self, facts_data: Dict, taxonomy: str, concept_tag: str) -> Optional[Dict]:
        """
        Extracts the most recently reported data point for a specific XBRL concept from raw facts data.

        Navigates the nested structure of the company facts JSON (`facts_data`) based on the
        provided `taxonomy` (e.g., 'us-gaap') and `concept_tag` (e.g., 'Assets').
        It identifies the relevant units (preferring 'USD' or 'shares') and then finds the
        data point within that unit list that has the latest 'end' date.

        Args:
            facts_data (Dict): The raw JSON dictionary obtained from the SEC Company Facts API
                (usually via the `fetch_company_facts` function).
            taxonomy (str): The XBRL taxonomy where the concept is defined (e.g., 'us-gaap', 'dei').
            concept_tag (str): The specific XBRL concept tag to extract data for
                (e.g., 'RevenueFromContractWithCustomerExcludingAssessedTax').

        Returns:
            Optional[Dict]: A dictionary containing details of the latest fact found, including its
                'value', 'unit', 'end_date', fiscal year ('fy'), fiscal period ('fp'), source
                'form', and 'filed' date. Returns None if the concept, unit, or valid data point
                cannot be found within the provided `facts_data`.
        """
        try:
            concept_data = facts_data.get('facts', {}).get(taxonomy, {}).get(concept_tag)
            if not concept_data:
                # logging.debug(f"Concept '{concept_tag}' not found in {taxonomy}.")
                return None

            units = concept_data.get('units')
            if not units:
                # logging.debug(f"No units for concept '{concept_tag}'.")
                return None

            target_unit = None
            if 'USD' in units: target_unit = 'USD'
            elif 'shares' in units: target_unit = 'shares'
            else: target_unit = list(units.keys())[0]

            unit_data = units.get(target_unit)
            if not unit_data or not isinstance(unit_data, list) or len(unit_data) == 0:
                # logging.debug(f"No data for unit '{target_unit}' in concept '{concept_tag}'.")
                return None

            # Find the entry with the latest 'end' date
            # TODO: Consider 'filed' date as tie-breaker if needed
            latest_entry = max(unit_data, key=lambda x: x.get('end', '0000-00-00'))

            if not latest_entry or 'val' not in latest_entry:
                 logging.warning(f"Latest entry for '{concept_tag}' seems invalid: {latest_entry}")
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
            logging.error(f"Error processing concept '{concept_tag}' in {taxonomy}: {e}", exc_info=True)
            return None

    async def get_financial_summary(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Generates a flattened summary dictionary of key financial metrics for a given ticker.

        This is the main public method of the processor. It orchestrates the process:
        1. Calls the injected `fetch_company_facts` function to get the raw XBRL data.
        2. Iterates through the `KEY_FINANCIAL_SUMMARY_METRICS` mapping.
        3. For each metric, calls `_get_latest_fact_value` to extract the latest data point.
        4. Populates a flat dictionary with the extracted values, along with metadata like
           ticker, entity name, CIK, and the estimated source form and period end date
           (based on the latest end date found among key income statement metrics).

        Args:
            ticker (str): The stock ticker symbol for which to generate the summary.
            use_cache (bool, optional): Passed to the `fetch_company_facts` function to indicate
                whether cached data should be used if available and fresh. Defaults to True.

        Returns:
            Optional[Dict]: A flat dictionary containing the requested financial summary.
                Keys include 'ticker', 'entityName', 'cik', 'source_form', 'period_end',
                and the keys defined in `KEY_FINANCIAL_SUMMARY_METRICS` (e.g., 'revenue',
                'net_income', 'assets'). Values will be the latest reported numerical value
                or None if a metric couldn't be found. Returns None if the initial company
                facts data cannot be retrieved or if none of the requested metrics are found.
        """
        company_facts = await self.fetch_company_facts(ticker, use_cache=use_cache)
        if not company_facts:
            logging.warning(f"Could not retrieve company facts for {ticker}. Cannot generate financial summary.")
            return None

        summary_data = {
            "ticker": ticker.upper(),
            "entityName": company_facts.get('entityName', "N/A"),
            "cik": company_facts.get('cik', "N/A"),
            "source_form": None,
            "period_end": None,
        }

        # Initialize all required metric keys to None
        for key in self.KEY_FINANCIAL_SUMMARY_METRICS.keys():
            summary_data[key] = None

        latest_period_info = {"end_date": "0000-00-00", "form": None}
        has_data = False

        # Iterate through the required metrics defined in the mapping
        for metric_key, (taxonomy, concept_tag) in self.KEY_FINANCIAL_SUMMARY_METRICS.items():
            latest_fact = self._get_latest_fact_value(company_facts, taxonomy, concept_tag)

            if latest_fact:
                has_data = True
                summary_data[metric_key] = latest_fact.get('value') # Extract only the value

                # Try to determine the most recent period end date and form
                current_end_date = latest_fact.get("end_date", "0000-00-00")
                if metric_key in ["revenue", "net_income"] and current_end_date > latest_period_info["end_date"]:
                    latest_period_info["end_date"] = current_end_date
                    latest_period_info["form"] = latest_fact.get('form')
            else:
                 logging.debug(f"Metric '{metric_key}' (Tag: {concept_tag}, Tax: {taxonomy}) not found/no data for {ticker}.")
                 summary_data[metric_key] = None

        summary_data["period_end"] = latest_period_info["end_date"] if latest_period_info["end_date"] != "0000-00-00" else None
        summary_data["source_form"] = latest_period_info["form"]

        if not has_data:
             logging.warning(f"No financial metrics found for {ticker} based on defined tags.")
             return None

        logging.info(f"Generated financial summary for {ticker} ending {summary_data['period_end']} from form {summary_data['source_form']}.")
        return summary_data

    # Placeholder for future ratio calculations
    def _calculate_ratios(self, summary_metrics: Dict) -> Dict:
        """
        Placeholder method for calculating financial ratios from the summary data.

        This method is not currently implemented or used. It would take the dictionary
        produced by `get_financial_summary` and compute common financial ratios
        (e.g., P/E, Debt-to-Equity) if needed.

        Args:
            summary_metrics (Dict): The dictionary containing the flattened summary metrics.

        Returns:
            Dict: A dictionary containing calculated ratios (currently empty).
        """
        logging.warning("_calculate_ratios is not fully implemented.")
        # TODO: Implement ratio calculations based on extracted summary_metrics if needed.
        return {} 