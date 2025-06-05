# Data Flow

The TradeSuite data pipeline was completely overhauled as part of the
`data_source_refactor` effort. The key idea is that widgets subscribe to generic
`StreamKey` values (`exchange`, `symbol`, `timeframe`) instead of owning their
own data streams. `TaskManager` maintains reference counts and runs all async
tasks in a dedicated event loop, allowing multiple widgets to share a single
WebSocket connection.

For in-depth rationale and migration details see
[`design_documents/implemented_designs/data_source_refactor.md`](../design_documents/implemented_designs/data_source_refactor.md).
