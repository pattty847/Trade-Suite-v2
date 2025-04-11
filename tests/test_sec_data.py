#!/usr/bin/env python
"""
Demo script to test the SEC data fetcher and print the actual data structures.
This will help update the SECFilingViewer to display the data correctly.
"""

import asyncio
import os
import logging
import json
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Import our SEC data fetcher
from trade_suite.data.sec_data import SECDataFetcher
from trade_suite.gui.signals import SignalEmitter, Signals

class TestEmitter(SignalEmitter):
    """Simple emitter implementation that prints signals and saves data for inspection."""
    
    def __init__(self):
        super().__init__()
        self.received_data = {}
    
    def emit(self, signal, **kwargs):
        """Override emit to capture and print the data."""
        signal_name = signal.name if hasattr(signal, "name") else str(signal)
        logging.info(f"Signal emitted: {signal_name}")
        
        # Store the data for later inspection
        if signal_name not in self.received_data:
            self.received_data[signal_name] = []
        self.received_data[signal_name].append(kwargs)
        
        # Print a simplified version
        if signal in [Signals.SEC_FILINGS_UPDATE, Signals.SEC_INSIDER_TX_UPDATE, Signals.SEC_FINANCIALS_UPDATE]:
            print(f"\n--- {signal_name} ---")
            
            # Special handling for each signal type
            if signal == Signals.SEC_FILINGS_UPDATE:
                ticker = kwargs.get('ticker')
                filings = kwargs.get('filings', [])
                print(f"Ticker: {ticker}")
                print(f"Number of filings: {len(filings)}")
                
                if filings:
                    print("\nSample filing keys:")
                    print(list(filings[0].keys()))
                    
                    print("\nFirst filing data:")
                    for k, v in filings[0].items():
                        print(f"  {k}: {v}")
            
            elif signal == Signals.SEC_INSIDER_TX_UPDATE:
                ticker = kwargs.get('ticker')
                transactions = kwargs.get('transactions', [])
                print(f"Ticker: {ticker}")
                print(f"Number of transactions: {len(transactions)}")
                
                if transactions:
                    print("\nSample transaction keys:")
                    print(list(transactions[0].keys()))
                    
                    print("\nFirst transaction data:")
                    for k, v in transactions[0].items():
                        print(f"  {k}: {v}")
            
            elif signal == Signals.SEC_FINANCIALS_UPDATE:
                ticker = kwargs.get('ticker')
                financials = kwargs.get('financials', {})
                print(f"Ticker: {ticker}")
                
                if financials:
                    print("\nFinancials keys:")
                    print(list(financials.keys()))
                    
                    print("\nFinancials data:")
                    for k, v in financials.items():
                        print(f"  {k}: {v}")
        
        elif signal == Signals.SEC_DATA_FETCH_ERROR:
            print(f"\n!!! ERROR: {kwargs.get('error')} !!!")
            print(f"Data type: {kwargs.get('data_type')}")
            print(f"Ticker: {kwargs.get('ticker')}")

    def process_signal_queue(self):
        """No queue to process in this implementation."""
        pass

async def run_test(ticker="AAPL"):
    """Run tests for all SEC data fetcher methods."""
    # Create the emitter and SEC data fetcher
    emitter = TestEmitter()
    sec_fetcher = SECDataFetcher(emitter)
    
    try:
        # Test all three methods
        print(f"\n=========== Testing fetch_filings for {ticker} ===========")
        await sec_fetcher.fetch_filings(ticker, max_filings=5)
        
        print(f"\n=========== Testing fetch_insider_transactions for {ticker} ===========")
        await sec_fetcher.fetch_insider_transactions(ticker, max_tx=5)
        
        print(f"\n=========== Testing fetch_financials for {ticker} ===========")
        await sec_fetcher.fetch_financials(ticker)
        
        # Print a summary of what was found
        print("\n=========== Summary ===========")
        for signal_name, data_list in emitter.received_data.items():
            print(f"{signal_name}: {len(data_list)} signals received")
            
        # Save the raw data to a file for further analysis
        with open('sec_data_sample.json', 'w') as f:
            # Convert to a serializable format
            serializable_data = {}
            for signal_name, data_list in emitter.received_data.items():
                serializable_data[signal_name] = []
                for data in data_list:
                    serializable_data[signal_name].append({
                        k: (str(v) if not isinstance(v, (dict, list, str, int, float, bool, type(None))) else v)
                        for k, v in data.items()
                    })
            json.dump(serializable_data, f, indent=2)
        print("Raw data saved to sec_data_sample.json")
        
    except Exception as e:
        logging.error(f"Error in test: {e}", exc_info=True)
    finally:
        # Clean up
        sec_fetcher.close()

def print_edgartools_info():
    """Print information about the edgartools package to verify it's working."""
    try:
        from edgar import __version__
        print(f"edgartools version: {__version__}")
    except ImportError:
        print("edgartools not installed or version not available")

if __name__ == "__main__":
    # Check if edgartools is available
    print_edgartools_info()
    
    # Run the tests
    ticker = input("Enter ticker to test (default is AAPL): ").strip() or "AAPL"
    asyncio.run(run_test(ticker))
 