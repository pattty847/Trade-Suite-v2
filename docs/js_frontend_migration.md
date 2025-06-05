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

