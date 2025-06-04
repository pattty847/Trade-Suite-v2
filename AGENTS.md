# Agent & Contributor Guide: TradeSuite Project

## 1. Introduction

Welcome to the TradeSuite project! This document serves as a guide for AI agents and human contributors working on this multi-faceted cryptocurrency trading platform and analysis suite. The goal is to ensure consistent development practices, effective collaboration, and a clear understanding of the project's architecture and ongoing efforts.

## 2. Project Overview

The project is primarily composed of three major systems, each with its own set of sub-modules:

### 2.1. `trade_suite/` - The Core Trading Application
This is the main GUI application for real-time cryptocurrency trading and market data visualization.
-   **Functionality:** Multi-exchange connectivity (via CCXT PRO), real-time candlestick charting, order book display, trade execution (planned), and a flexible dockable widget-based UI.
-   **Key Sub-directories & Files:**
    -   `trade_suite/data/data_source.py`: Core data handling using CCXT PRO for market data streams.
    -   `trade_suite/data/sec/`: Module for fetching and processing data from the SEC EDGAR API (see `trade_suite/data/sec/SEC_API_README.md`).
    -   `trade_suite/widgets/`: Contains all dockable UI widgets (e.g., `chart_widget.py`, `orderbook_widget.py`, `price_level_widget.py`). Inherit from `base_widget.py`. (See `docs/DOCKABLE_WIDGETS.md`).
    -   `trade_suite/gui/`: Older GUI components, largely migrated to `widgets/`.
    -   `trade_suite/core/` (or similar convention): Houses `task_manager.py` (manages async data streams), `config_manager.py`.
    -   `trade_suite/program/` (or similar convention): Controllers like `dashboard_program.py` (handles widget creation logic, signal handling) and `viewport.py` (manages main window and docking).
-   **Entry Point:** `python -m trade_suite`
-   **Documentation:** `README.md`, `docs/DOCKABLE_WIDGETS.md`

### 2.2. `sentinel/` - Data Collection & Alerting System
This system operates in two main capacities: a 24/7 data collection service and an advanced alert bot.
-   **A. Sentinel Data Collector:**
    -   **Functionality:** Collects and stores BTC/USD order book snapshots and trades from Coinbase (initially) into InfluxDB. Designed for resilience and continuous operation.
    -   **Key Sub-directories & Files:**
        -   `sentinel/collectors/`: Bridges `TradeSuiteData` to internal queues.
        -   `sentinel/writers/`: Writes data from queues to InfluxDB (e.g., `influx_writer.py`).
        -   `sentinel/supervisor.py`: Orchestrates collector and writer tasks, manages queues and task lifecycles.
        -   `sentinel/schema.py`: Defines InfluxDB Line Protocol schemas.
        -   `sentinel/config.py`: Configuration for data collection.
    -   **Entry Point:** `python -m sentinel.run`
    -   **Documentation:** `sentinel/PROGRESS.md`
-   **B. Sentinel Alert Bot:**
    -   **Functionality:** Monitors market conditions (price levels, CVD, percentage changes, etc.) based on live data streams and triggers alerts via various notifiers. Can run integrated or standalone.
    -   **Key Sub-directories & Files:**
        -   `sentinel/alert_bot/manager.py`: `AlertDataManager` class, the core orchestrator.
        -   `sentinel/alert_bot/config/alerts_config.yaml`: Primary configuration for alerts.
        -   `sentinel/alert_bot/rules/`: Logic for different alert types (price, percentage, CVD, volatility).
        -   `sentinel/alert_bot/processors/`: Data processors (e.g., `cvd_calculator.py`).
        -   `sentinel/alert_bot/notifier/`: Notification modules (console, email).
    -   **Entry Point:** `python -m sentinel.alert_bot.main`
    -   **Documentation:** `sentinel/alert_bot/README.md`, `sentinel/alert_bot/docs/ALERTBOTMANAGER.md`

### 2.3. `scanner/` - Price Action Analysis Tools
This module is evolving to provide sophisticated tools for price action analysis, intended to be callable by Large Language Models (LLMs) for generating market insights.
-   **Functionality:**
    -   `tool_analyze_chart_window`: Analyzes a specific chart window, providing detailed metrics, indicator values (including intra-dataset deltas), and key price action events.
    -   `tool_scanner_run`: Scans symbols against pre-defined criteria based on latest data, identifies matches, and can calculate inter-scan deltas.
-   **Key Components (Planned/In-Progress):**
    -   `IndicatorCalculator`: Computes technical indicators and intra-dataset deltas.
    -   `PriceActionAnalyzer`: Identifies key events like swing points, OB/OS crossings, volume spikes.
    -   Adapts existing `scanner/main_workflow.py`.
-   **Data Storage:**
    -   `data/cache/`: Raw OHLCV data.
    -   `scan_snapshots/`: Results from scanner runs (e.g., `results_last_{timeframe}.parquet`).
-   **Configuration:** `scan_config.yaml`
-   **Documentation:** `scanner/llm_price_action_plan_v1.md`

### 2.4. Common Directories
-   `scripts/`: Utility scripts (installation, build executables).
-   `docs/`: General project documentation.
-   `config/`: Global configuration files (e.g., `factory_layout.ini`, `user_layout.ini` for TradeSuite GUI).
-   `tests/`: (Currently needs significant development) Intended for unit and integration tests.

## 3. Development Environment & Setup

-   Refer to `README.md` for detailed prerequisites and installation instructions (Python 3.10+, InfluxDB, API keys).
-   The project uses a virtual environment (managed by `scripts/install.sh` or `scripts/install.bat`, preferably with `uv`).
-   Dependencies are listed in `requirements.txt`.

## 4. Key Areas & Current Focus

-   **Testing Infrastructure:** The current testing system is minimal or "broken." Establishing a robust testing framework (unit, integration) across all major components (`trade_suite`, `sentinel`, `scanner`) is a high priority.
-   **Sentinel Data Collector Enhancements:**
    -   Order book binning logic in `sentinel/schema.py :: build_book_lp()`.
    -   InfluxDB gap audit mechanism.
    -   (See `sentinel/PROGRESS.md` for more).
-   **LLM Tool Development (`scanner/`):**
    -   Full implementation of `tool_analyze_chart_window` and `tool_scanner_run` as per `scanner/llm_price_action_plan_v1.md`.
    -   Refinement of `PriceActionAnalyzer` for more sophisticated event detection.
-   **TradeSuite Trading Capabilities:** Implementing order execution and management features.
-   **Codebase Cleanup:** Identifying and removing old, unused, or redundant files/code.

## 5. Contribution Guidelines

### 5.1. General Style
-   Follow Python best practices (PEP 8).
-   Aim for clear, modular, and well-documented code.
-   Maintain consistency with the existing coding style within each module.
-   Use type hinting extensively.

### 5.2. Commits
-   Make atomic commits with clear and concise messages.
-   Reference relevant issue numbers if applicable.

### 5.3. Pull Requests (PRs)
-   **Title Format:** `[<module_area>] <Brief description of change>`
    -   Examples:
        -   `[Sentinel/AlertBot] Add support for XYZ alert condition`
        -   `[TradeSuite/Chart] Fix rendering issue with EMA indicator`
        -   `[Scanner] Implement inter-scan delta calculation for tool_scanner_run`
        -   `[Docs] Update AGENTS.md with testing guidelines`
-   Provide a clear description of the changes made and the problem solved.
-   Ensure changes are related to the PR's stated purpose.
-   Update relevant documentation (READMEs, design docs) if your changes impact functionality or architecture.

## 6. Validating Changes

1.  **Running the Applications:**
    -   TradeSuite GUI: `python -m trade_suite`
    -   Sentinel Alert Bot: `python -m sentinel.alert_bot.main --config path/to/alerts_config.yaml`
    -   Sentinel Data Collector: `python -m sentinel.run [--dry-run | --live]`
    -   Scanner (manual trigger, specifics may vary): e.g., `python -m scanner.main_workflow --config scan_config.yaml` (adapt as tools evolve).
2.  **Linting:** (Assumed, standard practice) Run a linter (e.g., Flake8, Pylint) to check for style and basic errors. (Agent: If a specific linter configuration is found, adhere to it).
3.  **Testing (Future Goal):**
    -   Once the testing framework is established, all new contributions MUST include relevant tests.
    -   All tests MUST pass before merging a PR.
    -   Agent: When adding or modifying code, proactively identify areas for new tests and, if feasible, implement them or note them for future development.

## 7. Working with the AI Agent (Instructions for Gemini/Cursor)

-   **Contextual Awareness:** This `AGENTS.md` file is your primary guide. Refer to it and the linked documents to understand project structure, goals, and conventions.
-   **Focus on Modularity:** When implementing new features or refactoring, prioritize creating well-defined, modular components with clear responsibilities. This aligns with the project's existing architecture.
-   **Incremental Changes:** Prefer smaller, incremental changes that are easier to review and test.
-   **Documentation:**
    -   When adding new features, update or create relevant README sections or design documents.
    -   If a tool's behavior or output format changes, ensure its documentation (e.g., in `scanner/llm_price_action_plan_v1.md`) is updated.
-   **Testing:** As noted, testing is a key area for improvement. When you write new code, please:
    -   Identify what unit or integration tests would be appropriate.
    -   If possible within the current scope/tooling, write these tests.
    -   If not immediately feasible, clearly note the required tests in comments or as a follow-up task.
-   **File Operations:**
    -   Confirm before deleting files unless they are clearly temporary or obsolete (e.g., old log files).
    -   When creating new files, place them in the appropriate module directory.
-   **Problem Solving:** If requirements are unclear or there are multiple ways to implement a solution, briefly outline the options and your recommended approach before proceeding.

## 8. Codebase Cleanup & Future Work

-   **Identify & Remove Redundancy:** Actively look for opportunities to remove old/unused files, duplicated code, or obsolete logic.
-   **Improve Test Coverage:** This is an ongoing effort.
-   **Refine Configuration Management:** Standardize configuration loading and access across different modules.
-   **Enhance Error Handling & Resilience:** Particularly for long-running services like Sentinel.

By following these guidelines, we can collaboratively build and maintain a robust and powerful TradeSuite ecosystem. 