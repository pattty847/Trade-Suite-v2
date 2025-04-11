import logging
import dearpygui.dearpygui as dpg
from typing import Any, Dict, List, Optional
from datetime import datetime

from trade_suite.data.sec_data import SECDataFetcher
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager
from trade_suite.gui.widgets.base_widget import DockableWidget

class SECFilingViewer(DockableWidget):
    """
    A dockable widget to fetch and display SEC filing data for a company ticker.
    """
    WIDGET_TYPE = "SECFilingViewer"

    def __init__(
        self,
        emitter: SignalEmitter,
        sec_fetcher: SECDataFetcher,
        task_manager: TaskManager,
        instance_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            title="SEC Filing Viewer",
            widget_type=self.WIDGET_TYPE,
            emitter=emitter,
            instance_id=instance_id,
            width=600,
            height=500,
            **kwargs
        )
        self.sec_fetcher = sec_fetcher
        self.task_manager = task_manager

        # Tags for UI elements
        self.ticker_input_tag = f"{self.content_tag}_ticker_input"
        self.filings_table_tag = f"{self.content_tag}_filings_table"
        self.insider_tx_table_tag = f"{self.content_tag}_insider_tx_table"
        self.financials_display_tag = f"{self.content_tag}_financials_display"
        self.status_text_tag = f"{self.content_tag}_status_text"

        # Store the last requested ticker to avoid race conditions in UI updates
        self._last_requested_ticker: Optional[str] = None

        logging.info(f"SECFilingViewer instance {self.instance_id} created.")

    def build_content(self) -> None:
        """Build the widget's main content area."""
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag=self.ticker_input_tag, label="Ticker", hint="Enter Ticker (e.g., AAPL)", width=150, callback=self._clear_on_ticker_change)
            dpg.add_button(label="Fetch Filings", callback=self._fetch_filings_callback)
            dpg.add_button(label="Fetch Insider Tx", callback=self._fetch_insider_tx_callback)
            dpg.add_button(label="Fetch Financials", callback=self._fetch_financials_callback)

        dpg.add_separator()
        dpg.add_text("Status:", tag=self.status_text_tag, wrap=dpg.get_item_width(self.content_tag) - 20 if dpg.get_item_width(self.content_tag) else 580) # Adjust wrap width dynamically if possible
        dpg.add_separator()

        # Filings Section
        dpg.add_text("Recent Filings:")
        with dpg.table(tag=self.filings_table_tag, header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp,
                       borders_outerH=True, borders_innerV=True, borders_innerH=True, borders_outerV=True, row_background=True):
            dpg.add_table_column(label="Acc No.")
            dpg.add_table_column(label="Form")
            dpg.add_table_column(label="Filing Date")
            dpg.add_table_column(label="Report Date")
            dpg.add_table_column(label="View") # Added column for View button

        dpg.add_separator()

        # Insider Transactions Section
        dpg.add_text("Insider Transactions (Form 4):")
        with dpg.table(tag=self.insider_tx_table_tag, header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp,
                       borders_outerH=True, borders_innerV=True, borders_innerH=True, borders_outerV=True, row_background=True):
            dpg.add_table_column(label="Filer")
            dpg.add_table_column(label="Date")
            dpg.add_table_column(label="Type") # TODO: Confirm keys from sec_fetcher
            dpg.add_table_column(label="Shares") # TODO: Confirm keys
            dpg.add_table_column(label="Price") # TODO: Confirm keys
            dpg.add_table_column(label="Value") # TODO: Confirm keys
            dpg.add_table_column(label="Form URL")
            # Add placeholder row?

        dpg.add_separator()

        # Financials Section
        dpg.add_text("Latest Financials:")
        with dpg.group(tag=self.financials_display_tag):
             dpg.add_text("No data loaded.") # Placeholder

    def register_handlers(self) -> None:
        """Register signal handlers."""
        self.emitter.register(Signals.SEC_FILINGS_UPDATE, self._handle_filings_update)
        self.emitter.register(Signals.SEC_INSIDER_TX_UPDATE, self._handle_insider_tx_update)
        self.emitter.register(Signals.SEC_FINANCIALS_UPDATE, self._handle_financials_update)
        self.emitter.register(Signals.SEC_DATA_FETCH_ERROR, self._handle_fetch_error)
        logging.info(f"SECFilingViewer {self.instance_id} registered signal handlers.")

    def _clear_on_ticker_change(self, sender: int, app_data: str, user_data: Any) -> None:
        """Clear results when ticker changes."""
        # Clear tables and financials if ticker changes significantly
        # Avoid clearing if just adding a character during typing (optional optimization)
        if self._last_requested_ticker and app_data.upper() != self._last_requested_ticker:
             self._clear_all_results()
             dpg.set_value(self.status_text_tag, "Status:")
             self._last_requested_ticker = None # Reset requested ticker

    def _clear_all_results(self):
        """Clears all data display areas."""
        dpg.delete_item(self.filings_table_tag, children_only=True, slot=1) # Keep header row
        dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1) # Keep header row
        dpg.delete_item(self.financials_display_tag, children_only=True) # Remove all content
        dpg.add_text("No data loaded.", parent=self.financials_display_tag) # Add back placeholder

    def _update_status(self, message: str):
        """Updates the status text area."""
        if dpg.does_item_exist(self.status_text_tag):
            dpg.set_value(self.status_text_tag, f"Status: {message}")

    def _get_ticker(self) -> Optional[str]:
        """Gets the ticker from the input field, validates, and sets status."""
        if not dpg.does_item_exist(self.ticker_input_tag):
            return None
        ticker = dpg.get_value(self.ticker_input_tag).strip().upper()
        if not ticker:
            self._update_status("Error: Ticker symbol cannot be empty.")
            return None
        self._last_requested_ticker = ticker # Store the ticker we are about to request
        return ticker

    # --- Button Callbacks ---

    def _fetch_filings_callback(self, sender: int, app_data: Any, user_data: Any) -> None:
        """Callback for the 'Fetch Filings' button."""
        ticker = self._get_ticker()
        if ticker:
            self._update_status(f"Fetching filings for {ticker}...")
            dpg.delete_item(self.filings_table_tag, children_only=True, slot=1) # Clear table content (keep header)
            # First parameter should be task_id, second parameter is coroutine object
            task_id = f"sec_filings_{ticker}_{self.instance_id}"
            self.task_manager.start_task(
                task_id, 
                self.sec_fetcher.fetch_filings(ticker=ticker)
            )

    def _fetch_insider_tx_callback(self, sender: int, app_data: Any, user_data: Any) -> None:
        """Callback for the 'Fetch Insider Tx' button."""
        ticker = self._get_ticker()
        if ticker:
            self._update_status(f"Fetching insider transactions for {ticker}...")
            dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1) # Clear table content
            # First parameter should be task_id, second parameter is coroutine object
            task_id = f"sec_insider_tx_{ticker}_{self.instance_id}"
            self.task_manager.start_task(
                task_id,
                self.sec_fetcher.fetch_insider_transactions(ticker=ticker)
            )

    def _fetch_financials_callback(self, sender: int, app_data: Any, user_data: Any) -> None:
        """Callback for the 'Fetch Financials' button."""
        ticker = self._get_ticker()
        if ticker:
            self._update_status(f"Fetching financials for {ticker}...")
            dpg.delete_item(self.financials_display_tag, children_only=True) # Clear financials display
            dpg.add_text("Loading...", parent=self.financials_display_tag)
            # First parameter should be task_id, second parameter is coroutine object
            task_id = f"sec_financials_{ticker}_{self.instance_id}"
            self.task_manager.start_task(
                task_id,
                self.sec_fetcher.fetch_financials(ticker=ticker)
            )

    # --- Signal Handlers ---

    def _handle_filings_update(self, **kwargs) -> None:
        """Handles the SEC_FILINGS_UPDATE signal."""
        ticker = kwargs.get('ticker')
        filings = kwargs.get('filings', [])

        if not dpg.does_item_exist(self.window_tag) or ticker != self._last_requested_ticker:
            logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring filings update for {ticker} (current: {self._last_requested_ticker}) or window closed.")
            return

        self._update_status(f"Successfully loaded {len(filings)} filings for {ticker}.")
        dpg.delete_item(self.filings_table_tag, children_only=True, slot=1) # Clear existing rows

        for filing in filings:
            with dpg.table_row(parent=self.filings_table_tag):
                dpg.add_text(filing.get('accession_no', 'N/A'))
                dpg.add_text(filing.get('form', 'N/A'))
                dpg.add_text(filing.get('filing_date', 'N/A'))
                dpg.add_text(filing.get('report_date', 'N/A')) # May not exist
                # Add a "View" button to open the filing in a browser
                url = filing.get('url', None)
                if url:
                    dpg.add_button(label="View", callback=lambda s, a, u=url: self._open_url(u))
                else:
                    dpg.add_text("N/A")

    def _handle_insider_tx_update(self, **kwargs) -> None:
        """Handles the SEC_INSIDER_TX_UPDATE signal."""
        ticker = kwargs.get('ticker')
        transactions = kwargs.get('transactions', [])

        if not dpg.does_item_exist(self.window_tag) or ticker != self._last_requested_ticker:
            logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring insider tx update for {ticker} (current: {self._last_requested_ticker}) or window closed.")
            return

        self._update_status(f"Successfully loaded {len(transactions)} insider transactions for {ticker}.")
        dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1) # Clear existing rows

        # Keys based on the actual edgartools Form 4 data structure
        for tx in transactions:
            with dpg.table_row(parent=self.insider_tx_table_tag):
                # Filer name - truncate if too long
                filer = tx.get('filer', 'N/A')
                if filer and len(filer) > 25:
                    filer = filer[:22] + "..."
                dpg.add_text(filer)
                
                # Date - format as MM/DD/YYYY if possible
                date_str = tx.get('date', 'N/A')
                try:
                    if date_str and date_str != 'N/A':
                        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        date_str = date_obj.strftime('%m/%d/%Y')
                except (ValueError, TypeError):
                    # Keep original string if parsing fails
                    pass
                dpg.add_text(date_str)
                
                # Transaction type
                dpg.add_text(tx.get('type', 'N/A'))
                
                # Format numerical values properly
                shares = tx.get('shares', 'N/A')
                if isinstance(shares, (int, float)):
                    dpg.add_text(f"{shares:,.0f}")  # No decimal places for shares
                else:
                    dpg.add_text(str(shares))
                
                price = tx.get('price', 'N/A')
                if isinstance(price, (int, float)):
                    dpg.add_text(f"${price:.2f}")
                else:
                    dpg.add_text(str(price))
                
                value = tx.get('value', 'N/A')
                if isinstance(value, (int, float)):
                    dpg.add_text(f"${value:,.2f}")
                else:
                    dpg.add_text(str(value))
                
                url = tx.get('form_url', None)
                if url:
                    dpg.add_button(label="View", callback=lambda s, a, u=url: self._open_url(u))
                else:
                    dpg.add_text("N/A")

    def _handle_financials_update(self, **kwargs) -> None:
        """Handles the SEC_FINANCIALS_UPDATE signal."""
        ticker = kwargs.get('ticker')
        financials = kwargs.get('financials')

        if not dpg.does_item_exist(self.window_tag) or ticker != self._last_requested_ticker:
             logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring financials update for {ticker} (current: {self._last_requested_ticker}) or window closed.")
             return

        self._update_status(f"Successfully loaded financials for {ticker}.")
        dpg.delete_item(self.financials_display_tag, children_only=True) # Clear previous content

        if financials:
            # Display source filing info
            dpg.add_text(f"Source: {financials.get('source_form', 'N/A')} ({financials.get('source_filing', 'N/A')})", parent=self.financials_display_tag)
            dpg.add_text(f"Period End: {financials.get('period_end', 'N/A')}", parent=self.financials_display_tag)
            
            # Display financial metrics with proper formatting
            self._add_financial_metric("Revenue", financials.get('revenue', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Net Income", financials.get('net_income', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("EPS (Basic)", financials.get('eps', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Total Assets", financials.get('assets', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Total Liabilities", financials.get('liabilities', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Stockholders' Equity", financials.get('equity', 'N/A'), self.financials_display_tag)
            
            # Add a link to view the source filing if available
            source_url = financials.get('source_url', None)
            if source_url:
                with dpg.group(horizontal=True, parent=self.financials_display_tag):
                    dpg.add_text("Source Filing: ")
                    dpg.add_button(label="View", callback=lambda s, a, u=source_url: self._open_url(u))
        else:
            dpg.add_text("Financial data not available.", parent=self.financials_display_tag)

    def _add_financial_metric(self, label, value, parent):
        """Helper to add a financial metric with proper formatting."""
        if isinstance(value, (int, float)):
            # Format large numbers with commas and 2 decimal places if it's a dollar amount
            formatted_value = f"${value:,.2f}" if label.lower() not in ["eps (basic)", "eps (diluted)"] else f"{value:.2f}"
            dpg.add_text(f"{label}: {formatted_value}", parent=parent)
        else:
            dpg.add_text(f"{label}: {value}", parent=parent)
    
    def _open_url(self, url):
        """Open a URL in the default browser."""
        import webbrowser
        try:
            if url and isinstance(url, str) and url.startswith(('http://', 'https://', 'www.')):
                logging.debug(f"Opening URL in browser: {url}")
                webbrowser.open(url)
            else:
                logging.error(f"Invalid URL format: {url}")
                self._update_status(f"Error: Invalid URL format. Unable to open browser.")
        except Exception as e:
            logging.error(f"Error opening URL {url}: {e}")
            self._update_status(f"Error opening URL: {str(e)}")

    def _handle_fetch_error(self, **kwargs) -> None:
        """Handles the SEC_DATA_FETCH_ERROR signal."""
        ticker = kwargs.get('ticker')
        data_type = kwargs.get('data_type')
        error = kwargs.get('error')

        # Only update status if the error corresponds to the last requested ticker
        if dpg.does_item_exist(self.window_tag) and ticker == self._last_requested_ticker:
            error_message = f"Error fetching {data_type} for {ticker}: {error}"
            self._update_status(error_message)
            logging.error(error_message)
            # Optionally clear the specific section that failed
            if data_type == 'filings':
                 dpg.delete_item(self.filings_table_tag, children_only=True, slot=1)
                 # Add error message row?
            elif data_type == 'insider_transactions':
                 dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1)
            elif data_type == 'financials':
                 dpg.delete_item(self.financials_display_tag, children_only=True)
                 dpg.add_text(f"Error loading financials: {error}", parent=self.financials_display_tag, color=(255, 0, 0))


    def close(self) -> None:
        """Clean up when the widget is closed."""
        # Unregister signal handlers? Depends on Emitter implementation.
        # If emitter holds strong refs, unregistering might be needed.
        # Assuming weak refs or automatic cleanup for now.
        logging.info(f"Closing SECFilingViewer {self.instance_id}.")
        super().close()

# Example Integration (in Viewport or DashboardManager):
# from trade_suite.gui.widgets.sec_filing_viewer import SECFilingViewer
#
# sec_viewer = SECFilingViewer(
#     emitter=signal_emitter,
#     sec_fetcher=sec_data_fetcher_instance,
#     task_manager=task_manager_instance
# )
# sec_viewer.create() # Or add to docking layout 