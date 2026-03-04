# AGENTS.md

## Purpose
This file is the default operating guide for AI agents and new contributors working in this repository.
It prioritizes practical execution: understand the current architecture, avoid breaking invariants, and validate changes quickly.

## Current Repo Structure (Source of Truth)
- `sentinel/`: Main Qt desktop application (PySide6 + PyQtGraph + qasync).
- `sentinel_ops/`: Legacy collector/alert system (renamed from old `sentinel`). Keep runnable; treat as separate runtime.
- `trade_suite/core/`: Reused backend services (streams, subscriptions, task management, facade, signals).
- `trade_suite/analysis/`: Reusable analytics/processors (orderbook processing, etc.).
- `scanner/`: Analysis/scanner workflows and tooling.
- `config/`: Layout + widget defaults and user-persisted Qt state.

## Runtime Entry Points
- Sentinel Qt app: `python -m sentinel`
- Sentinel ops collector: `python -m sentinel_ops.run`
- Sentinel ops alert bot: `python -m sentinel_ops.alert_bot.main`

Use `uv` for environment/dependency workflows.
- Sync deps: `uv sync`
- Run with project env: `uv run python -m sentinel`

## Packaging / Dependency Rules
- Dependencies are managed in `pyproject.toml` (not `requirements.txt`).
- Do not reintroduce `requirements.txt`.
- Keep runtime dependencies minimal and explicit.

## Sentinel Architecture (Qt)

### UI Shell
- Main window: `sentinel/app/main_window.py`
- Layout persistence: `sentinel/app/layout_manager.py`
- Widget creation/registry: `sentinel/app/widget_registry.py`
- Runtime lifecycle + backend bridge: `sentinel/app/runtime.py`, `sentinel/app/signal_bridge.py`
- Widgets: `sentinel/widgets/`

### Layout Contracts (must keep)
- Every dock must have stable identity:
  - `dock.setObjectName(f"dock:{instance_id}")`
- Layout JSON schema must include:
  - `layout_version`
  - `qt_version`
  - `app_version`
  - `state_b64`
  - `geometry_b64`
- On layout version mismatch:
  - log warning
  - skip restore
  - load default layout

### Async/Runtime Contracts (must keep)
- `TaskManager` supports:
  - `mode="thread" | "external"`
- Sentinel Qt path uses external event loop mode via qasync.
- `TaskManager.aclose()` exists and is used on shutdown.
- Shutdown sequence must remain deterministic and non-blocking:
  1. stop subscriptions
  2. cancel tasks
  3. await exchange/client close
  4. verify no unexpected pending tasks

### High-Frequency Rendering Contracts (must keep)
For chart/orderbook/DOM:
- Do not render by per-tick Qt signal spam.
- Use model updates + dirty flag + capped `QTimer` pull render loop.
- Reserve signals for lifecycle/error/control events.

### Chart Contract (current direction)
- X-axis is index-based for candle rendering stability.
- Maintain timestamp mapping for labels separately.
- Avoid candle-width logic based on float timestamp deltas.

## Backend Reuse Policy
- Prefer importing from `trade_suite/core` and `trade_suite/analysis`.
- Do not duplicate/move backend modules into `sentinel/` unless explicitly requested.
- If backend refactors are required, preserve behavior first; optimize later.

## Code Standards
- Python 3.10+ compatible.
- Type hints for new/changed functions.
- Small focused modules and functions.
- Avoid broad refactors during feature work.
- Keep comments concise and only where logic is non-obvious.
- Preserve public method names/contracts unless migration plan explicitly changes them.

## UI/UX Standards (Sentinel)
- Dark, high-contrast, thin-line, boxy visual language.
- Avoid template-like third-party themes as default.
- Prefer in-repo QSS/style tokens and incremental tuning.
- Default layout target:
  - chart primary area
  - right rail narrow DOM (top)
  - right rail depth/orderbook (bottom)

## Safety Rules for Agents
- Do not delete or rewrite unrelated files.
- Do not mix mechanical renames with architectural rewrites in one step.
- Do not introduce backward-compat runtime shims for DearPyGUI.
- Keep DPG code reference-only until explicitly removed from non-runtime areas.

## Validation Checklist (run before finishing)
1. Import checks:
   - `python -m sentinel` imports cleanly (or full launch if available).
   - `python -m sentinel_ops.run` imports cleanly when touched.
2. No unintended DPG usage in Sentinel runtime path:
   - `rg "dearpygui|import dpg|dpg\." sentinel trade_suite/core`
3. No circular-import symptoms introduced.
4. Layout persistence still works (save, restart, restore/fallback).
5. Shutdown path does not block.

## Change Scope Discipline
When implementing a requested phase/task:
- Execute only the requested scope.
- Avoid opportunistic architecture changes.
- If you see adjacent issues, note them separately instead of bundling.

## Preferred Workflow for Agents
1. Inspect affected modules and call graph.
2. Make minimal coherent patch set.
3. Run targeted validation commands.
4. Report:
   - what changed
   - why
   - what was validated
   - known follow-ups/risks
