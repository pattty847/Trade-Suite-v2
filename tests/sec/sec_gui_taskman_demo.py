# Assuming this code is part of your main GUI class (e.g., Viewport or similar)
# where you have access to signal_emitter and task_manager instances.

from typing import Dict, List
import dearpygui.dearpygui as dpg
import logging
from concurrent.futures import ThreadPoolExecutor # Might be needed if sharing executor

# Import your components
from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.task_manager import TaskManager # Assuming path
from trade_suite.data.sec_data import SECDataFetcher

class GuiManager: # Example class structure
    def __init__(self):
        self.signal_emitter = SignalEmitter()
        # Initialize TaskManager (assuming it's needed here or passed in)
        self.task_manager = TaskManager()
        # Initialize SECDataFetcher, passing the emitter
        # Optional: Pass a shared ThreadPoolExecutor if you have one
        self.sec_fetcher = SECDataFetcher(emitter=self.signal_emitter)

        # --- Setup Dear PyGui ---
        dpg.create_context()
        dpg.create_viewport(title='Trade Suite', width=1200, height=800)
        dpg.setup_dearpygui()

        self._create_ui_layout() # Method to build the UI
        self._register_signal_handlers()

        # Register cleanup method for the DPG exit callback
        dpg.set_exit_callback(self._cleanup)

        dpg.show_viewport()
        # --- Main Render Loop ---
        # dpg.start_dearpygui() # Old way
        # New way (more control)
        while dpg.is_dearpygui_running():
            # Process signals from background threads BEFORE rendering the frame
            self.signal_emitter.process_signal_queue()
            # Render the frame
            dpg.render_dearpygui_frame()

        dpg.destroy_context()


    def _create_ui_layout(self):
        # --- Example: Add an SEC Data Window ---
        # (Could be within a docking setup)
        with dpg.window(label="SEC Data", tag="sec_data_window", width=600, height=400):
            dpg.add_input_text(label="Ticker", tag="sec_ticker_input")

            with dpg.group(horizontal=True):
                dpg.add_button(label="Fetch Filings", callback=self._fetch_filings_callback)
                dpg.add_button(label="Fetch Insider Tx", callback=self._fetch_insider_tx_callback)
                dpg.add_button(label="Fetch Financials", callback=self._fetch_financials_callback)

            dpg.add_separator()
            dpg.add_text("Filings:", tag="sec_filings_header")
            # --- Filings Table ---
            with dpg.table(tag="sec_filings_table", header_row=True, borders_innerH=True,
                           borders_outerH=True, borders_innerV=True, borders_outerV=True,
                           policy=dpg.mvTable_SizingStretchProp, row_background=True):
                dpg.add_table_column(label="Acc No")
                dpg.add_table_column(label="Form")
                dpg.add_table_column(label="Filing Date")
                dpg.add_table_column(label="Report Date")

            dpg.add_separator()
            dpg.add_text("Insider Transactions:", tag="sec_insider_tx_header")
             # --- Insider Tx Table ---
            with dpg.table(tag="sec_insider_tx_table", header_row=True, borders_innerH=True,
                           borders_outerH=True, borders_innerV=True, borders_outerV=True,
                           policy=dpg.mvTable_SizingStretchProp, row_background=True):
                dpg.add_table_column(label="Filer") # Placeholder columns
                dpg.add_table_column(label="Date")
                dpg.add_table_column(label="Type")
                dpg.add_table_column(label="Shares")
                dpg.add_table_column(label="Price")
                dpg.add_table_column(label="Value")

            dpg.add_separator()
            dpg.add_text("Financials:", tag="sec_financials_header")
            dpg.add_text("Financial data will appear here.", tag="sec_financials_text", wrap=580) # Wrap text

            dpg.add_separator()
            dpg.add_text("", tag="sec_status_text", color=(255, 255, 0)) # For status/errors


    def _register_signal_handlers(self):
        self.signal_emitter.register(Signals.SEC_FILINGS_UPDATE, self._handle_filings_update)
        self.signal_emitter.register(Signals.SEC_INSIDER_TX_UPDATE, self._handle_insider_tx_update)
        self.signal_emitter.register(Signals.SEC_FINANCIALS_UPDATE, self._handle_financials_update)
        self.signal_emitter.register(Signals.SEC_DATA_FETCH_ERROR, self._handle_sec_error)


    # --- Button Callbacks ---
    def _fetch_filings_callback(self):
        ticker = dpg.get_value("sec_ticker_input")
        if ticker:
            logging.info(f"GUI requesting filings for {ticker}")
            dpg.set_value("sec_status_text", f"Fetching filings for {ticker}...")
            # Clear previous results
            dpg.delete_item("sec_filings_table", children_only=True)
            # Use TaskManager to run the fetch method
            self.task_manager.start_task(self.sec_fetcher.fetch_filings, ticker=ticker)
        else:
             dpg.set_value("sec_status_text", "Please enter a ticker.")

    def _fetch_insider_tx_callback(self):
        ticker = dpg.get_value("sec_ticker_input")
        if ticker:
            logging.info(f"GUI requesting insider tx for {ticker}")
            dpg.set_value("sec_status_text", f"Fetching insider tx for {ticker}...")
            dpg.delete_item("sec_insider_tx_table", children_only=True)
            self.task_manager.start_task(self.sec_fetcher.fetch_insider_transactions, ticker=ticker)
        else:
             dpg.set_value("sec_status_text", "Please enter a ticker.")

    def _fetch_financials_callback(self):
        ticker = dpg.get_value("sec_ticker_input")
        if ticker:
            logging.info(f"GUI requesting financials for {ticker}")
            dpg.set_value("sec_status_text", f"Fetching financials for {ticker}...")
            dpg.set_value("sec_financials_text", "Loading...")
            self.task_manager.start_task(self.sec_fetcher.fetch_financials, ticker=ticker)
        else:
             dpg.set_value("sec_status_text", "Please enter a ticker.")


    # --- Signal Handlers (Callbacks) ---
    def _handle_filings_update(self, ticker: str, filings: List[Dict]):
        # Check if the update is for the currently entered ticker (optional)
        current_ticker = dpg.get_value("sec_ticker_input")
        if ticker.upper() != current_ticker.upper():
            logging.debug(f"Ignoring filings update for {ticker}, current is {current_ticker}")
            return

        logging.info(f"GUI received filings update for {ticker}")
        dpg.set_value("sec_status_text", f"Filings received for {ticker}.")
        # Ensure table is clean before adding new rows
        dpg.delete_item("sec_filings_table", children_only=True)

        for filing in filings:
            with dpg.table_row(parent="sec_filings_table"):
                dpg.add_text(filing.get('accession_no', 'N/A'))
                dpg.add_text(filing.get('form', 'N/A'))
                dpg.add_text(filing.get('filing_date', 'N/A'))
                dpg.add_text(filing.get('report_date', 'N/A'))

    def _handle_insider_tx_update(self, ticker: str, transactions: List[Dict]):
        current_ticker = dpg.get_value("sec_ticker_input")
        if ticker.upper() != current_ticker.upper(): return

        logging.info(f"GUI received insider tx update for {ticker}")
        dpg.set_value("sec_status_text", f"Insider transactions received for {ticker}.")
        dpg.delete_item("sec_insider_tx_table", children_only=True)

        for tx in transactions:
            with dpg.table_row(parent="sec_insider_tx_table"):
                # Adjust .get() calls based on the actual keys in your refined data structure
                dpg.add_text(tx.get('filer', 'N/A'))
                dpg.add_text(tx.get('date', 'N/A'))
                dpg.add_text(tx.get('type', 'N/A'))
                dpg.add_text(str(tx.get('shares', 'N/A'))) # Ensure string
                dpg.add_text(str(tx.get('price', 'N/A'))) # Ensure string
                dpg.add_text(str(tx.get('value', 'N/A'))) # Ensure string


    def _handle_financials_update(self, ticker: str, financials: Dict):
        current_ticker = dpg.get_value("sec_ticker_input")
        if ticker.upper() != current_ticker.upper(): return

        logging.info(f"GUI received financials update for {ticker}")
        dpg.set_value("sec_status_text", f"Financials received for {ticker}.")

        # Format the financials data for display
        financials_text = (
            f"Source: {financials.get('source_form','N/A')} ({financials.get('source_filing','N/A')})\n"
            f"Period End: {financials.get('period_end','N/A')}\n"
            f"Revenue: {financials.get('revenue','N/A')}\n"
            f"Net Income: {financials.get('net_income','N/A')}\n"
            f"EPS: {financials.get('eps','N/A')}\n"
            "(Note: Financial data parsing may be preliminary)"
        )
        dpg.set_value("sec_financials_text", financials_text)

    def _handle_sec_error(self, ticker: str, data_type: str, error: str):
        current_ticker = dpg.get_value("sec_ticker_input")
        # Show error regardless of current ticker, maybe? Or only if relevant.
        # if ticker.upper() != current_ticker.upper(): return

        logging.error(f"GUI received error fetching {data_type} for {ticker}: {error}")
        error_message = f"Error fetching {data_type} for {ticker}: {error}"
        dpg.set_value("sec_status_text", error_message)
        # Maybe clear the relevant loading indicator too
        if data_type == 'financials':
            dpg.set_value("sec_financials_text", "Error loading financials.")


    def _cleanup(self):
        logging.info("GUI initiated cleanup...")
        # Important: Close the SEC fetcher to shut down its thread pool
        self.sec_fetcher.close()
        # Add cleanup for crypto data source, task manager etc.
        self.task_manager.shutdown() # Assuming TaskManager has a shutdown
        logging.info("Cleanup complete.")

# --- To run this example ---
# if __name__ == "__main__":
#     # Setup logging
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(filename)s:%(funcName)s: %(message)s')
#     gui = GuiManager()
#     # The render loop is now inside GuiManager __init__