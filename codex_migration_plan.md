Codex Prompt – "Migrate TradeSuite GUI to JS + Lightweight-Charts"

"""
🔍 **Mission**
You are reviewing the Python-based TradeSuite codebase—especially `trade_suite/gui/` and `data/`.
Your job: generate a *step-by-step refactor plan* to replace the current DearPyGui desktop UI with a modern JavaScript front-end that uses **TradingView Lightweight-Charts** plus a dockable widget layout (React or Vue).

---

## 1. Explore & Document
1. Scan `trade_suite/gui/`:
   - Identify each widget class (chart, order-book, stats panes, log panels, etc.).
   - Note their props, update signals, and dependencies on `DataSource`.
2. Inspect `trade_suite/data/data_source.py`:
   - Document its API surface (methods, expected returns, push vs pull).
   - Clarify what is synchronous vs async, and which calls require live exchange websockets.
3. Produce a **component–data interaction matrix**:

WidgetDataSource method(s)Update cadenceComplexity
MainChartWidget.get_candles(), .subscribe_trades()streammedium
…

## 2. JS Front-End Feasibility Study
1. Evaluate **React vs Vue**:
- Ecosystem maturity for trading-widgets.
- Support for TypeScript & hooks/composables.
2. Evaluate **dockable layout libraries**:
- `golden-layout` (React wrapper)
- `react-grid-layout`
- `@zcorky/vuedraggable-golden-layout` (Vue)
3. Map existing widgets ➜ JS equivalents:
- Chart → **Lightweight-Charts** `ChartApi`
- Table-like widgets → `react-virtualized` or `ag-grid`
- Logs / consoles → simple `<pre>` component with auto-scroll.

## 3. Data-Pipeline Refactor Plan
1. Define a *thin* HTTP+WebSocket API the JS front-end will consume:  
GET  /candles?symbol=BTCUSD&tf=1m&limit=500
WS   /stream/trades?symbol=BTCUSD
WS   /alerts?user_id=…

2. Specify **Data Schema** (JSON) for:
- Candles (timestamp, open, high, low, close, volume)
- Trade ticks
- Alert events
3. Show how current `DataSource` can be wrapped/exposed in FastAPI (or Sanic) without rewriting its internals.

## 4. Incremental Migration Steps
1. Stand-up `server/main.py` (FastAPI) exposing the endpoints from §3.
2. Build a **React + Vite** starter with:
- `lightweight-charts`
- Chosen dockable layout lib
3. Port one widget (MainChart) end-to-end:
- Fetch historical candles via REST
- Subscribe to live candles via WS
- Render with Lightweight-Charts
4. Port remaining widgets iteratively.
5. Cut over DearPyGui → JS once feature-parity hits 80 %.

## 5. Deliverables (to output back to me)
- **Component–Data matrix** (see §1).
- **Pros/Cons table**: React vs Vue for this project.
- **Chosen layout library** rationale.
- **API spec** (endpoints + JSON samples).
- **Migration checklist** as GitHub Issues markdown:

•create server/main.py with FastAPI boilerplate
•implement /candles endpoint …

**Notes & Constraints**
- Keep server-side Python; only the GUI moves.
- Re-use existing async streams; do **not** re-implement exchange adapters in JS.
- Prioritize *smallest viable* JS bundle—no heavyweight chart libs beyond Lightweight-Charts.
"""


⸻

How to use this prompt
1.Create a new file codex_migration_plan.md at repo root.
2.Paste the entire block above.
3.Select it in Cursor or your Codex IDE → “Ask Codex”.
4.Codex will read the codebase, generate the matrices, API spec, and checklist.
5.Copy the output into a new markdown doc (docs/js_frontend_migration.md) and start executing the checklist.

