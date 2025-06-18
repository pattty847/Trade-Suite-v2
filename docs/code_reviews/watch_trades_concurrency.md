# watch_trades Concurrency Review

This note outlines how `Data.watch_trades` delegates to `Streamer.watch_trades` and how that
function is reused by both the TradeSuite GUI and the Sentinel service.

## Overview

- `Data.watch_trades` is a thin wrapper that simply forwards all arguments
to `Streamer.watch_trades`.
- `Streamer.watch_trades` supports three output mechanisms:
  - GUI updates via `SignalEmitter` when no `sink` or `queue` is provided.
  - Direct async callbacks via a supplied `sink` function.
  - Delivery through an `asyncio.Queue`.
- Sentinel uses `sink` functions to pipe trades into its queues while the GUI
relies on `SignalEmitter` emissions.

## Potential Interactions

If both systems share the same `Data` instance (as with
`Data.initialize_sentinel()`), they call `watch_trades` independently.
Each call maintains its own `asyncio.Event` and loop but operates on the
same underlying CCXT exchange object.

- Multiple tasks can therefore invoke `exchange.watch_trades(symbol)` at the
  same time. CCXT-PRO generally supports this but it results in separate
  consumer loops on the same WebSocket stream.
- The GUI and Sentinel do not share queues or sinks, so their emitted data
  remains isolated.
- CPU and network load may increase when two watchers fetch the same market,
  but no direct data corruption occurs within `Streamer.watch_trades`.

## Recommendations

- When running Sentinel alongside the GUI, prefer dedicated exchanges or
  symbols where possible to avoid duplicate connections.
- If both must observe the same market, be aware of the extra WebSocket load.
  Consider adding a shared fan‑out layer in the future so that a single watcher
  feeds multiple consumers.

Overall the current implementation allows concurrent use, but resource
usage grows with each separate `watch_trades` task on the same market.

## Multi-Symbol Streaming and Hot Reload

`Streamer.watch_trades_list` already calls `exchange.watchTradesForSymbols(symbols)`
to subscribe to multiple markets in one WebSocket connection.  However the
current TaskManager spins up individual `watch_trades` tasks per symbol.  This
means adding or removing a symbol requires starting or stopping entire tasks and
does not reuse a single feed.

To support hot reloading we could maintain a symbol set per exchange and restart
`watchTradesForSymbols` when that set changes.  The TaskManager would update the
set whenever a widget subscribes or unsubscribes and signal the running stream to
restart with the new list.  Alternatively a small facade around the CCXT exchange
could manage the symbol list internally, exposing `add_symbol` and
`remove_symbol` helpers that trigger `exchange.watchTradesForSymbols` with the
updated list.  Either approach would allow dynamic subscription changes without
opening a new socket for every symbol.

## StreamManager Refactor

The codebase now includes a `StreamManager` class extracted from `TaskManager`.
It keeps per-exchange symbol sets and runs continuous
`watchTradesForSymbols` and `watchOrderBookForSymbols` loops. Widgets call
`subscribe_to_asset` or `unsubscribe_from_asset` to update these sets.  Because
the loops read the latest symbol list each iteration, new markets can be added
or removed at runtime without restarting the WebSocket connection.
