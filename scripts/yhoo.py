import csv
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta

def fetch_bitcoin_data_and_indicators():
    # Define the start and end dates
    start_date = "2024-04-01"
    # Add buffer for indicator calculation lookback (e.g., 200 days for SMA200)
    # Calculate the actual start date needed
    start_buffer_days = 210 # A bit more than 200 for safety
    fetch_start_date = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=start_buffer_days)).strftime('%Y-%m-%d')
    
    # yfinance fetches data up to, but not including, the end date.
    # So add one day to include today's data if available.
    end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Define output filename
    output_filename = 'bitcoin_closes_indicators_cleaned.csv'

    print(f"Fetching data from {fetch_start_date} to {end_date} (includes buffer for indicators)")

    try:
        # Get Bitcoin data using yfinance
        btc = yf.Ticker("BTC-USD")
        # Fetch historical market data (OHLCV)
        hist = btc.history(start=fetch_start_date, end=end_date)

        if hist.empty:
            print("No data returned from yfinance for the specified range.")
            return

        print(f"Received {len(hist)} data points (including buffer) from yfinance.")

        # Calculate indicators using pandas_ta
        print("Calculating indicators...")
        # Calculate SMAs
        hist.ta.sma(length=25, append=True) # SMA_25
        hist.ta.sma(length=50, append=True) # SMA_50
        hist.ta.sma(length=100, append=True) # SMA_100
        hist.ta.sma(length=200, append=True) # SMA_200
        # Calculate RSI
        hist.ta.rsi(length=14, append=True) # RSI_14
        # Calculate MFI (requires high, low, close, volume)
        hist.ta.mfi(length=14, append=True) # MFI_14

        # Select only the necessary columns + indicators
        # Ensure column names match what pandas_ta generates (check case sensitivity)
        indicator_cols = ['Close', 'SMA_25', 'SMA_50', 'SMA_100', 'SMA_200', 'RSI_14', 'MFI_14']
        # Check if all expected columns exist
        missing_cols = [col for col in indicator_cols if col not in hist.columns]
        if missing_cols:
            print(f"Error: Missing expected indicator columns: {missing_cols}")
            print(f"Available columns: {hist.columns.tolist()}")
            return
            
        final_data = hist[indicator_cols]
        
        # Filter data back to the original requested start date
        final_data = final_data[final_data.index >= start_date]

        # Drop rows with NaN values (resulting from indicator calculations)
        print(f"Original rows from {start_date}: {len(final_data)}")
        final_data_cleaned = final_data.dropna()
        print(f"Rows after removing NaNs: {len(final_data_cleaned)}")

        if final_data_cleaned.empty:
             print(f"No data left after removing NaN values. Increase date range or buffer?")
             return

        # Save the cleaned DataFrame to CSV
        final_data_cleaned.to_csv(output_filename)

        print(f"Cleaned data with indicators saved to '{output_filename}'.")
        print("Columns:", final_data_cleaned.columns.tolist())

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

fetch_bitcoin_data_and_indicators()
