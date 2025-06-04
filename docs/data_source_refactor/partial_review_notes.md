## Additional Notes from Partial Code Review

The audit recorded in `docs/partial_code_review.md` pointed out that the `Data` class still acts as a monolith responsible for exchange access, caching,
aggregation and GUI signal emission. Splitting these responsibilities will make
testing and future maintenance much easier. The decomposition proposal in Phase
2 should therefore be prioritised. In particular:

- Extract cache operations into a `CacheStore` component.
- Move CCXT interaction and retry logic into a `CandleFetcher`.
- Handle live streaming via a dedicated `Streamer` class.
- Provide a thin `DataFacade` that orchestrates these pieces and integrates with
  InfluxDB and the GUI.

These changes will reduce coupling and keep each piece focused on a single job.
