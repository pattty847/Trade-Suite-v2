import logging
import dearpygui.dearpygui as dpg
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base_widget import DockableWidget
from ...core.facade import CoreServicesFacade
from ...gui import utils

class SECFilingViewer(DockableWidget):
    """
    A dockable DearPyGui widget for fetching, displaying, and interacting with
    SEC filing data for a specified company ticker.

    Features:
    - Input field for ticker symbol.
    - Dropdown to select common SEC form types (excluding Form 4).
    - Buttons to trigger fetching of:
        - General filings (based on selected form type).
        - Insider transactions (Form 4).
        - Key financial summary metrics (from XBRL data).
    - Displays fetched data in tables (Filings, Insider Transactions) and a dedicated area (Financials).
    - Provides a status bar for feedback on operations.
    - Integrates with TaskManager to perform asynchronous data fetching.
    - Uses SignalEmitter for asynchronous communication and UI updates.
    - Allows viewing raw filing content in a modal window.
    - Allows opening SEC filing URLs in a web browser.

    Attributes:
        sec_fetcher (SECDataFetcher): Instance used to fetch data from SEC APIs.
        task_manager (TaskManager): Instance used to run fetch operations asynchronously.
        ticker_input_tag (str): DPG tag for the ticker input field.
        form_type_combo_tag (str): DPG tag for the form type dropdown.
        filings_table_tag (str): DPG tag for the general filings table.
        insider_tx_table_tag (str): DPG tag for the insider transactions table.
        financials_display_tag (str): DPG tag for the group displaying financial data.
        status_text_tag (str): DPG tag for the status text label.
        _last_requested_ticker (Optional[str]): Stores the last ticker requested to prevent race conditions.
        _last_fetched_filings (List[Dict]): Stores the last fetched filings data for debugging.
        _last_fetched_transactions (List[Dict]): Stores the last fetched transactions data for debugging.
        _last_fetched_financials (Optional[Dict]): Stores the last fetched financials data for debugging.
        _is_loading (bool): Flag to track if a load is in progress.
    """
    WIDGET_TYPE = "sec_filing_viewer"
    WIDGET_TITLE = "SEC Filing Viewer"

    def __init__(
        self,
        core: CoreServicesFacade,
        instance_id: str,
        ticker: Optional[str] = None,
        **kwargs
    ):
        """Initializes the SECFilingViewer widget.

        Args:
            core (CoreServicesFacade): The application's core services facade.
            instance_id (Optional[str], optional): A unique identifier for this widget instance.
            ticker (Optional[str], optional): The initial ticker symbol to load. Defaults to None.
            **kwargs: Additional keyword arguments passed to the base DockableWidget constructor.
        """
        self._last_requested_ticker: Optional[str] = ticker.upper() if ticker else None
        kwargs.pop('ticker', None)

        super().__init__(
            core=core,
            instance_id=instance_id,
            width=600,
            height=500,
            **kwargs
        )
        self.sec_fetcher = self.core.data.sec_fetcher

        # Tags for UI elements
        self.ticker_input_tag = f"{self.content_tag}_ticker_input"
        self.form_type_combo_tag = f"{self.content_tag}_form_type_combo"
        self.filings_table_tag = f"{self.content_tag}_filings_table"
        self.insider_tx_table_tag = f"{self.content_tag}_insider_tx_table"
        self.financials_display_tag = f"{self.content_tag}_financials_display"
        self.status_text_tag = f"{self.content_tag}_status_text"

        # Store the last requested ticker to avoid race conditions in UI updates
        # self._last_requested_ticker: Optional[str] = None # This is now set above before super()
        # Store last fetched data for debugging
        self._last_fetched_filings: List[Dict] = []
        self._last_fetched_transactions: List[Dict] = []
        self._last_fetched_financials: Optional[Dict] = None
        self._is_loading: bool = False # Flag to track if a load is in progress

        logging.info(f"SECFilingViewer instance {self.instance_id} created with ticker: {self._last_requested_ticker}")

    def build_content(self) -> None:
        """Builds the DearPyGui elements within the widget's content area."""
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                tag=self.ticker_input_tag,
                label="Ticker",
                hint="Enter Ticker (e.g., AAPL)",
                width=150,
                callback=self._clear_on_ticker_change,
                default_value=self._last_requested_ticker or "" # Set initial value
            )

            # Form type selector dropdown
            # Filter out Form 4 as it has its own button
            common_forms = [ft for ft in self.sec_fetcher.FORM_TYPES.keys() if ft != "4"]
            dpg.add_combo(tag=self.form_type_combo_tag,
                          items=common_forms,
                          label="Form Type",
                          default_value="8-K", # Sensible default
                          width=100)

            dpg.add_button(label="Fetch Filings", callback=self._fetch_filings_callback)
            dpg.add_button(label="Fetch Insider Tx", callback=self._fetch_insider_tx_callback)
            dpg.add_button(label="Fetch Financials", callback=self._fetch_financials_callback)
            dpg.add_button(label="Save Fetched Data", callback=self._save_fetched_data_callback)

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
            dpg.add_table_column(label="Position")
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
        """Registers necessary signal handlers with the application's emitter."""
        # Register for generic task success/error signals
        self.emitter.register(Signals.TASK_SUCCESS, self._handle_task_success)
        self.emitter.register(Signals.TASK_ERROR, self._handle_task_error)

        logging.info(f"SECFilingViewer {self.instance_id} registered signal handlers.")

    def _clear_on_ticker_change(self, sender: int, app_data: str, user_data: Any) -> None:
        """Callback triggered when the ticker input value changes. Clears results if ticker differs."""
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
        """Helper method to update the status text label within the widget."""
        if dpg.does_item_exist(self.status_text_tag):
            dpg.set_value(self.status_text_tag, f"Status: {message}")

    def _get_ticker(self) -> Optional[str]:
        """Gets and validates the ticker symbol from the input field.

        Updates the status bar if the ticker is invalid. Stores the valid ticker
        in `_last_requested_ticker`.

        Returns:
            Optional[str]: The validated, uppercase ticker symbol, or None if invalid.
        """
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
        """Callback for the 'Fetch Filings' button.

        Retrieves the ticker and selected form type, clears the filings table,
        updates the status, and starts an asynchronous task via TaskManager
        to fetch the filings using `sec_fetcher.get_filings_by_form`.
        """
        ticker = self._get_ticker()

        # Get the selected form type from the UI
        form_type = None
        if dpg.does_item_exist(self.form_type_combo_tag):
            form_type = dpg.get_value(self.form_type_combo_tag)

        if ticker and form_type: # Ensure both ticker and form type are present
            if self._is_loading:
                self._update_status("Please wait for the current request to complete.")
                return # Prevent concurrent loads for now
            self._is_loading = True
            utils.create_loading_modal(f"Fetching {form_type} filings for {ticker}...") # Show modal
            self._update_status(f"Fetching {form_type} filings for {ticker}...")
            dpg.delete_item(self.filings_table_tag, children_only=True, slot=1) # Clear table content (keep header)
            # First parameter should be task_id, second parameter is coroutine object
            task_id = f"sec_filings_{ticker}_{form_type}_{self.instance_id}"
            self.task_manager.start_task(
                task_id,
                self.sec_fetcher.get_filings_by_form(ticker=ticker, form_type=form_type)
            )
        elif not ticker:
            self._update_status("Error: Please enter a ticker symbol.")
        elif not form_type:
            self._update_status("Error: Please select a form type.")

    def _fetch_insider_tx_callback(self, sender: int, app_data: Any, user_data: Any) -> None:
        """Callback for the 'Fetch Insider Tx' button.

        Retrieves the ticker, clears the insider transactions table,
        updates the status, and starts an asynchronous task via TaskManager
        to fetch transactions using `sec_fetcher.get_recent_insider_transactions`.
        """
        ticker = self._get_ticker()
        if ticker:
            if self._is_loading:
                self._update_status("Please wait for the current request to complete.")
                return # Prevent concurrent loads
            self._is_loading = True
            utils.create_loading_modal(f"Fetching insider transactions for {ticker}...") # Show modal
            self._update_status(f"Fetching insider transactions for {ticker}...")
            dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1) # Clear table content
            # First parameter should be task_id, second parameter is coroutine object
            task_id = f"sec_insider_tx_{ticker}_{self.instance_id}"
            self.task_manager.start_task(
                task_id,
                self.sec_fetcher.get_recent_insider_transactions(ticker=ticker)
            )

    def _fetch_financials_callback(self, sender: int, app_data: Any, user_data: Any) -> None:
        """Callback for the 'Fetch Financials' button.

        Retrieves the ticker, clears the financials display area,
        updates the status, and starts an asynchronous task via TaskManager
        to fetch the financial summary using `sec_fetcher.get_financial_summary`.
        """
        ticker = self._get_ticker()
        if ticker:
            if self._is_loading:
                self._update_status("Please wait for the current request to complete.")
                return # Prevent concurrent loads
            self._is_loading = True
            utils.create_loading_modal(f"Fetching financials for {ticker}...") # Show modal
            self._update_status(f"Fetching financials for {ticker}...")
            dpg.delete_item(self.financials_display_tag, children_only=True) # Clear financials display
            dpg.add_text("Loading...", parent=self.financials_display_tag)
            # First parameter should be task_id, second parameter is coroutine object
            task_id = f"sec_financials_{ticker}_{self.instance_id}"
            self.task_manager.start_task(
                task_id,
                self.sec_fetcher.get_financial_summary(ticker=ticker)
            )

    def _save_fetched_data_callback(self, sender: int, app_data: Any, user_data: Any) -> None:
        """Callback for the 'Save Fetched Data' button.

        Saves the most recently successfully fetched filings, transactions,
        and financials data for the current ticker to JSON files in data/debug_dumps/.
        """
        ticker = self._last_requested_ticker # Use the last ticker we attempted to fetch for
        if not ticker:
            self._update_status("Error: No ticker data has been fetched yet.")
            return

        import json
        import os
        from datetime import datetime

        dump_dir = os.path.join("data", "debug_dumps")
        os.makedirs(dump_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        saved_files = []

        try:
            # Save filings
            if self._last_fetched_filings:
                filename = os.path.join(dump_dir, f"{ticker}_filings_{timestamp}.json")
                with open(filename, 'w') as f:
                    json.dump(self._last_fetched_filings, f, indent=2)
                saved_files.append(filename)

            # Save transactions
            if self._last_fetched_transactions:
                filename = os.path.join(dump_dir, f"{ticker}_transactions_{timestamp}.json")
                with open(filename, 'w') as f:
                    json.dump(self._last_fetched_transactions, f, indent=2)
                saved_files.append(filename)

            # Save financials
            if self._last_fetched_financials:
                filename = os.path.join(dump_dir, f"{ticker}_financials_{timestamp}.json")
                with open(filename, 'w') as f:
                    json.dump(self._last_fetched_financials, f, indent=2)
                saved_files.append(filename)

            if saved_files:
                self._update_status(f"Saved data for {ticker} to {len(saved_files)} file(s) in {dump_dir}")
                logging.info(f"Saved data dump for {ticker}: {saved_files}")
            else:
                self._update_status(f"No fetched data available to save for {ticker}.")

        except Exception as e:
            error_msg = f"Error saving data dump for {ticker}: {e}"
            self._update_status(error_msg)
            logging.error(error_msg, exc_info=True)

    # --- Generic Task Handlers ---

    def _handle_task_success(self, **kwargs) -> None:
        """Handles TASK_SUCCESS signals emitted by the TaskManager.

        Checks if the task is relevant to this widget instance and the currently
        requested ticker (or accession number for content fetches).
        Routes the result to the appropriate internal update handler
        (`_handle_filings_update`, `_handle_insider_tx_update`, `_handle_financials_update`,
        or `_display_filing_content`).

        Args:
            **kwargs: Keyword arguments from the signal, expected to include
                      `task_name` (str) and `result` (Any).
        """
        task_name = kwargs.get('task_name', '')
        result = kwargs.get('result')

        # Check if this task belongs to this widget instance
        if not task_name.endswith(self.instance_id):
            return # Ignore tasks not meant for this instance

        # Extract ticker or other relevant ID based on task name format
        ticker_from_task = None
        accession_no_from_task = None

        parts = task_name.split('_')
        if len(parts) >= 3 and parts[0] == 'sec': # Need at least sec_TYPE_ID
            task_type = parts[1]
            if task_type == 'fetch' and parts[2] == 'content': # Check for sec_fetch_content_ACCNO_instanceid
                if len(parts) >= 5:
                    accession_no_from_task = parts[3]
            elif task_type == 'filings': # sec_filings_TICKER_FORM_instanceid
                if len(parts) >= 5:
                    try:
                        ticker_from_task = parts[2]
                    except IndexError: pass
            elif task_type == 'insider' and parts[2] == 'tx': # sec_insider_tx_TICKER_instanceid
                if len(parts) >= 5:
                    try:
                        ticker_from_task = parts[3]
                    except IndexError: pass
            elif task_type == 'financials': # sec_financials_TICKER_instanceid
                if len(parts) >= 4:
                    try:
                        ticker_from_task = parts[2]
                    except IndexError: pass
            else:
                logging.warning(f"SECFilingViewer {self.instance_id}: Unrecognized sec task format: {task_name}")

        # Log extracted identifiers for debugging
        # logging.debug(f"Parsed task: {task_name} -> Type: {parts[1] if len(parts)>1 else 'N/A'}, Ticker: {ticker_from_task}, AccNo: {accession_no_from_task}")

        # --- Handling based on task type --- #

        # Handle Filing Content Fetch
        if task_name.startswith('sec_fetch_content_') and accession_no_from_task:
            self._update_status(f"Content loaded for {accession_no_from_task}.")
            # Extract document name if it's part of the task name
            doc_name_from_task = None
            if len(parts) >= 6 and parts[1] == 'fetch' and parts[2] == 'content': # Format: sec_fetch_content_ACCNO_DOCNAME_instanceid
                doc_name_from_task = parts[4] # Assuming doc name is the 4th part

            self._display_filing_content(accession_no_from_task, result, document_name=doc_name_from_task or "Document") # result should be the content string
            return # Handled

        # Handle Filing Document List Fetch
        if task_name.startswith('sec_list_docs_'):
            # Extract accession number from task name: sec_list_docs_ACCNO_instanceid
            acc_no_list_task = None
            if len(parts) >= 4 and parts[0] == 'sec' and parts[1] == 'list' and parts[2] == 'docs':
                 acc_no_list_task = parts[3]
            
            if acc_no_list_task:
                 self._update_status(f"Document list loaded for {acc_no_list_task}.")
                 self._display_filing_document_list(acc_no_list_task, result) # result is the list of documents
            else:
                 logging.warning(f"Could not parse accession number from list_docs task: {task_name}")
            return # Handled

        # --- Original Handling for Ticker-Based Tasks --- #

        # Verify ticker matches the last requested one for this widget
        if not ticker_from_task or ticker_from_task != self._last_requested_ticker:
            logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring task success for {task_name} (ticker mismatch: expected {self._last_requested_ticker}, got {ticker_from_task})")
            return

        # Route based on task type prefix
        if task_name.startswith('sec_filings_'):
            self._handle_filings_update(filings=result, ticker=ticker_from_task)
        elif task_name.startswith('sec_insider_tx_'):
            self._handle_insider_tx_update(transactions=result, ticker=ticker_from_task)
        elif task_name.startswith('sec_financials_'):
            self._handle_financials_update(financials=result, ticker=ticker_from_task)
        else:
            # Log if a task succeeded but wasn't handled (should be caught by earlier checks)
            logging.debug(f"SECFilingViewer {self.instance_id}: Received unhandled successful task: {task_name}")

        # --- Delete loading modal --- #
        if self._is_loading:
             if dpg.does_item_exist("loading_modal"): # Use the tag from utils
                  utils.delete_popup_modal("loading_modal")
             self._is_loading = False # Reset loading flag

    def _handle_task_error(self, **kwargs) -> None:
        """Handles TASK_ERROR signals emitted by the TaskManager.

        Checks if the task is relevant to this widget instance and the currently
        requested ticker.
        Updates the status bar with an error message and logs the error.
        Optionally clears the relevant data section in the UI.

        Args:
            **kwargs: Keyword arguments from the signal, expected to include
                      `task_name` (str) and `error` (Exception).
        """
        task_name = kwargs.get('task_name', '')
        error = kwargs.get('error')

        # Check if this task belongs to this widget instance
        if not task_name.endswith(self.instance_id):
            # logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring task error {task_name} (instance mismatch)")
            return # Ignore tasks not meant for this instance

        # Extract ticker from task name (assuming format like "sec_TYPE_TICKER_[FORM_]_instanceid")
        ticker_from_task = None
        try:
            parts = task_name.split('_')
            if len(parts) >= 4 and parts[0] == 'sec':
                 # Ticker is consistently the 3rd part (index 2)
                 ticker_from_task = parts[2]
        except IndexError:
             logging.warning(f"SECFilingViewer {self.instance_id}: Could not parse ticker from error task name: {task_name}")
             ticker_from_task = None

        # Only update status if the error is for the currently relevant ticker
        # And if we successfully extracted the ticker
        if ticker_from_task and ticker_from_task == self._last_requested_ticker:
            # Construct a user-friendly error message
            error_message = f"Error fetching data for {ticker_from_task} ({parts[1] if len(parts)>1 else 'task'}): {str(error)}"
            self._update_status(error_message)
            logging.error(f"Task Error ({task_name}): {error}")
            # Optionally clear the specific section that failed
            if task_name.startswith('sec_filings_'):
                 dpg.delete_item(self.filings_table_tag, children_only=True, slot=1)
                 # Add error message row?
            elif task_name.startswith('sec_insider_tx_'):
                 dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1)
            elif task_name.startswith('sec_financials_'):
                 dpg.delete_item(self.financials_display_tag, children_only=True)
                 dpg.add_text(f"Error loading financials: {error}", parent=self.financials_display_tag, color=(255, 0, 0))

        # --- Delete loading modal --- #
        if self._is_loading:
             if dpg.does_item_exist("loading_modal"): # Use the tag from utils
                  utils.delete_popup_modal("loading_modal")
             self._is_loading = False # Reset loading flag

    def _handle_filings_update(self, **kwargs) -> None:
        """Internal handler to update the filings table with new data.

        Triggered by `_handle_task_success` when a relevant 'sec_filings_...' task completes.
        Clears the existing table content and populates it with the fetched filings.
        Adds a "View" button for each filing to fetch its content.

        Args:
            **kwargs: Keyword arguments, expected to include `ticker` (str) and `filings` (List[Dict]).
        """
        ticker = kwargs.get('ticker')
        filings = kwargs.get('filings', [])

        if not dpg.does_item_exist(self.window_tag) or ticker != self._last_requested_ticker:
            logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring filings update for {ticker} (current: {self._last_requested_ticker}) or window closed.")
            return

        self._update_status(f"Successfully loaded {len(filings)} filings for {ticker}.")
        dpg.delete_item(self.filings_table_tag, children_only=True, slot=1) # Clear existing rows
        self._last_fetched_filings = filings # Store fetched data

        for filing in filings:
            with dpg.table_row(parent=self.filings_table_tag):
                dpg.add_text(filing.get('accession_no', 'N/A'))
                dpg.add_text(filing.get('form', 'N/A'))
                dpg.add_text(filing.get('filing_date', 'N/A'))
                dpg.add_text(filing.get('report_date', 'N/A'))
                # Add a "View" button to fetch and display content
                accession_no = filing.get('accession_no')
                primary_doc = filing.get('primary_document')
                # Only add button if we have the necessary info
                if accession_no and primary_doc:
                    user_data_dict = {
                        'accession_no': accession_no,
                        'primary_document': primary_doc
                    }
                    dpg.add_button(label="View", callback=self._request_filing_content_callback, user_data=user_data_dict)
                else:
                    # Log if view button cannot be created due to missing info
                    if not accession_no:
                        logging.warning(f"Cannot create View button for filing on {filing.get('filing_date')}: Missing accession_no")
                    if not primary_doc:
                         logging.warning(f"Cannot create View button for filing {accession_no}: Missing primary_document")
                    dpg.add_text("N/A") # Display N/A if button can't be created

    def _handle_insider_tx_update(self, **kwargs) -> None:
        """Internal handler to update the insider transactions table with new data.

        Triggered by `_handle_task_success` when a relevant 'sec_insider_tx_...' task completes.
        Clears the existing table content and populates it with the fetched transactions.
        Formats data (dates, numbers, filer names) and applies color coding to transaction types.
        Adds a "View" button for each transaction to open the source filing URL.

        Args:
            **kwargs: Keyword arguments, expected to include `ticker` (str) and `transactions` (List[Dict]).
        """
        ticker = kwargs.get('ticker')
        transactions = kwargs.get('transactions', [])

        if not dpg.does_item_exist(self.window_tag) or ticker != self._last_requested_ticker:
            logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring insider tx update for {ticker} (current: {self._last_requested_ticker}) or window closed.")
            return

        self._update_status(f"Successfully loaded {len(transactions)} insider transactions for {ticker}.")
        dpg.delete_item(self.insider_tx_table_tag, children_only=True, slot=1) # Clear existing rows
        self._last_fetched_transactions = transactions # Store fetched data

        for tx in transactions:
            with dpg.table_row(parent=self.insider_tx_table_tag):
                # Filer name - truncate if too long
                filer = tx.get('filer', 'N/A')
                if filer and len(filer) > 25:
                    filer = filer[:22] + "..."
                dpg.add_text(filer)
                
                # Add Position
                position = tx.get('position', 'N/A')
                dpg.add_text(position)
                
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
                
                # Transaction type with color coding for purchase/sale
                tx_type = tx.get('type', 'N/A')
                tx_type_color = None
                
                # Color-code different transaction types
                if tx_type.lower().startswith(('purchase', 'buy', 'acquire')):
                    tx_type_color = (0, 180, 0)  # Green for purchases
                elif tx_type.lower().startswith(('sale', 'sell', 'dispose')):
                    tx_type_color = (180, 0, 0)  # Red for sales
                
                if tx_type_color:
                    dpg.add_text(tx_type, color=tx_type_color)
                else:
                    dpg.add_text(tx_type)
                
                # Format numerical values properly
                shares = tx.get('shares', 'N/A')
                if shares == 'N/A':
                    dpg.add_text('N/A')
                elif isinstance(shares, (int, float)):
                    dpg.add_text(f"{shares:,.0f}")  # No decimal places for shares
                else:
                    dpg.add_text(str(shares))
                
                price = tx.get('price', 'N/A')
                if price == 'N/A':
                    dpg.add_text('N/A')
                elif isinstance(price, (int, float)):
                    dpg.add_text(f"${price:.2f}")
                else:
                    dpg.add_text(str(price))
                
                value = tx.get('value', 'N/A')
                if value == 'N/A':
                    dpg.add_text('N/A')
                elif isinstance(value, (int, float)):
                    dpg.add_text(f"${value:,.2f}")
                else:
                    dpg.add_text(str(value))
                
                url = tx.get('form_url', None)
                if url:
                    dpg.add_button(label="View", callback=self._open_url, user_data=url)
                else:
                    dpg.add_text("N/A")

    def _handle_financials_update(self, **kwargs) -> None:
        """Internal handler to update the financials display area with new data.

        Triggered by `_handle_task_success` when a relevant 'sec_financials_...' task completes.
        Clears the existing content and displays the fetched financial summary metrics
        with appropriate formatting using the `_add_financial_metric` helper.

        Args:
            **kwargs: Keyword arguments, expected to include `ticker` (str) and `financials` (Optional[Dict]).
        """
        ticker = kwargs.get('ticker')
        financials = kwargs.get('financials')

        if not dpg.does_item_exist(self.window_tag) or ticker != self._last_requested_ticker:
             logging.debug(f"SECFilingViewer {self.instance_id}: Ignoring financials update for {ticker} (current: {self._last_requested_ticker}) or window closed.")
             return

        self._update_status(f"Successfully loaded financials for {ticker}.")
        dpg.delete_item(self.financials_display_tag, children_only=True) # Clear previous content
        self._last_fetched_financials = financials # Store fetched data

        if financials:
            # Display source filing info
            dpg.add_text(f"Source: {financials.get('source_form', 'N/A')}", parent=self.financials_display_tag)
            dpg.add_text(f"Period End: {financials.get('period_end', 'N/A')}", parent=self.financials_display_tag)
            
            # Display financial metrics with proper formatting
            self._add_financial_metric("Revenue", financials.get('revenue', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Net Income", financials.get('net_income', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("EPS (Basic)", financials.get('eps', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Total Assets", financials.get('assets', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Total Liabilities", financials.get('liabilities', 'N/A'), self.financials_display_tag)
            self._add_financial_metric("Stockholders' Equity", financials.get('equity', 'N/A'), self.financials_display_tag)
            
            # Add cash flow data if available
            if any(key in financials for key in ['operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow']):
                dpg.add_separator(parent=self.financials_display_tag)
                dpg.add_text("Cash Flow:", parent=self.financials_display_tag)
                self._add_financial_metric("Operating Cash Flow", financials.get('operating_cash_flow', 'N/A'), self.financials_display_tag)
                self._add_financial_metric("Investing Cash Flow", financials.get('investing_cash_flow', 'N/A'), self.financials_display_tag)
                self._add_financial_metric("Financing Cash Flow", financials.get('financing_cash_flow', 'N/A'), self.financials_display_tag)
        else:
            dpg.add_text("Financial data not available.", parent=self.financials_display_tag)

    def _add_financial_metric(self, label, value, parent):
        """Helper method to add a formatted financial metric text element to a parent container.

        Formats numerical values as currency (except EPS) or leaves them as strings.

        Args:
            label (str): The label for the metric (e.g., "Revenue").
            value (Any): The value of the metric.
            parent (Union[int, str]): The DPG tag/ID of the parent container.
        """
        if isinstance(value, (int, float)):
            # Format large numbers with commas and 2 decimal places if it's a dollar amount
            formatted_value = f"${value:,.2f}" if label.lower() not in ["eps (basic)", "eps (diluted)"] else f"{value:.2f}"
            dpg.add_text(f"{label}: {formatted_value}", parent=parent)
        else:
            dpg.add_text(f"{label}: {value}", parent=parent)
    
    def _request_filing_content_callback(self, sender, app_data, user_data):
        """Callback for the 'View' button in the filings table.

        Starts a task to fetch the list of documents for the selected filing.
        The result is handled by _handle_task_success, which calls
        _display_filing_document_list.
        """
        if not isinstance(user_data, dict):
            logging.error(f"_request_filing_content_callback: Invalid user_data type: {type(user_data)}")
            self._update_status("Error: Internal data mismatch for View button.")
            return

        accession_no = user_data.get('accession_no')
        # primary_doc = user_data.get('primary_document') # We don't need primary_doc directly anymore

        # Get the current ticker from the input field
        ticker = self._get_ticker()

        if not accession_no:
            logging.error(f"_request_filing_content_callback: Missing accession_no")
            self._update_status("Error: Missing accession number to list documents.")
            return

        if self._is_loading:
            self._update_status("Please wait for the current request to complete.")
            return
        self._is_loading = True
        utils.create_loading_modal(f"Fetching document list for {accession_no}...") # Show modal
        logging.debug(f"Requesting document list for {accession_no}, ticker: {ticker}")
        self._update_status(f"Fetching document list for {accession_no}...")

        # Create task ID for fetching the document list
        task_id = f"sec_list_docs_{accession_no}_{self.instance_id}"

        # Start background task to get the list of documents
        self.task_manager.start_task(
            task_id,
            self.sec_fetcher.document_handler.get_filing_documents_list(accession_no=accession_no, ticker=ticker)
        )

    def _request_specific_document_content_callback(self, sender, app_data, user_data):
        """Callback for the 'View' button *within* the document list modal.

        Starts a task to fetch the content of a *specific* document from a filing.
        The result is handled by _handle_task_success, which calls
        _display_filing_content.
        """
        if not isinstance(user_data, dict):
            logging.error(f"_request_specific_document_content_callback: Invalid user_data: {user_data}")
            return

        accession_no = user_data.get('accession_no')
        document_name = user_data.get('document_name')
        ticker = user_data.get('ticker')

        if not accession_no or not document_name:
            logging.error(f"Missing accession_no or document_name for content fetch.")
            # Optionally update status in the main window or the modal?
            return

        if self._is_loading:
            self._update_status("Please wait for the current request to complete.")
            return
        self._is_loading = True
        utils.create_loading_modal(f"Fetching content for {document_name}...") # Show modal
        logging.debug(f"Requesting content for {accession_no}, specific doc: {document_name}, ticker: {ticker}")
        self._update_status(f"Fetching content for {document_name} ({accession_no})...")

        # Create task ID for fetching specific document content
        task_id = f"sec_fetch_content_{accession_no}_{document_name}_{self.instance_id}"

        # Start background task
        self.task_manager.start_task(
            task_id,
            self.sec_fetcher.document_handler.fetch_filing_document(accession_no=accession_no, primary_doc=document_name, ticker=ticker)
        )

    def _open_url(self, sender, app_data, user_data):
        """Callback to open a URL (passed in user_data) in the default web browser.

        Handles basic URL validation and attempts to add scheme if missing.
        Updates status bar on error.
        """
        url = user_data # URL is passed via user_data
        import webbrowser
        try:
            logging.debug(f"_open_url: Received user_data (URL): {url} (type: {type(url)})") # Log entry
            if not url:
                logging.error(f"Invalid URL: URL is None or empty in user_data")
                self._update_status(f"Error: URL is missing. Unable to open browser.")
                return

            if isinstance(url, str) and url.startswith(('http://', 'https://', 'www.')):
                logging.debug(f"_open_url: Attempting to open valid URL: {url}") # Log before opening
                webbrowser.open(url)
            else:
                # If URL doesn't have proper scheme, try to add it
                if isinstance(url, str) and not url.startswith(('http://', 'https://')):
                    if url.startswith('www.'):
                        url = 'https://' + url
                        webbrowser.open(url)
                        logging.debug(f"Opening modified URL in browser: {url}")
                    elif url.startswith('/'):
                        # Relative URL, add SEC domain
                        url = 'https://www.sec.gov' + url
                        webbrowser.open(url)
                        logging.debug(f"Opening SEC URL in browser: {url}")
                    else:
                        logging.error(f"Invalid URL format: {url}")
                        self._update_status(f"Error: Invalid URL format. Unable to open browser.")
                else:
                    logging.error(f"Invalid URL format: {url}")
                    self._update_status(f"Error: Invalid URL format. Unable to open browser.")
        except Exception as e:
            logging.error(f"Error opening URL {url}: {e}", exc_info=True)
            self._update_status(f"Error opening URL: {str(e)}")

    def close(self) -> None:
        """Clean up when the widget is closed."""
        # Unregister signal handlers? Depends on Emitter implementation.
        # If emitter holds strong refs, unregistering might be needed.
        # Assuming weak refs or automatic cleanup for now.
        logging.info(f"Closing SECFilingViewer {self.instance_id}.")
        super().close()

    def _display_filing_document_list(self, accession_no: str, documents: Optional[List[Dict]]):
        """Displays the list of documents for a filing in a modal window.

        Each document has a 'View' button to fetch its specific content.

        Args:
            accession_no (str): The accession number (for modal title).
            documents (Optional[List[Dict]]): List of document info dicts, or None if error.
        """
        list_modal_id = dpg.generate_uuid()
        list_table_id = dpg.generate_uuid()

        with dpg.window(label=f"Documents for Filing: {accession_no}", modal=True, show=True, id=list_modal_id,
                          tag=f"filing_doc_list_modal_{accession_no}", width=600, height=400,
                          on_close=lambda: dpg.delete_item(list_modal_id)):

            if documents is None:
                dpg.add_text("Error: Could not load document list.")
                return
            if not documents:
                dpg.add_text("No documents found in the index for this filing.")
                return

            dpg.add_text(f"Found {len(documents)} documents:")
            with dpg.table(tag=list_table_id, header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp,
                           borders_outerH=True, borders_innerV=True, borders_innerH=True, borders_outerV=True):
                dpg.add_table_column(label="Filename")
                dpg.add_table_column(label="Type")
                dpg.add_table_column(label="Size (Bytes)")
                dpg.add_table_column(label="Action")

                ticker = self._last_requested_ticker # Get ticker for the context

                for doc in documents:
                    with dpg.table_row():
                        dpg.add_text(doc.get('name', 'N/A'))
                        dpg.add_text(doc.get('type', 'N/A'))
                        # Format size
                        size = doc.get('size', 'N/A')
                        try:
                            size_str = f"{int(size):,}" if size is not None else "N/A"
                        except (ValueError, TypeError):
                            size_str = str(size)
                        dpg.add_text(size_str)

                        # Button to view this specific document
                        if doc.get('name'):
                            view_user_data = {
                                'accession_no': accession_no,
                                'document_name': doc['name'],
                                'ticker': ticker
                            }
                            dpg.add_button(label="View Content",
                                           callback=self._request_specific_document_content_callback,
                                           user_data=view_user_data)
                        else:
                            dpg.add_text("N/A")

    def _display_filing_content(self, accession_no: str, content: Optional[str], document_name: str = "Document"):
        """Displays fetched filing content in a modal window.

        Creates a modal window with a read-only, multiline input text
        field to show the document content.

        Args:
            accession_no (str): The accession number of the filing (used in modal title).
            content (Optional[str]): The textual content of the filing document.
                                   Displays an error message if None.
            document_name (str): The name of the document (used in modal title).
        """
        modal_id = dpg.generate_uuid()
        content_area_id = dpg.generate_uuid()

        if not content:
            content = "Error: Could not load document content."
            logging.warning(f"Attempted to display empty content for {accession_no}")

        # Estimate window size (adjust as needed)
        # Crude estimation based on content length, might need refinement
        width = 800
        height = 600
        if len(content) > 50000: # Very large content
            width = 1000
            height = 750

        # Use document_name in the label if available
        label = f"Content: {document_name} ({accession_no})"

        with dpg.window(label=label, modal=True, show=True, id=modal_id,
                          tag=f"filing_content_modal_{accession_no}_{dpg.generate_uuid()}", # Add uuid for uniqueness
                          width=width, height=height, on_close=lambda: dpg.delete_item(modal_id)):
            # Use InputText for potentially large, scrollable, selectable text
            dpg.add_input_text(tag=content_area_id, default_value=content, multiline=True, readonly=True, width=-1, height=-1) # Fill window

        # Auto-adjust height based on content? DPG might not support this easily for modals.
        # dpg.configure_item(content_area_id, height=dpg.get_text_size(content, wrap_width=width-20)[1] + 40)
        # dpg.configure_item(modal_id, height=dpg.get_item_height(content_area_id) + 60)
    
    def get_requirements(self) -> Dict[str, Any]:
        """This widget fetches data on demand, so it has no streaming requirements."""
        return {}

    def get_config(self) -> Dict[str, Any]:
        """Returns the configuration needed to recreate this SECFilingViewer.

        In this case, it includes the last successfully requested ticker.
        """
        return {
            "ticker": self._last_requested_ticker if self._last_requested_ticker else "" # Return empty string if None
        }
        
# Example Integration (in Viewport or DashboardManager):
# from trade_suite.gui.widgets.sec_filing_viewer import SECFilingViewer
#
# sec_viewer = SECFilingViewer(
#     core=core_instance,
#     instance_id="example_instance_id",
#     ticker="AAPL"
# )
# sec_viewer.create() # Or add to docking layout 