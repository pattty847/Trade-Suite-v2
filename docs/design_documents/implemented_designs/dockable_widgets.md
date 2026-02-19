# Dockable Widgets Refactoring

This document outlines the substantial architectural changes made to implement a fully dockable widget system in the Trading Suite v2.

## Overview

The application has been refactored from a fixed layout with component-based tabs to a flexible, dockable widget system. This allows users to:

- Dock any widget to any other widget or to the viewport
- Customize their workspace layout
- Save and restore layouts between sessions
- Reset to default layouts when needed

## Key Changes

### 1. Component to Widget Migration (**Completed**)

The legacy `/components` directory has been **removed**. Its functionality has been migrated into the new widget-based system under `/widgets`:

- `/components/chart.py` -> `/widgets/chart_widget.py`
- `/components/orderbook.py` -> `/widgets/orderbook_widget.py`
- `/components/trading.py` -> `/widgets/trading_widget.py`
- `/components/test_ob.py` -> `/widgets/price_level_widget.py` (**New** - Displays aggregated price levels/DOM)
- `/components/indicators.py` -> Logic integrated into `/widgets/chart_widget.py`
- `/components/tpo.py` -> Removed (can be reimplemented as a widget if needed)
- `/components/tab.py` -> Removed (superseded by docking system)
- `/components/plot_series.py` -> Removed (superseded)

Each functional UI piece is now a standalone, dockable widget inheriting from `/widgets/base_widget.py`.

### 2. Architectural Changes

- `Viewport` (`viewport.py`): Manages the main application window, viewport menu bar, docking space, and the primary DPG render loop.
- `DashboardManager` (`widgets/dashboard_manager.py`): Handles widget creation/tracking, layout saving/loading (`.ini` files), and provides layout management tools.
- `DashboardProgram` (`dashboard_program.py`): Acts as a controller/coordinator. It handles signals for creating new widgets (e.g., `NEW_CHART_REQUESTED`), displays the necessary dialogs (exchange/symbol selection), and instructs the `DashboardManager` to add the new widget. It also orchestrates starting initial data streams and propagating symbol changes between related widgets.
- `BaseWidget` (`widgets/base_widget.py`): Provides common functionality (stable IDs, creation/showing/hiding, menu/content/status bar structure) for all dockable widgets.
- Entry point: `main.py` calls `test_widgets_launch.py` which sets up core services (`Data`, `TaskManager`, `ConfigManager`, `Emitter`) and runs the `Viewport`.

### 3. Docking Implementation

The docking system uses DearPyGUI's built-in docking capabilities:

- Configured via `Viewport` using `dpg.configure_app(docking=True, docking_space=True, init_file=user_layout.ini)`.
- Layout persistence using `.ini` files:
    - `config/factory_layout.ini`: Default layout shipped with the application. Can be updated by saving a desired layout over this file.
    - `config/user_layout.ini`: User's custom layout saved automatically between sessions.
- Viewport-level menu bar (`File`, `View`, `Exchange`) provides global actions.
- Individual widgets can have their own menus (e.g., Chart widget has `Timeframes`, `View`, `Indicators`).

### 4. Signal System Enhancements

New signals added to support dynamic widget creation:
- `NEW_CHART_REQUESTED`
- `NEW_ORDERBOOK_REQUESTED`
- `NEW_TRADING_PANEL_REQUESTED`
- `NEW_PRICE_LEVEL_REQUESTED` (**New**)

These signals are emitted by the `Viewport` menu and handled by `DashboardProgram` to show the relevant creation dialog.

### 5. Data Stream Management

- `TaskManager` now includes `is_stream_running(stream_id)` method.
- `DashboardProgram` uses this check when creating Orderbook or Price Level widgets to avoid starting duplicate WebSocket streams for the same exchange/symbol pair.

## Usage

### Basic Docking Operations

1. **Dock widgets**: Drag a widget's title bar onto another widget or the viewport edge.
2. **Detach widgets**: Drag a widget's title bar away from its current docked position.
3. **Rearrange widgets**: Drag widgets to create split views, tabs, or floating windows.

### Layout Management

- **Save current layout**: `File` -> `Save Layout` (saves to `user_layout.ini`).
- **Reset layout**: `File` -> `Reset Layout` (deletes `user_layout.ini`, causing `factory_layout.ini` to load on next start).
- **Layout tools**: `View` -> `Layout Tools` (DPG tools for debugging layout).
- **Update Factory Default**: To make the *current* layout the new default, manually copy/rename `config/user_layout.ini` to `config/factory_layout.ini`.

### Adding Widgets

Use the `File` menu (`New Chart`, `New Orderbook`, etc.) to add new widgets to the workspace. Select the desired exchange and symbol in the popup dialog.

## Remaining Tasks / Future Improvements

See `docs/CLEANUP_PLAN.md` for detailed tasks, including:

- Refining the default factory layout.
- Optimizing `PriceLevelWidget` performance.
- Enhancing data stream management robustness.
- Renaming the entry point script.
- Further refining `DashboardProgram`'s role.

## Branch Information

This refactoring is in the `feature/dockable-widgets` branch. 