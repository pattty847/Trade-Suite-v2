# Cleanup Plan for Dockable Widgets Refactoring

This document outlines the steps needed to clean up and finalize the codebase after the dockable widgets refactoring before merging back to the main branch.

## Priority Tasks

### 1. Performance Optimization (`PriceLevelWidget`)

- [ ] Investigate and mitigate lag observed when adding/using `PriceLevelWidget`, especially with small tick sizes.
    - [ ] **Strategy 1 (Easy):** Increase `update_interval` in `PriceLevelWidget` (e.g., 0.1 or 0.2 seconds) to reduce UI update frequency.
    - [ ] **Strategy 2 (Medium):** Modify `_process_and_display_orderbook` to only call `dpg.set_value` / `dpg.configure_item` for cells whose *value or color* has actually changed since the last update.
    - [ ] **Strategy 3 (Harder):** Implement data source throttling in `data_source.py` for `ORDER_BOOK_UPDATE` signals.
- [ ] Profile application with multiple widgets (especially `PriceLevelWidget`) open to identify other potential bottlenecks.

### 2. Default Layout (`factory_layout.ini`)

- [ ] Review the current default layout defined in `config/factory_layout.ini`.
- [ ] Arrange widgets in a desired default configuration within the running application.
- [ ] Copy the resulting `config/user_layout.ini` to `config/factory_layout.ini` to set the new default.
- [ ] Test the reset layout functionality (`--reset-layout` flag or `File` -> `Reset Layout`) to ensure the new factory default loads correctly.

### 3. Entry Point Refactoring

- [ ] Rename `test_widgets_launch.py` to `app.py` or another appropriate name reflecting its role as the main application runner.
- [ ] Update `main.py` to properly import and call the main function from the renamed entry point file.
- [ ] Ensure command-line arguments (e.g., `--reset-layout`, `--level`) are handled correctly in the renamed entry point.

### 4. Final Testing & Bug Fixes

- [ ] Test all docking operations thoroughly (drag/drop, tabs, splits, floating).
- [ ] Verify layout persistence works correctly (save on close, load on start, reset).
- [ ] Check that the dynamic `Exchange` menu populates and functions correctly.
- [ ] Ensure all menu items (`File`, `View`, individual widget menus) trigger the appropriate actions without errors.
- [ ] Test adding/removing all types of widgets (`Chart`, `Orderbook`, `Trading`, `Price Level`).
- [ ] Verify real-time data updates correctly across all relevant widgets (candles, order books, price levels).
- [ ] Check indicator functionality (`EMA` on charts).

## Completed Tasks (During Refactoring Session)

- **Legacy Code Removal:**
    - [x] Migrated `chart.py`, `orderbook.py`, `trading.py` logic to respective `Widget` classes.
    - [x] Migrated `test_ob.py` logic to `PriceLevelWidget`.
    - [x] Migrated `indicators.py` logic into `ChartWidget`.
    - [x] **Removed** the entire `/trade_suite/gui/components/` directory.
- **Widget Integration:**
    - [x] Added `PriceLevelWidget` creation via `File` menu and dialog.
- **Stream Handling:**
    - [x] Added `TaskManager.is_stream_running` check.
    - [x] Prevented duplicate order book streams when adding Orderbook/PriceLevel widgets for the same market.
- **Documentation:**
    - [x] Updated `DOCKABLE_WIDGETS.md` with latest architecture and changes.

## Medium Priority Tasks (Post-Merge / Future)

### 5. Code Duplication and Refactoring

- [ ] Review `DashboardProgram` - can parts of its logic (dialogs, stream coordination) be moved into `Viewport` or `DashboardManager`?
- [ ] Refactor shared functionality (e.g., default symbol/timeframe logic) into utility classes/functions if applicable.
- [ ] Clean up any temporary workarounds or TODOs identified during refactoring.

### 6. Update In-Code Documentation & README

- [ ] Update docstrings in all new/modified files (`Viewport`, `DashboardManager`, `widgets/*`, `DashboardProgram`, etc.).
- [ ] Ensure `README.md` reflects the new architecture and how to run the application.
- [ ] Add developer documentation about how to create new widget types (inheriting `BaseWidget`, etc.).

### 7. Automated Testing

- [ ] Write unit/integration tests for the core widget system (`DashboardManager`, `BaseWidget`).
- [ ] Consider UI automation tests if feasible for testing docking and widget interactions.

## Low Priority Tasks (Future Polish)

### 8. UI Polishing

- [ ] Review widget default sizes and adjust as needed.
- [ ] Add any missing keyboard shortcuts for common actions.
- [ ] Consider adding tooltips for clarification on UI elements.

## Merge Strategy

1. Complete all Priority Tasks before merging.
2. Create a PR with detailed description of all changes.
3. Code review.
4. Test thoroughly.
5. Merge `feature/dockable-widgets` into `main` (or `develop`).

## Timeline

- Priority Tasks: [Estimate based on complexity]
- Medium Priority: [Estimate]
- Low Priority: Ongoing / As needed

## Responsible Team Members

- Main Refactor: [You!]
- Code Review: [If applicable]
- Testing: [You! / QA] 