# AGENTS.md

## Purpose

This file is the default operating guide for agents and new contributors working in this repository.
It is written for someone with no prior context.

The repository is now centered on one active application: `sentinel`.

## Source Of Truth

- `sentinel/` is the only active application/runtime in this repo.
- `sentinel_ops/` is legacy and not part of the active product direction.
- Dependencies are managed in `pyproject.toml`.
- Use `uv`, not `requirements.txt`.

## Entrypoints

- App: `uv run python -m sentinel`
- Tests: `uv run python -m pytest`

If you touch `sentinel_ops`, treat it as legacy maintenance only.

## Repository Structure

- `sentinel/app/`
  - Qt shell and runtime orchestration
  - main window
  - layout persistence
  - widget registry
  - signal/runtime bridge
- `sentinel/widgets/`
  - user-facing dock widgets
  - chart
  - DOM
  - orderbook
- `sentinel/core/`
  - backend services and shared runtime
  - data access
  - streaming
  - task management
  - signals
  - cache/fetch infrastructure
- `sentinel/analysis/`
  - reusable analytics/processors

## Architectural Rules

### 1. Sentinel-first only

- Do not reintroduce `trade_suite`.
- Do not build new features in `sentinel_ops`.
- New runtime code belongs under `sentinel`.

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

For chart, DOM, and orderbook:

- do not drive rendering through per-tick Qt signal spam
- update an internal model first
- mark dirty
- render on a capped `QTimer` pull loop
- reserve signals for lifecycle, control, and error events

### 5. Chart contract

Current chart behavior:

- candlesticks use timestamp-based plotting
- candle widths are derived from real timeframe spacing
- auto-fit should not keep firing on every update
- wicks and bodies must render as separate primitives

If chart behavior regresses, check these first:

- timestamp axis setup
- candle width calculation
- repeated autorange calls
- plot linking between price and volume panes

## Coding Standards

- Python 3.10+
- type hints on new/changed functions
- keep modules focused
- prefer small, coherent patches over broad rewrites
- keep comments short and useful
- do not preserve dead architecture out of caution; remove it when the active path is clear

## UI Standards

Sentinel UI direction:

- dark
- high-contrast
- thin-line
- boxy
- minimal visual noise

Avoid:

- generic third-party themes as the default look
- overly glossy or template-like styling
- UI changes that break docking/layout behavior

Default workspace intent:

- chart is primary
- right rail holds DOM and orderbook/depth
- controls are compact and trading-focused

## Validation Checklist

Run appropriate checks before finishing:

1. Import/runtime
- `uv run python -c "import sentinel, sentinel.app.runtime, sentinel.core.facade"`
- full `uv run python -m sentinel` launch when practical

2. Tests
- `uv run python -m pytest`
- if full suite is too broad, run the smallest relevant subset

3. Legacy leak check
- `rg "dearpygui|import dpg|dpg\\.|trade_suite" /Users/copeharder/Programming/Trade-Suite-v2`

4. Layout/runtime sanity
- layout still restores or falls back cleanly
- shutdown path does not block

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
