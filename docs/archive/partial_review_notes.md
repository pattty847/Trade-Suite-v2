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

### Progress After Initial Refactor

The initial steps moved heavy I/O onto `asyncio.to_thread` and switched the
`watch_*` methods to `asyncio.get_running_loop()`. The refactor is now complete:
`CacheStore`, `CandleFetcher`, and `Streamer` live in their own modules and
`Data` merely delegates to them. This reduces coupling and clarifies each
component's role.

