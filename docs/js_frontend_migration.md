# JS Front-End Migration Plan

This document summarizes how to migrate the current DearPyGui desktop GUI to a web based UI using TradingView **Lightweight‑Charts** and a dockable layout system. The analysis is based on the existing `trade_suite/gui` widgets and `trade_suite/data/data_source.py` API.

## Component–Data Interaction Matrix

| Widget               | DataSource method(s)                   | Update cadence | Complexity |
|----------------------|----------------------------------------|----------------|------------|
| `ChartWidget`        | `fetch_candles()`, `watch_trades()` via `TaskManager` | streaming | medium |
| `OrderbookWidget`    | `watch_orderbook()`                    | streaming | medium |
| `PriceLevelWidget`   | `watch_orderbook()`                    | streaming | medium |
| `TradingWidget`      | `watch_trades()` (for price updates) and later order execution APIs | streaming | high |
| `SECFilingViewer`    | Uses `SECDataFetcher` (HTTP)           | on‑demand | low |

## React vs Vue

| Option | Pros | Cons |
|--------|------|------|
| **React** | - Mature ecosystem and large community.<br>- Rich TypeScript support with hooks.<br>- Existing wrappers for **lightweight-charts**.<br>- Docking libraries such as `golden-layout` have official React bindings. | - Slightly steeper learning curve for reactive state management.<br>- Boilerplate can grow without careful structure. |
| **Vue** | - Simpler template syntax.<br>- `Composition API` provides hooks-like patterns.<br>- Community packages for golden-layout exist. | - Smaller ecosystem for trading widgets.<br>- Fewer TypeScript-first packages compared to React. |

**Recommended:** React + TypeScript for the front-end. It aligns well with available docking libs and chart packages.

## Dockable Layout Library

`golden-layout` provides a proven, flexible docking UI commonly used in trading dashboards. It has an actively maintained React wrapper and supports saving/restoring layouts. Other grid libraries are either grid oriented (`react-grid-layout`) or less actively maintained. Hence **golden-layout** is the preferred choice.

## API Specification

The front-end will communicate with a thin FastAPI server that wraps the existing `Data` class.

### REST Endpoints

- `GET /candles` – query params: `exchange`, `symbol`, `timeframe`, `limit`
  - Returns: `[{"timestamp": 1680000000, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}, ...]`
- `GET /sec/filings` – query params: `ticker`, `form_type`
  - Returns a list of filing objects.

### WebSocket Streams

- `/stream/trades?exchange=coinbase&symbol=BTC/USD`
  - Emits `{"timestamp": ..., "price": ..., "size": ...}`
- `/stream/orderbook?exchange=coinbase&symbol=BTC/USD`
  - Emits order book snapshots `{"bids": [[price, qty], ...], "asks": ...}`

These endpoints map directly to existing async methods such as `watch_trades()` and `watch_orderbook()`.

## Incremental Migration Checklist

```markdown
- [ ] create `server/main.py` with FastAPI boilerplate
- [ ] expose `/candles` endpoint using `Data.fetch_candles`
- [ ] expose trade and order book WebSocket routes
- [ ] scaffold React + Vite project with TypeScript
- [ ] integrate `lightweight-charts` and `golden-layout`
- [ ] implement MainChart component fetching history and subscribing to WS
- [ ] port Orderbook and PriceLevel widgets
- [ ] add Trading panel with basic order entry UI
- [ ] migrate SEC Filing viewer (simple tables)
- [ ] phase out DearPyGui once widgets run in browser
```

## DataSource API Summary

The `trade_suite.data.data_source.Data` class orchestrates fetching historical data and starting live streams. Key methods are:

| Method | Description | Async? | Notes |
|--------|-------------|-------|-------|
| `fetch_candles(exchanges, symbols, since, timeframes)` | Retrieve batches of OHLCV data from cache or the exchange. Returns `Dict[str, Dict[str, DataFrame]]`. | **async** | Writes to InfluxDB when `write_to_db=True`. |
| `watch_trades(exchange, symbol, stop_event, ...)` | Stream new trades over websockets. Emits `Signals.NEW_TRADE`. | **async** | Runs until `stop_event` is set. |
| `watch_orderbook(exchange, symbol, stop_event, cadence_ms=500)` | Stream order book snapshots. Emits `Signals.ORDER_BOOK_UPDATE`. | **async** | Throttled by `cadence_ms`. |
| `watch_ticker(exchange, symbol, stop_event)` | Stream ticker data for last price / spread. | **async** | Optional, not used by current widgets. |

`Data` delegates the heavy lifting to `Streamer` and `CandleFetcher` but exposes a clean interface for the GUI and (future) FastAPI layer.

## Widget Interaction Details

Beyond the high-level matrix, each widget relies on `TaskManager` to manage subscriptions:

- **ChartWidget** – Subscribes to a candle factory plus the trade stream to incrementally update its series. Uses signals `NEW_CANDLES` and `UPDATED_CANDLES`.
- **OrderbookWidget** – Subscribes to an order book stream. Processes raw data with `OrderBookProcessor` and updates a plot.
- **PriceLevelWidget** – Shares the same order book stream but aggregates levels to display a DOM-style table.
- **TradingWidget** – Consumes trade ticks for live pricing and will issue future REST calls for order placement.
- **SECFilingViewer** – Does not use `Data`; it talks directly to `SECDataFetcher` via `TaskManager` tasks.

The `TaskManager` maintains reference counts per stream or candle factory. When the first widget subscribes, the relevant `watch_*` coroutine is started. When all widgets unsubscribe, the `stop_event` is set and the task cancelled.

## Integration Strategy

1. **Expose Data via FastAPI** – Wrap the methods above into REST and WebSocket endpoints. Maintain the `TaskManager` so server-side streaming mirrors the current GUI.
2. **Front-End Components** – Recreate each widget using React components. The existing widget code serves as a blueprint for required props and behaviors.
3. **Shared Layout** – Persist layout state on the client (Golden Layout) and optionally in the backend for user profiles.
4. **Incremental Porting** – Start with the Chart and Orderbook since they cover the main data flows. Once stable, migrate Trading and SEC filings features.

=======
