# Data Flow

The TradeSuite data pipeline was completely overhauled as part of the
`data_source_refactor` effort. Widgets subscribe to generic `StreamKey` values
(`exchange`, `symbol`, `timeframe`) and the `TaskManager` maintains reference
counts, running all async tasks in a dedicated event loop. A `DataFacade`
(in `trade_suite/data/data_source.py`) now orchestrates `CacheStore`,
`CandleFetcher`, and `Streamer` components, allowing multiple widgets to share a
single WebSocket connection and centralizing cache and exchange logic.

For in-depth rationale and migration details see
[`design_documents/implemented_designs/data_source_refactor.md`](../design_documents/implemented_designs/data_source_refactor.md).
