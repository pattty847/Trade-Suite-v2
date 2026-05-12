# AGENTS.md

## Purpose

This is the default operating guide for agents and new contributors working in this repository.
It assumes no prior context.

The repo is centered on one active product: `sentinel`.

## Source Of Truth

- `sentinel/` is the only active application/runtime.
- Dependencies are managed in `pyproject.toml`.
- Use `uv`, not `requirements.txt`.

## Entrypoints

- App: `uv run python -m sentinel`
- Tests: `uv run python -m pytest`


## Repository Structure

- `sentinel/app/`
  - Qt shell
  - main window
  - layout persistence
  - widget registry
  - runtime/signal bridge
- `sentinel/widgets/`
  - chart pane and chart dock widgets
  - chart-local toolbar
  - chart+orderflow composite
  - DOM and orderbook widgets
- `sentinel/core/`
  - backend runtime
  - streaming
  - task management
  - signals
  - exchange/data access
  - cache/fetch infrastructure
- `sentinel/analysis/`
  - reusable processors and analytics
  - orderbook aggregation / ladder helpers

## Architectural Rules

### 1. Sentinel-first only

- Do not reintroduce `trade_suite`.
- New code that matters to the app belongs under `sentinel`.

### 2. Layout persistence contract

These rules must remain stable:

- every dock must have a stable object name:
  - `dock.setObjectName(f"dock:{instance_id}")`
- persisted layout metadata must include:
  - `layout_version`
  - `qt_version`
  - `app_version`
  - `state_b64`
  - `geometry_b64`
- on version mismatch:
  - log a warning
  - skip restore
  - fall back to defaults

### 3. Async/runtime contract

These rules must remain stable:

- `TaskManager` supports `mode="thread" | "external"`
- Sentinel uses the external Qt event loop path via `qasync`
- `TaskManager.aclose()` exists and is used during shutdown
- shutdown must be deterministic:
  1. stop subscriptions
  2. cancel tasks
  3. await exchange/client close
  4. verify no unexpected pending tasks remain

### 4. High-frequency UI contract

For chart, DOM, orderbook, and chart+orderflow:

- do not render directly from per-tick signal spam
- update an internal model first
- mark dirty
- render on a capped `QTimer` pull loop
- reserve signals for lifecycle, control, and error events

### 5. Chart contract

Current chart behavior:

- candlesticks use timestamp-based plotting
- candle widths are derived from real timeframe spacing
- auto-fit should not keep firing on every update
- wicks and bodies render as separate primitives
- the chart price line and right-edge price pill are active runtime overlays
- trade bubbles are optional and should not leave stale overlay artifacts

If chart behavior regresses, check these first:

- timestamp axis setup
- candle width calculation
- repeated autorange calls
- plot linking between price and volume panes
- overlay invalidation when bubbles or price line updates occur

### 6. Chart-local toolbar contract

The global top bar is workspace-level only.

Each `ChartDockWidget` and `ChartOrderflowDockWidget` owns its own:

- `Symbol` — editable combo (Return key confirms custom symbol)
- `Timeframe`
- `Mode`
- `Bubbles`
- `EMA` — toggles EMA-20 overlay on price pane; `ChartPane.set_ema_enabled(bool)`
- `CVD` — toggles the CVD subplot below the price pane (live-only, no historical bootstrap)
- `VPVR` — toggles volume-at-price overlay
- `OB` — toggles the orderbook ladder (`ChartOrderflowDockWidget` only)

This state must persist per widget.
Do not reintroduce global market-control broadcasting.

OB toggle contract:
- When OB is ON: `ChartPane.show_price_axis=False`, `_right_container` visible, OB subscription active
- When OB is OFF: `ChartPane.set_price_axis_visible(True)`, `_right_container` hidden
- Orderbook subscription is started on first enable; it stays active if OB is toggled off mid-session (reconnect on next toggle-on)
- `export_definition()` saves `show_ob`, `show_cvd`, `show_ema`, and `show_vpvr` per widget instance

EMA contract:
- `ChartPane.set_ema_enabled(bool)` / `ema_enabled() -> bool` toggle the EMA-20 line
- When disabled, the `ema_item` is removed from the plot immediately
- On render, EMA uses `setData()` in-place rather than remove+recreate

CVD contract:
- `CandleCVDProcessor` (in `sentinel/analysis/cvd_processor.py`) accumulates live trades into per-candle buy/sell buckets
- CVD starts from zero when the widget opens — no historical bootstrap
- `ChartPane.set_cvd_enabled(bool)` shows/hides the CVD `QSplitter` pane below the price chart
- `ChartPane.cvd_stats()` returns `{session_cvd, bar_delta, total_buy, total_sell}` for the stats strip

Delta Stats contract (`ChartOrderflowDockWidget` only):
- `DeltaStatsPanel` widget shows below the OB ladder when BOTH OB and CVD are active
- Refreshed every 500 ms via `_stats_timer` → `_refresh_delta_stats()` → `chart_pane.cvd_stats()`
- Shows: bar delta, session CVD, buy/sell volume, buy/sell ratio gradient bar
- Hidden automatically when OB or CVD is toggled off; timer stopped

VPVR contract:
- `VpvrItem` (in `sentinel/widgets/chart_pane.py`) draws horizontal volume-profile bars as a `pg.GraphicsObject` in data-space
- VPVR updates on every Y range change (`sigYRangeChanged`) and X range change (`sigXRangeChanged`)
- Volume is distributed across `_VPVR_N_BINS` = 60 price buckets using linear candle-range interpolation
- Bars are anchored to the right edge of the visible X range; max bar width = 22% of visible X span
- Point of Control (highest-volume bin) is highlighted in amber
- `ChartPane.set_vpvr_enabled(bool)` shows/hides the overlay; persists via `show_vpvr` in `export_definition`

### 7. Chart+Orderflow contract

The `Chart + Orderflow` composite is an active product surface.

Current rules:

- the chart owns the visible price scale
- the ladder mirrors the chart’s visible Y range
- ladder columns are:
  - `Price`
  - `Size`
  - `Total`
- auto tick mode uses a nice-ticks preset ladder
- `price_precision` is the instrument minimum increment
- `tick_size` is current ladder aggregation state
- do not treat saved `tick_size` as `price_precision`

If chart+orderflow behavior regresses, check these first:

- widget restore path in `widget_registry.py`
- `calculate_tick_presets(...)` in `sentinel/analysis/orderbook_processor.py`
- `choose_auto_tick_size(...)` in `sentinel/widgets/chart_orderflow_widget.py`
- ladder canvas draw-area sizing after header/control changes

## Current Debugging Notes

Recent chart+orderflow work introduced several important constraints:

- auto tick should choose from a dense nice-ticks ladder:
  - `0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, ...`
- row-height targeting currently uses a pixel band and sticky switching
- startup/restore bugs can appear if tick is resolved before the ladder canvas is fully settled
- if rows appear to lock at coarse ticks unexpectedly, inspect whether restore/config confused `tick_size` and `price_precision`

Known fragile area:

- tiny row gaps/seams during smooth pan/zoom can come from row-boundary rasterization
- if this returns, inspect:
  - float vs integer position mapping
  - row boundary tiling math in `LadderCanvas`

## Coding Standards

- Python 3.10+
- type hints on new or changed functions
- keep modules focused
- prefer small coherent patches over broad rewrites
- keep comments short and useful
- remove dead architecture when the active path is clear

## UI Standards

Sentinel UI direction:

- dark
- high-contrast
- thin-line
- boxy
- compact
- trading-focused

Avoid:

- generic third-party theme defaults
- glossy/template-like styling
- UI changes that break docking, persistence, or runtime clarity

Default workspace intent:

- chart is primary
- chart+orderflow is a first-class workflow
- right rail can hold DOM and orderbook/depth
- controls should be local where ownership matters

## Validation Checklist

Run appropriate checks before finishing:

### 1. Import/runtime

- `uv run python -c "import sentinel, sentinel.app.runtime, sentinel.core.facade"`
- full `uv run python -m sentinel` launch when practical

### 2. Tests

- `uv run python -m pytest`
- if full suite is too broad, run the smallest relevant subset

### 3. Legacy leak check

- `rg "dearpygui|import dpg|dpg\\.|trade_suite" .`

### 4. Layout/runtime sanity

- layout still restores or falls back cleanly
- shutdown path does not block
- chart-local widget state restores correctly

## Change Discipline

- execute the requested scope first
- do not bundle unrelated architecture work without reason
- if you find adjacent problems, call them out separately
- if unexpected external edits appear while you are working, stop and raise it immediately

## Preferred Workflow

1. inspect the affected modules and call graph
2. patch the smallest coherent surface
3. run targeted validation
4. report:
   - what changed
   - why
   - what was validated
   - what remains risky or unfinished
