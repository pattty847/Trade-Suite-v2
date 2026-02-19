# DataFacade Refactor

**Date:** 2025-06-05

## Summary

The monolithic `Data` class was decomposed into specialized components:
`CacheStore` for all cache I/O, `CandleFetcher` for CCXT interactions, and
`Streamer` for live WebSocket data. `trade_suite/data/data_source.py` now
exposes a thin `DataFacade` that orchestrates these helpers. This change clarifies
responsibilities and prepares the code base for future testing.

## Impact

* Widgets and services interact with `DataFacade` using the same API, but
  performance improves thanks to better separation of duties.
* The architecture documentation and diagrams were updated accordingly.
