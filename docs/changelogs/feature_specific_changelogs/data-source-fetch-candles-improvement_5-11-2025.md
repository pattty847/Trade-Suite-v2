# CCXT Data Fetching Enhancements

**Date:** 2025-05-11

## Summary

This update significantly refactors the historical OHLCV data fetching logic within `trade_suite/data/data_source.py`. The primary goal was to improve the reliability and accuracy of data collection, especially for newly listed assets or when populating data for symbols with no prior cache. These changes have resulted in faster and more robust data acquisition.

## Key Changes

1.  **Intelligent First Candle Detection & Dynamic Fetch Start**:
    *   When fetching data for a symbol where no local cache exists (or the cache is empty), if the initial attempt (based on the global `since` parameter) yields no data, the system now intelligently attempts to find the asset's *actual* first traded candle.
    *   This is achieved by querying the exchange for the earliest possible candle (e.g., `since=1ms`, `limit=1`).
    *   If the asset's true listing date is found to be later than the initially requested `since` date, the data fetching process for that specific symbol will commence from its actual listing date. This ensures that data for recently listed assets (like PEPE, WIF in the logs) is correctly captured from their inception.

2.  **Restoration and Enhancement of `retry_fetch_ohlcv`**:
    *   The `retry_fetch_ohlcv` asynchronous method was re-integrated into the `Data` class.
    *   It now correctly handles an optional `limit` parameter, crucial for the "first candle" detection and allowing for more controlled batch fetching.
    *   The method includes robust retry mechanisms with exponential backoff for common API issues such as rate limits and network errors, improving the resilience of data fetching operations.

3.  **Improved Cache Management**:
    *   Enhanced logic for loading, prepending, and appending data to local CSV cache files.
    *   More graceful handling of scenarios involving empty or potentially malformed cache files.
    *   The system now correctly identifies when to prepend older data, append newer data, or perform a full historical fetch for a symbol.

4.  **Efficient Handling of Data Gaps**:
    *   By accurately determining the actual listing date for assets, the system avoids unnecessary API calls for periods before an asset existed.
    *   If no data is genuinely available for a symbol (even after checking its first candle), an empty DataFrame is now correctly handled and stored, preventing downstream errors in analysis scripts.

5.  **Enhanced Logging**:
    *   Added more detailed debug and info logs throughout the `fetch_and_process_candles` and `retry_fetch_ohlcv` methods, providing better traceability of the data fetching process.

## Impact

*   **Accuracy**: Ensures that historical data for all assets, including those listed after a globally set `since` date, is fetched from their true listing date.
*   **Reliability**: Reduces errors caused by missing data for new assets or unexpected API responses.
*   **Efficiency**: Optimizes API calls by fetching data only from relevant periods and improves overall data pipeline robustness.
*   **User Experience**: Provides clearer logs and more predictable behavior when fetching historical market data.
