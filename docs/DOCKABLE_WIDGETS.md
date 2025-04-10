# Dockable Widgets Refactoring

This document outlines the substantial architectural changes made to implement a fully dockable widget system in the Trading Suite v2.

## Overview

The application has been refactored from a fixed layout with component-based tabs to a flexible, dockable widget system. This allows users to:

- Dock any widget to any other widget or to the viewport
- Customize their workspace layout
- Save and restore layouts between sessions
- Reset to default layouts when needed

## Key Changes

### 1. Component to Widget Migration

The application's UI components have been refactored from:
- `/components/chart.py`
- `/components/orderbook.py` 
- `/components/trading.py`

Into a widget-based system:
- `/widgets/base_widget.py` - Base class for all widgets
- `/widgets/chart_widget.py` - Chart display
- `/widgets/orderbook_widget.py` - Order book display 
- `/widgets/trading_widget.py` - Trading interface

Each widget is now a standalone, dockable element rather than a tab within a fixed container.

### 2. Architectural Changes

- `program.py` → `dashboard_program.py`: Refactored to support the widget-based approach
- Added `viewport.py`: New implementation for managing the application viewport
- Created `dashboard_manager.py`: Manages widget creation, layout saving/loading
- Entry point change: `main.py` now calls `test_widgets_launch.py`

### 3. Docking Implementation

The docking system uses DearPyGUI's built-in docking capabilities:

- Configured with `dpg.configure_app(docking=True, docking_space=True, init_file=user_layout.ini)`
- Layout persistence using `.ini` files:
  - `factory_layout.ini`: Default layout shipped with the application
  - `user_layout.ini`: User's custom layout saved between sessions
- Removed primary window concept - all windows are equally dockable
- Added viewport-level menu bar instead of window-level menus

### 4. Signal System Enhancements

Added new signals for widget creation:
- `NEW_CHART_REQUESTED`
- `NEW_ORDERBOOK_REQUESTED`
- `NEW_TRADING_PANEL_REQUESTED`

These signals decouple the menu system from the widget creation logic.

## Usage

### Basic Docking Operations

1. **Dock widgets**: Drag a widget's title bar onto another widget or the viewport
2. **Detach widgets**: Drag a widget's title bar away from its current position
3. **Rearrange widgets**: Drag widgets to create split views, tabs, or side-by-side layouts

### Layout Management

- **Save layout**: File → Save Layout
- **Reset layout**: File → Reset Layout or View → Reset Layout
- **Layout tools**: View → Layout Tools

## Cleanup and Technical Debt

The following items should be addressed in future updates:

1. **Legacy component removal**: The `/components` directory can eventually be removed once the widget system is fully tested
2. **Rename entry point**: Rename `test_widgets_launch.py` to something more appropriate
3. **Code duplication**: Some functionality is duplicated between the old and new systems
4. **Documentation**: Update in-code documentation to reflect architectural changes

## Branch Information

This refactoring is currently in the `features/dockable-widgets` branch and should be merged to main after testing is complete. 